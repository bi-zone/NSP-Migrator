"""Integration coverage for the CSP profile lifecycle use cases.

The lifecycle scenario verifies the contract that matters across application
and persistence boundaries: profile metadata and encrypted credentials are
created together, secrets are never persisted as plaintext, updates preserve
the intended credential state, password removal keeps mTLS credentials usable,
and deletion removes both profile metadata and stored credentials.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.csp_profiles.adapters.db.uow import CSPProfilesUnitOfWork
from app.modules.settings.csp_profiles.application.change_profile_active_status import (
    ChangeProfileActiveStatusCommand,
    ChangeProfileActiveStatusUseCase,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileCommand,
    DeleteProfileUseCase,
)
from app.modules.settings.csp_profiles.application.get_profile import (
    GetProfileQuery,
    GetProfileUseCase,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordCommand,
    RemoveProfilePasswordUseCase,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UpdateProfileCommand,
    UpdateProfileUseCase,
)


@pytest.mark.asyncio
async def test_profile_lifecycle_persists_encrypted_credentials_and_updates_profile(
    db_session: AsyncSession,
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    profile_command_factory: Callable[..., CreateProfileCommand],
    create_profile_use_case: CreateProfileUseCase,
    get_profile_use_case: GetProfileUseCase,
    list_profiles_use_case: ListProfilesUseCase,
    update_profile_use_case: UpdateProfileUseCase,
    remove_profile_password_use_case: RemoveProfilePasswordUseCase,
    change_profile_active_status_use_case: ChangeProfileActiveStatusUseCase,
    delete_profile_use_case: DeleteProfileUseCase,
) -> None:
    """Run a full profile lifecycle through real UoW, repositories, and DB rows."""
    created = await create_profile_use_case.execute(
        profile_command_factory(
            name="  Primary  ",
            base_url="https://CSP.EXAMPLE/",
            username=" operator ",
            password="initial-password",
        )
    )

    assert created.name == "Primary"
    assert created.base_url == "https://csp.example"
    assert created.username == "operator"
    assert created.auth_type == "password_mtls"
    assert created.is_connectable is True

    rows = (
        await db_session.execute(
            text("""
                SELECT p.name,
                       p.base_url,
                       p.username,
                       c.encrypted_payload,
                       c.has_password,
                       c.has_certificate,
                       c.certificate_has_private_key
                FROM csp_profile p
                JOIN csp_profile_credentials c ON c.profile_id = p.id
                WHERE p.id = :profile_id
                """),
            {"profile_id": created.id},
        )
    ).one()
    encrypted_payload = bytes(rows.encrypted_payload)
    assert rows.name == "Primary"
    assert rows.base_url == "https://csp.example"
    assert rows.username == "operator"
    assert rows.has_password is True
    assert rows.has_certificate is True
    assert rows.certificate_has_private_key is True
    assert b"initial-password" not in encrypted_payload
    assert b"BEGIN CERTIFICATE" not in encrypted_payload
    assert b"BEGIN PRIVATE KEY" not in encrypted_payload

    retrieved = await get_profile_use_case.execute(GetProfileQuery(created.id))
    listed = await list_profiles_use_case.execute(
        query=ListProfilesQuery(active_only=False)
    )
    assert retrieved.id == created.id
    assert [profile.id for profile in listed.profiles] == [created.id]

    updated = await update_profile_use_case.execute(
        UpdateProfileCommand(
            profile_id=created.id,
            name="Primary Renamed",
            base_url="https://new-csp.example/",
            username="new-operator",
            password="rotated-password",
        )
    )
    assert updated.name == "Primary Renamed"
    assert updated.base_url == "https://new-csp.example"
    assert updated.username == "new-operator"
    assert updated.has_password is True

    async with csp_profiles_uow_factory() as uow:
        credentials = await uow.credentials.get_for_connection(created.id)
    assert credentials is not None
    assert credentials.password == "rotated-password"

    without_password = await remove_profile_password_use_case.execute(
        RemoveProfilePasswordCommand(created.id)
    )
    assert without_password.auth_type == "mtls"
    assert without_password.has_password is False
    assert without_password.is_connectable is True

    async with csp_profiles_uow_factory() as uow:
        credentials = await uow.credentials.get_for_connection(created.id)
    assert credentials is not None
    assert credentials.password is None

    # change active status
    assert created.is_active == True

    await change_profile_active_status_use_case.execute(
        command=ChangeProfileActiveStatusCommand(
            profile_id=created.id,
            new_status=False,
        )
    )
    retrieved = await get_profile_use_case.execute(GetProfileQuery(created.id))
    assert retrieved.is_active == False

    await change_profile_active_status_use_case.execute(
        command=ChangeProfileActiveStatusCommand(
            profile_id=created.id,
            new_status=True,
        )
    )
    retrieved = await get_profile_use_case.execute(GetProfileQuery(created.id))
    assert retrieved.is_active == True

    # deletion
    await delete_profile_use_case.execute(DeleteProfileCommand(created.id))
    counts = (
        await db_session.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM csp_profile WHERE id = :profile_id) AS profiles,
                    (
                        SELECT count(*)
                        FROM csp_profile_credentials
                        WHERE profile_id = :profile_id
                    ) AS credentials
                """),
            {"profile_id": created.id},
        )
    ).one()
    assert counts.profiles == 0
    assert counts.credentials == 0
