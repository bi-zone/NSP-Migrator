from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileConnectionValidationError,
    CSPProfileNotFoundError,
)
from app.modules.settings.csp_profiles.ports.connection_tester import (
    AllowedVPC,
    CSPProfileConnectionTesterPort,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class TestProfileConnectionCommand:
    profile_id: UUID


@dataclass(frozen=True, slots=True)
class TestProfileConnectionResult:
    reachable: bool
    authenticated: bool
    allowed_vpcs: list[AllowedVPC]
    checked_at: datetime


class TestProfileConnectionUseCase:
    def __init__(
        self,
        uow: CSPProfilesUnitOfWorkPort,
        connection_tester: CSPProfileConnectionTesterPort,
    ) -> None:
        self.uow = uow
        self._connection_tester = connection_tester

    @async_transactional(read_only=True)
    async def execute(
        self, command: TestProfileConnectionCommand
    ) -> TestProfileConnectionResult:
        profile = await self.uow.profiles.get_by_id(command.profile_id)
        if profile is None:
            raise CSPProfileNotFoundError
        credentials = await self.uow.credentials.get_for_connection(profile.id)
        if credentials is None or not profile.is_connectable:
            raise CSPProfileConnectionValidationError
        allowed_vpcs = await self._connection_tester.test(profile, credentials)
        return TestProfileConnectionResult(
            reachable=True,
            authenticated=True,
            allowed_vpcs=allowed_vpcs,
            checked_at=datetime.now(UTC),
        )
