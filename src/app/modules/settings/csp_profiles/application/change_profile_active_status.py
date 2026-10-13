from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileError,
    CSPProfileNotFoundError,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class ChangeProfileActiveStatusCommand:
    profile_id: UUID
    new_status: bool


class ChangeProfileActiveStatusUseCase:
    def __init__(
        self,
        uow: CSPProfilesUnitOfWorkPort,
    ) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(self, command: ChangeProfileActiveStatusCommand) -> None:
        profile: CSPProfile | None = await self.uow.profiles.get_by_id(
            command.profile_id
        )
        if profile is None:
            raise CSPProfileNotFoundError

        if profile.is_active == command.new_status:
            return

        changed: bool = await self.uow.profiles.change_active_status(
            profile_id=profile.id,
            new_status=command.new_status,
        )
        if not changed:
            raise CSPProfileError("Profile active status not updated")
