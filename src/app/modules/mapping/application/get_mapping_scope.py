from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.mapping.domain.entities import MappingScope
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


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
        uow: MappingUnitOfWorkPort,
    ) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self,
        query: GetMappingScopeQuery,
    ) -> GetMappingScopeResult:
        """Get mapping scope data"""

        mapping_scope: MappingScope | None = (
            await self.uow.mapping_scope_repo.get_scope_by_id(
                scope_id=query.mapping_scope_id,
                with_rules=query.with_rules,
            )
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope {query.mapping_scope_id} not found"
            )

        return GetMappingScopeResult(mapping_scope)
