from dataclasses import dataclass
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanDeviceObjectType,
    SdwanRulePriority,
)
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
from app.modules.mapping.domain.enums import MappingScopeRulesPriority
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.port import CanonicalReaderPort
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalRule,
    CanonicalScopeEntities,
)
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort
from app.modules.mapping.ports.repositories import MappingRepositoryPort
from app.modules.mapping.services.mapping_objects.mapping_objects_service import (
    MappingObjectsService,
)
from app.modules.mapping.services.mapping_rules.mapping_scope_rules_builder import (
    MappingScopeRulesBuilder,
)


@dataclass(slots=True, frozen=True)
class MapCanonicalToSdwanCommand:
    mapping_scope_title: str
    csp_profile_id: UUID
    vpc_id: str
    sdwan_target_id: str
    rules_priority: MappingScopeRulesPriority
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
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
        canonical_reader: CanonicalReaderPort,
        mapping_objects_service: MappingObjectsService = MappingObjectsService(),
        mapping_scope_rules_builder: MappingScopeRulesBuilder = MappingScopeRulesBuilder(),
    ) -> None:
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider
        self.canonical_reader = canonical_reader
        self.mapping_objects_service = mapping_objects_service
        self.mapping_scope_rules_builder = mapping_scope_rules_builder

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
            6. Build MappingScopeRule + MappingScopeRuleOperand.
            7. Persist scope graph in runtime cache.
        """

        async with self.sdwan_gateway_provider.acquire(
            command.csp_profile_id,
            command.vpc_id,
        ) as sdwan_gateway:
            target: SdwanDeviceObject | None = await sdwan_gateway.get_device_object(
                dev_obj_id=command.sdwan_target_id,
            )
            if not target:
                raise MappingModuleNotFoundError(
                    f"Target (device object) {command.sdwan_target_id} not found"
                )

            if not command.canonical_rules_ids:
                raise MappingModuleDomainValidationError(
                    "Canonical rules ids must be provided"
                )

            # -- check priority by target type
            if (
                target.type == SdwanDeviceObjectType.DEVICE
                and command.rules_priority != SdwanRulePriority.LOCAL
            ):
                raise MappingModuleDomainValidationError(
                    "Policies for DEVICE can be placed only in LOCAL placements"
                )

            if (
                target.type == SdwanDeviceObjectType.GROUP
                and command.rules_priority
                not in (
                    SdwanRulePriority.PRE,
                    SdwanRulePriority.POST,
                )
            ):
                raise MappingModuleDomainValidationError(
                    "Policies for GROUP can be placed only in PRE, POST placements"
                )

            sdwan_full_catalog: SdwanFullCatalog = (
                await sdwan_gateway.get_sdwan_full_catalog()
            )

        mapping_scope = MappingScope.create_header(
            title=command.mapping_scope_title,
            canonical_snapshot_id=command.canonical_snapshot_id,
            csp_profile_id=command.csp_profile_id,
            vpc_id=command.vpc_id,
            sdwan_target_id=command.sdwan_target_id,
            rules_priority=command.rules_priority,
            catalog_fingerprint=sdwan_full_catalog.get_fingerprint(),
        )

        canonical_scope_entities: CanonicalScopeEntities = (
            await self.canonical_reader.get_canonical_scope_entities_data(
                canonical_snapshot_id=command.canonical_snapshot_id,
                canonical_rules_ids=command.canonical_rules_ids,
            )
        )

        canonical_rules: list[
            CanonicalRule
        ] = await self.canonical_reader.get_canonical_scope_rules(
            canonical_snapshot_id=command.canonical_snapshot_id,
            canonical_rules_ids=command.canonical_rules_ids,
        )

        mapping_results: list[MappingEntityResult] = (
            self.mapping_objects_service.build_results(
                mapping_scope_id=mapping_scope.id,
                canonical_scope_entities=canonical_scope_entities,
                sdwan_full_catalog=sdwan_full_catalog,
            )
        )

        mapping_scope_rules: list[MappingScopeRule] = (
            self.mapping_scope_rules_builder.build(
                mapping_scope_id=mapping_scope.id,
                canonical_rules=canonical_rules,
                canonical_scope_entities=canonical_scope_entities,
                mapping_results=mapping_results,
            )
        )

        await self.mapping_repo.add_scope(mapping_scope)
        await self.mapping_repo.add_results(
            scope_id=mapping_scope.id,
            results=mapping_results,
        )
        await self.mapping_repo.attach_rules(
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
