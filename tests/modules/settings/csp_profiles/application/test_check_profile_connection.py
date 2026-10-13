"""Integration coverage for CSP profile connection checks.

The tests keep the external CSP boundary fake, but exercise the real profile
lookup, credential decryption, and use case validation path. This proves that a
stored profile can be used to attempt a connection and that connection failures
are surfaced through the module's typed errors.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.modules.settings.csp_profiles.adapters.db.uow import CSPProfilesUnitOfWork
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionCommand as ConnectionCommand,
)
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionUseCase as ConnectionUseCase,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileAuthenticationError,
    CSPProfileConnectionError,
    CSPProfileConnectionValidationError,
)


@pytest.mark.asyncio
async def test_check_profile_connection_uses_stored_credentials_and_returns_allowed_vpcs(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    create_persisted_profile: Callable[..., object],
    connection_tester_factory: Callable[..., object],
) -> None:
    """Prove connection checks use decrypted credentials from the test database."""
    profile = await create_persisted_profile(
        name="Connection Profile",
        password="connection-password",
    )
    tester = connection_tester_factory()
    use_case = ConnectionUseCase(csp_profiles_uow_factory(), tester)  # type: ignore

    result = await use_case.execute(ConnectionCommand(profile.id))

    assert result.reachable is True
    assert result.authenticated is True
    assert [vpc.vpc_id for vpc in result.allowed_vpcs] == ["vpc-1"]
    assert tester.seen_profile is not None
    assert tester.seen_profile.id == profile.id
    assert tester.seen_credentials is not None
    assert tester.seen_credentials.password == "connection-password"
    assert "BEGIN CERTIFICATE" in tester.seen_credentials.certificate_pem


@pytest.mark.asyncio
async def test_check_profile_connection_rejects_profile_without_usable_credentials(
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    connection_tester_factory: Callable[..., object],
) -> None:
    """Prove a profile row without stored credentials cannot be used for CSP I/O."""
    profile = CSPProfile.create(
        name="Metadata Only",
        base_url="https://csp.example",
        username="operator",
    )
    async with csp_profiles_uow_factory() as uow:
        await uow.profiles.save(profile)
        await uow.commit()

    use_case = ConnectionUseCase(
        csp_profiles_uow_factory(),
        connection_tester_factory(),  # type: ignore
    )

    with pytest.raises(CSPProfileConnectionValidationError):
        await use_case.execute(ConnectionCommand(profile.id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_error"),
    [
        ("auth", CSPProfileAuthenticationError),
        ("unavailable", CSPProfileConnectionError),
        ("timeout", CSPProfileConnectionError),
    ],
)
async def test_check_profile_connection_surfaces_typed_csp_failures(
    mode: str,
    expected_error: type[Exception],
    csp_profiles_uow_factory: Callable[[], CSPProfilesUnitOfWork],
    create_persisted_profile: Callable[..., object],
    connection_tester_factory: Callable[..., object],
) -> None:
    """Prove authorization, availability, and timeout failures stay typed."""
    profile = await create_persisted_profile(name=f"Connection Failure {mode}")
    use_case = ConnectionUseCase(
        csp_profiles_uow_factory(),
        connection_tester_factory(mode),  # type: ignore
    )

    with pytest.raises(expected_error):
        await use_case.execute(ConnectionCommand(profile.id))
