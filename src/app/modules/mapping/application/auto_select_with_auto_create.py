from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanCommand,
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.domain.entities import MappingEntityResult, MappingScope
from app.modules.mapping.domain.enums import MappingResultStatus
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class AutoSelectEntitiesWithCreateForScopeCommand:

    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class AutoSelectEntitiesWithCreateForScopeResult:

    failed_selects: int
    success_selects: int
    errors: list[str]


class AutoSelectEntitiesWithCreateForScopeUseCase:
    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
        select_with_create: SelectEntityWithCreateOnSdwanUseCase,
    ) -> None:
        self.uow = uow
        self.select_with_create = select_with_create

    @async_transactional(uc_for_reuse_session=["select_with_create"], read_only=False)
    async def execute(
        self,
        command: AutoSelectEntitiesWithCreateForScopeCommand,
    ) -> AutoSelectEntitiesWithCreateForScopeResult:

        # -- get unresolved entities of mapping scope rules
        mapping_scope: MappingScope | None = (
            await self.uow.mapping_scope_repo.get_scope_by_id(
                scope_id=command.mapping_scope_id
            )
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope {command.mapping_scope_id} not found"
            )

        unresolved_mapping_results: list[MappingEntityResult] = (
            await self.uow.mapping_result_repo.list_by_scope(
                scope_id=mapping_scope.id,
                status=MappingResultStatus.UNRESOLVED,
            )
        )

        errors: list[str] = []
        success_auto_creates = 0
        for mapping_result in unresolved_mapping_results:
            try:
                await self.select_with_create.execute(
                    command=SelectEntityWithCreateOnSdwanCommand(mapping_result.id)
                )
                success_auto_creates += 1
            except Exception as err:
                errors.append(str(err))

        return AutoSelectEntitiesWithCreateForScopeResult(
            failed_selects=len(errors),
            success_selects=success_auto_creates,
            errors=errors,
        )
