from __future__ import annotations

from collections.abc import Sequence

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes
from cryptography.hazmat.primitives.serialization import pkcs12

from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.csp_profiles.domain.exceptions import (
    InvalidCertificateBundleError,
)
from app.modules.settings.csp_profiles.ports.certificate_bundle_converter import (
    CertificateBundleConverterPort,
)


class CryptographyCertificateBundleConverter(CertificateBundleConverterPort):
    """Normalize PEM or PKCS#12 client bundles to unencrypted combined PEM."""

    def convert(self, bundle: CertificateBundleDTO) -> str:
        if not bundle:
            raise InvalidCertificateBundleError
        password = _passphrase_bytes(bundle.passphrase)
        try:
            match bundle.format:
                case CertificateBundleFormat.PEM:
                    return _normalize_pem(bundle.data, password)
                case CertificateBundleFormat.PKCS12:
                    return _normalize_pkcs12(bundle.data, password)
                case _:
                    raise InvalidCertificateBundleError

        except InvalidCertificateBundleError:
            raise
        except Exception:
            raise InvalidCertificateBundleError from None


def _passphrase_bytes(passphrase: str | None) -> bytes | None:
    if not passphrase:
        return None
    return passphrase.encode("utf-8")


def _normalize_pem(bundle: bytes, password: bytes | None) -> str:
    certificates = x509.load_pem_x509_certificates(bundle)
    private_key = serialization.load_pem_private_key(bundle, password=password)
    if not certificates or private_key is None:
        raise ValueError
    return _export_combined_pem(private_key, certificates[0], certificates[1:])


def _normalize_pkcs12(bundle: bytes, password: bytes | None) -> str:
    private_key, certificate, additional = pkcs12.load_key_and_certificates(
        bundle,
        password,
    )
    if private_key is None or certificate is None:
        raise ValueError
    return _export_combined_pem(private_key, certificate, additional or ())


def _export_combined_pem(
    private_key: PrivateKeyTypes,
    leaf: x509.Certificate,
    additional: Sequence[x509.Certificate],
) -> str:
    parts = [
        leaf.public_bytes(serialization.Encoding.PEM),
        *(
            certificate.public_bytes(serialization.Encoding.PEM)
            for certificate in additional
        ),
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    ]
    return b"".join(parts).decode("utf-8")
