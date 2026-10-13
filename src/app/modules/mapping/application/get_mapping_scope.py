from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.domain.entities import MappingScope
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(slots=True, frozen=True)
class GetMappingScopeQuery:
    mapping_scope_id: UUID
    with_rules: bool = False


@dataclass(slots=True, frozen=True)
class GetMappingScopeResult:
    mapping_scope: MappingScope


class GetMappingScopeUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
    ) -> None:
        self.mapping_repo = mapping_repo

    async def execute(
        self,
        query: GetMappingScopeQuery,
    ) -> GetMappingScopeResult:
        """Get mapping scope data"""

        mapping_scope: MappingScope | None = await self.mapping_repo.get_scope_by_id(
            scope_id=query.mapping_scope_id,
            with_rules=query.with_rules,
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope {query.mapping_scope_id} not found"
            )

        return GetMappingScopeResult(mapping_scope)
