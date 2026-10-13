from dataclasses import dataclass, replace
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.application.dto import CSPProfileDTO
from app.modules.settings.csp_profiles.application.mappers import profile_to_dto
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileConnectionValidationError,
    CSPProfileNotFoundError,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class RemoveProfilePasswordCommand:
    profile_id: UUID


class RemoveProfilePasswordUseCase:
    def __init__(self, uow: CSPProfilesUnitOfWorkPort) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(self, command: RemoveProfilePasswordCommand) -> CSPProfileDTO:
        profile = await self.uow.profiles.get_by_id(command.profile_id)
        if profile is None:
            raise CSPProfileNotFoundError

        if profile.credential_metadata is None:
            raise CSPProfileConnectionValidationError

        metadata = replace(profile.credential_metadata, has_password=False)
        updated = profile.update(credential_metadata=metadata)

        await self.uow.credentials.remove_password(profile.id)
        return profile_to_dto(updated)
