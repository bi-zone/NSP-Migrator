from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.application.dto import CSPProfileDTO
from app.modules.settings.csp_profiles.application.mappers import profile_to_dto
from app.modules.settings.csp_profiles.domain.exceptions import (
    CSPProfileNotFoundError,
)
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class GetProfileQuery:
    profile_id: UUID


class GetProfileUseCase:
    def __init__(self, uow: CSPProfilesUnitOfWorkPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetProfileQuery) -> CSPProfileDTO:
        profile = await self.uow.profiles.get_by_id(query.profile_id)
        if profile is None:
            raise CSPProfileNotFoundError
        return profile_to_dto(profile)
