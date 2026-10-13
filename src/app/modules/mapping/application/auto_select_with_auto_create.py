from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.application.refresh_mapping_scope_catalog_fingerprint import (
    RefreshMappingScopeCatalogFingerprintCommand,
    RefreshMappingScopeCatalogFingerprintUseCase,
)
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanCommand,
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.domain.entities import MappingEntityResult, MappingScope
from app.modules.mapping.domain.enums import MappingResultStatus
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class AutoSelectEntitiesWithCreateForScopeCommand:
    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class AutoSelectEntitiesWithCreateForScopeResult:
    failed_selects: int
    success_selects: int
    errors: list[str]
    catalog_fingerprint_changed: bool


class AutoSelectEntitiesWithCreateForScopeUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        select_with_create: SelectEntityWithCreateOnSdwanUseCase,
        refresh_mapping_scope_catalog_fingerprint: RefreshMappingScopeCatalogFingerprintUseCase,
    ) -> None:
        self.mapping_repo = mapping_repo
        self.select_with_create = select_with_create
        self.refresh_mapping_scope_catalog_fingerprint = (
            refresh_mapping_scope_catalog_fingerprint
        )

    async def execute(
        self,
        command: AutoSelectEntitiesWithCreateForScopeCommand,
    ) -> AutoSelectEntitiesWithCreateForScopeResult:

        # -- get unresolved entities of mapping scope rules
        mapping_scope: MappingScope | None = await self.mapping_repo.get_scope_by_id(
            scope_id=command.mapping_scope_id
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope {command.mapping_scope_id} not found"
            )

        unresolved_mapping_results: list[MappingEntityResult] = (  # fmt: off
            await self.mapping_repo.list_results(
                scope_id=mapping_scope.id,
                status=MappingResultStatus.UNRESOLVED,
            )
        )

        errors: list[str] = []
        success_auto_creates = 0
        for mapping_result in unresolved_mapping_results:
            try:
                await self.select_with_create.execute(
                    command=SelectEntityWithCreateOnSdwanCommand(
                        mapping_scope_id=mapping_scope.id,
                        mapping_result_id=mapping_result.id,
                        refresh_catalog_fingerprint=False,
                    )
                )
                success_auto_creates += 1
            except Exception as err:
                errors.append(str(err))

        # -- refresh fingerprint if objects catalog was changed
        catalog_fingerprint_changed = False
        if success_auto_creates > 0:
            refresh_result = (
                await self.refresh_mapping_scope_catalog_fingerprint.execute(
                    RefreshMappingScopeCatalogFingerprintCommand(
                        mapping_scope_id=mapping_scope.id
                    )
                )
            )
            catalog_fingerprint_changed = refresh_result.catalog_fingerprint_changed

        return AutoSelectEntitiesWithCreateForScopeResult(
            failed_selects=len(errors),
            success_selects=success_auto_creates,
            errors=errors,
            catalog_fingerprint_changed=catalog_fingerprint_changed,
        )
