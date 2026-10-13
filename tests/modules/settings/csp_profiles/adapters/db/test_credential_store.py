from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import SecretBytes

from app.core.config.csp_credentials import CSPCredentialsConfig
from app.modules.settings.csp_profiles.adapters.db.credential_store import (
    SQLAlchemyEncryptedCredentialStore,
)
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
)
from app.modules.settings.csp_profiles.domain.exceptions import (
    CredentialEncryptionError,
)
from app.modules.settings.csp_profiles.domain.value_objects import (
    ProfileCredentials,
    StoredCredentialMetadata,
)
from app.modules.settings.csp_profiles.ports.credential_store import CredentialWrite


class _FakeSession:
    def __init__(self) -> None:
        self.model = None
        self.flushes = 0

    async def get(self, _model_type, _profile_id):
        return self.model

    def add(self, model) -> None:
        self.model = model

    async def flush(self) -> None:
        self.flushes += 1

    async def delete(self, _model) -> None:
        self.model = None


def _codec() -> AESGCMCredentialCodec:
    config = CSPCredentialsConfig(
        active_key=SecretBytes(b"k" * 32),
    )
    return AESGCMCredentialCodec(config)


def _write() -> CredentialWrite:
    return CredentialWrite(
        credentials=ProfileCredentials(
            certificate_pem="CERTIFICATE-MARKER",
            password="PASSWORD-MARKER",
        ),
        metadata=StoredCredentialMetadata(
            has_password=True,
            has_certificate=True,
            certificate_sha256="a" * 64,
            certificate_not_after=datetime.now(UTC),
            certificate_has_private_key=True,
        ),
    )


def test_store_persists_ciphertext_and_safe_metadata_only() -> None:
    asyncio.run(_test_store_persists_ciphertext_and_safe_metadata_only())


async def _test_store_persists_ciphertext_and_safe_metadata_only() -> None:
    session = _FakeSession()
    store = SQLAlchemyEncryptedCredentialStore(cast(Any, session), _codec())
    profile_id = uuid4()

    await store.put_for_profile(profile_id, _write())

    model = session.model
    assert model.profile_id == profile_id
    assert b"PASSWORD-MARKER" not in model.encrypted_payload
    assert b"CERTIFICATE-MARKER" not in model.encrypted_payload
    assert not hasattr(model, "password")
    assert not hasattr(model, "certificate_pem")
    assert await store.get_for_connection(profile_id) == _write().credentials


def test_store_does_not_touch_session_when_encryption_fails() -> None:
    asyncio.run(_test_store_does_not_touch_session_when_encryption_fails())


async def _test_store_does_not_touch_session_when_encryption_fails() -> None:
    class _FailingCodec:
        def encrypt(self, _profile_id, _credentials):
            raise CredentialEncryptionError

    session = _FakeSession()
    store = SQLAlchemyEncryptedCredentialStore(
        cast(Any, session),
        cast(Any, _FailingCodec()),
    )

    with pytest.raises(CredentialEncryptionError):
        await store.put_for_profile(uuid4(), _write())

    assert session.model is None
    assert session.flushes == 0


def test_remove_password_reencrypts_combined_payload() -> None:
    asyncio.run(_test_remove_password_reencrypts_combined_payload())


async def _test_remove_password_reencrypts_combined_payload() -> None:
    session = _FakeSession()
    store = SQLAlchemyEncryptedCredentialStore(cast(Any, session), _codec())
    profile_id = uuid4()
    await store.put_for_profile(profile_id, _write())
    old_nonce = session.model.nonce

    await store.remove_password(profile_id)

    credentials = await store.get_for_connection(profile_id)
    assert credentials is not None
    assert credentials.password is None
    assert credentials.certificate_pem == "CERTIFICATE-MARKER"
    assert session.model.has_password is False
    assert session.model.nonce != old_nonce
