from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
)
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(slots=True, frozen=True)
class GetMappingScopeRulesQuery:
    mapping_scope_id: UUID


@dataclass(slots=True, frozen=True)
class GetMappingScopeRulesResult:
    rules: list[MappingScopeRule]
    mapping_results: list[MappingEntityResult]


class GetMappingScopeRulesUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
    ) -> None:
        self.mapping_repo = mapping_repo

    async def execute(
        self,
        query: GetMappingScopeRulesQuery,
    ) -> GetMappingScopeRulesResult:
        """Get list of rules"""

        # -- get mapping scope with rules ids
        mapping_scope: MappingScope | None = await self.mapping_repo.get_scope_by_id(
            scope_id=query.mapping_scope_id,
            with_rules=True,
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope {query.mapping_scope_id} not found"
            )
        if not mapping_scope.rules:
            raise MappingModuleNotFoundError(
                f"Not provided rules for mapping scope {query.mapping_scope_id}"
            )

        # -- get results for rules of scope
        mapping_results: list[MappingEntityResult] = (
            await self.mapping_repo.list_results(
                scope_id=mapping_scope.id,
            )
        )

        return GetMappingScopeRulesResult(
            rules=mapping_scope.rules,
            mapping_results=mapping_results,
        )
