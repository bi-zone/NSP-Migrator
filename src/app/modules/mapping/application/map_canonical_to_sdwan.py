from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
)
from app.modules.mapping.application.dto import MappingResultsSummary
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
)
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
)
from app.modules.mapping.ports.canonical_reader.port import CanonicalReaderPort
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalRule,
    CanonicalScopeEntities,
)
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort
from app.modules.mapping.services.mapping_objects.mapping_objects_service import (
    MappingObjectsService,
)
from app.modules.mapping.services.mapping_rules.mapping_scope_rules_builder import (
    MappingScopeRulesBuilder,
)


@dataclass(slots=True, frozen=True)
class MapCanonicalToSdwanCommand:
    mapping_scope_title: str
    sdwan_target_id: str
    canonical_snapshot_id: UUID
    canonical_rules_ids: list[UUID]


@dataclass(slots=True, frozen=True)
class MapCanonicalToSdwanResult:
    mapping_scope_id: UUID
    mapping_results_summary: MappingResultsSummary
    mapped_rules_count: int


class MapCanonicalToSdwanUseCase:
    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
        sdwan_gateway: MappingSDWANGatewayPort,
        canonical_reader: CanonicalReaderPort,
        mapping_objects_service: MappingObjectsService = MappingObjectsService(),
        mapping_scope_rules_builder: MappingScopeRulesBuilder = MappingScopeRulesBuilder(),
    ) -> None:
        self.uow = uow
        self.sdwan_gateway = sdwan_gateway
        self.canonical_reader = canonical_reader
        self.mapping_objects_service = mapping_objects_service
        self.mapping_scope_rules_builder = mapping_scope_rules_builder

    @async_transactional(read_only=False)
    async def execute(
        self,
        command: MapCanonicalToSdwanCommand,
    ) -> MapCanonicalToSdwanResult:
        """
        New pipeline:
            1. Validate SD-WAN target.
            2. Create mapping scope shell.
            3. Fetch SD-WAN catalog.
            4. Fetch canonical entities and canonical rules with operands.
            5. Build mapping entity results.
            6. Persist mapping results.
            7. Build MappingScopeRule + MappingScopeRuleOperand.
            8. Persist scope rules.
        """

        target: SdwanDeviceObject = await self.sdwan_gateway.get_device_object(
            dev_obj_id=command.sdwan_target_id,
        )
        if target.cpe_id is None:
            raise MappingModuleDomainValidationError(
                f"Selected target {target.dev_obj_id} does not have cpe_id"
            )

        if not command.canonical_rules_ids:
            raise MappingModuleDomainValidationError(
                "Canonical rules ids must be provided"
            )

        mapping_scope = MappingScope.create_header(
            title=command.mapping_scope_title,
            canonical_snapshot_id=command.canonical_snapshot_id,
            sdwan_target_id=command.sdwan_target_id,
        )

        # Persist scope header first because mapping_entity_result has FK to scope.
        await self.uow.mapping_scope_repo.add_scope(mapping_scope)

        sdwan_full_catalog: SdwanFullCatalog = (
            await self.sdwan_gateway.get_sdwan_full_catalog()
        )

        canonical_scope_entities: CanonicalScopeEntities = (
            await self.canonical_reader.get_canonical_scope_entities_data(
                canonical_snapshot_id=command.canonical_snapshot_id,
                canonical_rules_ids=command.canonical_rules_ids,
            )
        )

        canonical_rules: list[CanonicalRule] = (
            await self.canonical_reader.get_canonical_scope_rules(
                canonical_snapshot_id=command.canonical_snapshot_id,
                canonical_rules_ids=command.canonical_rules_ids,
            )
        )

        mapping_results: list[MappingEntityResult] = (
            self.mapping_objects_service.build_results(
                mapping_scope_id=mapping_scope.id,
                canonical_scope_entities=canonical_scope_entities,
                sdwan_full_catalog=sdwan_full_catalog,
            )
        )

        await self.uow.mapping_result_repo.add_results(mapping_results)

        mapping_scope_rules: list[MappingScopeRule] = (
            self.mapping_scope_rules_builder.build(
                mapping_scope_id=mapping_scope.id,
                canonical_rules=canonical_rules,
                canonical_scope_entities=canonical_scope_entities,
                mapping_results=mapping_results,
            )
        )

        await self.uow.mapping_scope_repo.attach_rules(
            scope_id=mapping_scope.id,
            rules=mapping_scope_rules,
        )

        return MapCanonicalToSdwanResult(
            mapping_scope_id=mapping_scope.id,
            mapping_results_summary=self.mapping_objects_service.build_results_summary(
                results=mapping_results,
            ),
            mapped_rules_count=len(mapping_scope_rules),
        )
