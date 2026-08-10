from dataclasses import dataclass

from app.infrastructure.db.transactional import async_transactional
from app.modules.mapping.domain.entities import (
    MappingScope,
)
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


@dataclass(slots=True, frozen=True)
class GetMappingScopesResult:
    mapping_scopes: list[MappingScope]


class GetMappingScopesUseCase:
    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
    ) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self,
    ) -> GetMappingScopesResult:
        """Get mapping scopes list"""

        mapping_scopes: list[MappingScope] = (
            await self.uow.mapping_scope_repo.list_recent_scopes()
        )

        return GetMappingScopesResult(mapping_scopes)
