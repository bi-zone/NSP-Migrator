from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.csp_profiles.adapters.db.models import (
    CSPProfileCredentialsModel,
)
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
    EncryptedCredentialPayload,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
)
from app.modules.settings.csp_profiles.ports.credential_store import (
    CredentialStorePort,
    CredentialWrite,
)


class SQLAlchemyEncryptedCredentialStore(CredentialStorePort):
    """Store only authenticated ciphertext and safe certificate metadata."""

    def __init__(
        self,
        session: AsyncSession,
        codec: AESGCMCredentialCodec,
    ) -> None:
        self.session = session
        self._codec = codec

    async def put_for_profile(
        self, profile_id: UUID, credential_write: CredentialWrite
    ) -> None:
        payload = self._codec.encrypt(profile_id, credential_write.credentials)
        model = await self.session.get(CSPProfileCredentialsModel, profile_id)
        if model is None:
            model = CSPProfileCredentialsModel(profile_id=profile_id)
            self.session.add(model)
        _apply_encrypted_payload(model, payload)
        metadata = credential_write.metadata
        model.has_password = metadata.has_password
        model.has_certificate = metadata.has_certificate
        model.certificate_sha256 = metadata.certificate_sha256
        model.certificate_not_after = metadata.certificate_not_after
        model.certificate_has_private_key = metadata.certificate_has_private_key
        await self.session.flush()

    async def get_for_connection(self, profile_id: UUID) -> ProfileCredentials | None:
        model = await self.session.get(CSPProfileCredentialsModel, profile_id)
        if model is None:
            return None
        return self._codec.decrypt(profile_id, _payload_from_model(model))

    async def remove_password(self, profile_id: UUID) -> None:
        model = await self.session.get(CSPProfileCredentialsModel, profile_id)
        if model is None:
            return
        credentials = self._codec.decrypt(profile_id, _payload_from_model(model))
        payload = self._codec.encrypt(
            profile_id,
            ProfileCredentials(
                certificate_pem=credentials.certificate_pem,
                password=None,
            ),
        )
        _apply_encrypted_payload(model, payload)
        model.has_password = False
        await self.session.flush()

    async def delete_for_profile(self, profile_id: UUID) -> None:
        model = await self.session.get(CSPProfileCredentialsModel, profile_id)
        if model is not None:
            await self.session.delete(model)
            await self.session.flush()


def _payload_from_model(
    model: CSPProfileCredentialsModel,
) -> EncryptedCredentialPayload:
    return EncryptedCredentialPayload(
        ciphertext=model.encrypted_payload,
        nonce=model.nonce,
        format_version=model.format_version,
    )


def _apply_encrypted_payload(
    model: CSPProfileCredentialsModel,
    payload: EncryptedCredentialPayload,
) -> None:
    model.encrypted_payload = payload.ciphertext
    model.nonce = payload.nonce
    model.format_version = payload.format_version
