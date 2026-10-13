from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileNotFoundError,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class DeleteProfileCommand:
    profile_id: UUID


class DeleteProfileUseCase:
    def __init__(
        self,
        uow: CSPProfilesUnitOfWorkPort,
    ) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(self, command: DeleteProfileCommand) -> None:
        profile = await self.uow.profiles.get_by_id(command.profile_id)
        if profile is None:
            raise CSPProfileNotFoundError

        await self.uow.credentials.delete_for_profile(profile.id)
        await self.uow.profiles.delete(profile.id)
