from dataclasses import dataclass

from app.modules.mapping.domain.entities import (
    MappingScope,
)
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(slots=True, frozen=True)
class GetMappingScopesResult:
    mapping_scopes: list[MappingScope]


class GetMappingScopesUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
    ) -> None:
        self.mapping_repo = mapping_repo

    async def execute(
        self,
    ) -> GetMappingScopesResult:
        """Get mapping scopes list"""

        mapping_scopes: list[MappingScope] = (
            await self.mapping_repo.list_recent_scopes()
        )

        return GetMappingScopesResult(mapping_scopes)
