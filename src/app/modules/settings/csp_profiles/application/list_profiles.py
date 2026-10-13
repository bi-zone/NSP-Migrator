from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.settings.csp_profiles.application.dto import CSPProfileDTO
from app.modules.settings.csp_profiles.application.mappers import profile_to_dto
from app.modules.settings.csp_profiles.ports.uow import CSPProfilesUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class ListProfilesQuery:
    active_only: bool = False
    profile_ids: tuple[UUID, ...] | None = None


@dataclass(frozen=True, slots=True)
class ListProfilesResult:
    profiles: list[CSPProfileDTO]


class ListProfilesUseCase:
    def __init__(self, uow: CSPProfilesUnitOfWorkPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: ListProfilesQuery) -> ListProfilesResult:
        profiles = await self.uow.profiles.list_all(
            active_only=query.active_only,
            profile_ids=query.profile_ids,
        )
        return ListProfilesResult(
            profiles=[profile_to_dto(profile) for profile in profiles]
        )
