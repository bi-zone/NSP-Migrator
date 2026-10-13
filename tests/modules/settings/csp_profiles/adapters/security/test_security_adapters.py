from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pydantic import SecretBytes

from app.core.config.csp_credentials import CSPCredentialsConfig
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
    EncryptedCredentialPayload,
)
from app.modules.settings.csp_profiles.adapters.security.certificate_bundle_converter import (
    CryptographyCertificateBundleConverter,
)
from app.modules.settings.csp_profiles.adapters.security.pem_inspector import (
    PEMCertificateInspector,
)
from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.csp_profiles.domain.exceptions import (
    CredentialIntegrityError,
    InvalidCertificateBundleError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
)


def _codec(
    active_key: bytes = b"a" * 32,
) -> AESGCMCredentialCodec:
    return AESGCMCredentialCodec(
        CSPCredentialsConfig(
            active_key=SecretBytes(active_key),
        )
    )


def test_aes_gcm_roundtrip_uses_unique_nonce_and_redacted_values() -> None:
    profile_id = uuid4()
    credentials = ProfileCredentials(
        certificate_pem="CERTIFICATE-MARKER",
        password="PASSWORD-MARKER",
    )
    codec = _codec()

    first = codec.encrypt(profile_id, credentials)
    second = codec.encrypt(profile_id, credentials)

    assert first.nonce != second.nonce
    assert codec.decrypt(profile_id, first) == credentials
    assert b"PASSWORD-MARKER" not in first.ciphertext
    assert b"CERTIFICATE-MARKER" not in first.ciphertext
    assert "PASSWORD-MARKER" not in repr(credentials)


def test_aes_gcm_rejects_tampering_wrong_profile_and_missing_key() -> None:
    profile_id = uuid4()
    payload = _codec().encrypt(
        profile_id,
        ProfileCredentials(certificate_pem="certificate", password=None),
    )
    tampered = EncryptedCredentialPayload(
        ciphertext=payload.ciphertext[:-1] + bytes([payload.ciphertext[-1] ^ 1]),
        nonce=payload.nonce,
        format_version=payload.format_version,
    )

    with pytest.raises(CredentialIntegrityError):
        _codec().decrypt(profile_id, tampered)
    with pytest.raises(CredentialIntegrityError):
        _codec().decrypt(uuid4(), payload)


def test_pem_inspector_reads_combined_certificate_and_private_key() -> None:
    certificate_pem, expected_fingerprint = _combined_pem()

    metadata = PEMCertificateInspector().inspect(certificate_pem)

    assert metadata.sha256 == expected_fingerprint
    assert metadata.has_private_key is True
    assert metadata.not_after.tzinfo is not None


def test_pem_inspector_returns_static_safe_error() -> None:
    marker = "PRIVATE-KEY-MARKER"

    with pytest.raises(InvalidCertificateBundleError) as raised:
        PEMCertificateInspector().inspect(marker)

    assert marker not in str(raised.value)
    assert marker not in repr(raised.value)


def _combined_pem() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "test-client")]
    )
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    certificate_bytes = certificate.public_bytes(serialization.Encoding.PEM)
    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return (
        (certificate_bytes + key_bytes).decode(),
        certificate.fingerprint(hashes.SHA256()).hex(),
    )


def _client_material() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "bundle-client")]
    )
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def test_converter_normalizes_unencrypted_pkcs12_to_pem() -> None:
    key, certificate = _client_material()
    p12 = pkcs12.serialize_key_and_certificates(
        name=None,
        key=key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pem = CryptographyCertificateBundleConverter().convert(
        CertificateBundleDTO(
            data=p12,
            format=CertificateBundleFormat.PKCS12,
            passphrase=None,
        )
    )
    metadata = PEMCertificateInspector().inspect(pem)

    assert metadata.has_private_key is True
    assert metadata.sha256 == certificate.fingerprint(hashes.SHA256()).hex()
    assert "BEGIN PRIVATE KEY" in pem


def test_converter_requires_passphrase_for_encrypted_pkcs12() -> None:
    key, certificate = _client_material()
    secret = "p12-secret"
    p12 = pkcs12.serialize_key_and_certificates(
        name=None,
        key=key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(secret.encode()),
    )
    converter = CryptographyCertificateBundleConverter()

    with pytest.raises(InvalidCertificateBundleError) as raised:
        converter.convert(
            CertificateBundleDTO(
                data=p12,
                format=CertificateBundleFormat.PKCS12,
                passphrase=None,
            )
        )
    assert secret not in str(raised.value)

    pem = converter.convert(
            CertificateBundleDTO(
                data=p12,
                format=CertificateBundleFormat.PKCS12,
                passphrase=secret,
            )
        )
    metadata = PEMCertificateInspector().inspect(pem)
    assert metadata.has_private_key is True
    assert metadata.sha256 == certificate.fingerprint(hashes.SHA256()).hex()


def test_converter_decrypts_encrypted_pem_private_key() -> None:
    key, certificate = _client_material()
    secret = "pem-secret"
    encrypted_pem = certificate.public_bytes(
        serialization.Encoding.PEM
    ) + key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(secret.encode()),
    )
    converter = CryptographyCertificateBundleConverter()

    with pytest.raises(InvalidCertificateBundleError):
        converter.convert(
            CertificateBundleDTO(
                data=encrypted_pem,
                format=CertificateBundleFormat.PEM,
                passphrase=None,
            )
        )

    pem = converter.convert(
            CertificateBundleDTO(
                data=encrypted_pem,
                format=CertificateBundleFormat.PEM,
                passphrase=secret,
            )
        )
    metadata = PEMCertificateInspector().inspect(pem)
    assert metadata.has_private_key is True
    assert "ENCRYPTED PRIVATE KEY" not in pem


def test_converter_plain_pem_roundtrip_keeps_fingerprint() -> None:
    certificate_pem, expected_fingerprint = _combined_pem()

    pem = CryptographyCertificateBundleConverter().convert(
        CertificateBundleDTO(
            data=certificate_pem.encode("utf-8"),
            format=CertificateBundleFormat.PEM,
            passphrase=None,
        )
    )
    metadata = PEMCertificateInspector().inspect(pem)

    assert metadata.sha256 == expected_fingerprint
    assert metadata.has_private_key is True


def test_converter_rejects_pkcs12_bytes_when_format_is_pem() -> None:
    key, certificate = _client_material()
    p12 = pkcs12.serialize_key_and_certificates(
        name=None,
        key=key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with pytest.raises(InvalidCertificateBundleError):
        CryptographyCertificateBundleConverter().convert(
            CertificateBundleDTO(
                data=p12,
                format=CertificateBundleFormat.PEM,
                passphrase=None,
            )
        )
