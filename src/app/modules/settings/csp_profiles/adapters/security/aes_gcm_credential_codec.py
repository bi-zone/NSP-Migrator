from __future__ import annotations

import json
import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config.csp_credentials import CSPCredentialsConfig
from app.modules.settings.csp_profiles.domain.exceptions import (
    CredentialDecryptionError,
    CredentialEncryptionError,
    CredentialIntegrityError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
)

FORMAT_VERSION = 1
NONCE_BYTES = 12


@dataclass(frozen=True, slots=True)
class EncryptedCredentialPayload:
    ciphertext: bytes
    nonce: bytes
    format_version: int


class AESGCMCredentialCodec:
    """Serialize and authenticate credentials bound to one profile row."""

    def __init__(self, config: CSPCredentialsConfig) -> None:
        self._config = config

    def encrypt(
        self, profile_id: UUID, credentials: ProfileCredentials
    ) -> EncryptedCredentialPayload:
        nonce = os.urandom(NONCE_BYTES)
        try:
            plaintext = json.dumps(
                {
                    "certificate_pem": credentials.certificate_pem,
                    "password": credentials.password,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            ciphertext = AESGCM(self._config.active_key.get_secret_value()).encrypt(
                nonce,
                plaintext,
                _aad(profile_id, FORMAT_VERSION),
            )
        except Exception as exc:
            raise CredentialEncryptionError from exc
        return EncryptedCredentialPayload(
            ciphertext=ciphertext,
            nonce=nonce,
            format_version=FORMAT_VERSION,
        )

    def decrypt(
        self, profile_id: UUID, payload: EncryptedCredentialPayload
    ) -> ProfileCredentials:
        if (
            payload.format_version != FORMAT_VERSION
            or len(payload.nonce) != NONCE_BYTES
        ):
            raise CredentialIntegrityError
        try:
            plaintext = AESGCM(self._config.active_key.get_secret_value()).decrypt(
                payload.nonce,
                payload.ciphertext,
                _aad(profile_id, payload.format_version),
            )
            values = json.loads(plaintext)
            certificate_pem = values["certificate_pem"]
            password = values["password"]
            if not isinstance(certificate_pem, str) or (
                password is not None and not isinstance(password, str)
            ):
                raise ValueError
            return ProfileCredentials(
                certificate_pem=certificate_pem,
                password=password,
            )
        except InvalidTag:
            raise CredentialIntegrityError from None
        except Exception as exc:
            raise CredentialDecryptionError from exc


def _aad(profile_id: UUID, format_version: int) -> bytes:
    return f"profile_id={profile_id};format_version={format_version}".encode()
