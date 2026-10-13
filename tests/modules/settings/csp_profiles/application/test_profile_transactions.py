"""Transactional integration tests for CSP profile use cases.

These tests cover behavior that unit tests with fake repositories cannot prove:
profile metadata and credentials must commit or roll back as one transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.modules.settings.csp_profiles.adapters.db.uow import CSPProfilesUnitOfWork
from app.modules.settings.csp_profiles.adapters.security.aes_gcm_credential_codec import (
    AESGCMCredentialCodec,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.domain.exceptions import (
    CredentialEncryptionError,
)
from app.modules.settings.csp_profiles.domain.value_objects import ProfileCredentials
from app.modules.settings.csp_profiles.adapters.security.certificate_bundle_converter import (
    CryptographyCertificateBundleConverter,
)
from app.modules.settings.csp_profiles.ports.certificate_inspector import (
    CertificateInspectorPort,
)


class _FailingCredentialCodec(AESGCMCredentialCodec):
    """Codec test double that fails after profile metadata has been flushed."""

    def encrypt(self, profile_id: UUID, credentials: ProfileCredentials):
        raise CredentialEncryptionError


@pytest.mark.asyncio
async def test_create_profile_rolls_back_metadata_when_credential_storage_fails(
    db_session: AsyncSession,
    session_factory: SQLAlchemySessionFactory,
    credential_codec: AESGCMCredentialCodec,
    certificate_inspector: CertificateInspectorPort,
    certificate_converter: CryptographyCertificateBundleConverter,
    profile_command_factory: Callable[..., CreateProfileCommand],
) -> None:
    """Prove profile metadata is not committed without matching credentials."""
    failing_uow = CSPProfilesUnitOfWork(
        session_factory,
        _FailingCredentialCodec(credential_codec._config),
    )
    use_case = CreateProfileUseCase(
        failing_uow,
        certificate_inspector,
        certificate_converter,
    )

    with pytest.raises(CredentialEncryptionError):
        await use_case.execute(profile_command_factory(name="Rollback Candidate"))

    count = await db_session.scalar(
        text("SELECT count(*) FROM csp_profile WHERE name = 'Rollback Candidate'")
    )
    assert count == 0
