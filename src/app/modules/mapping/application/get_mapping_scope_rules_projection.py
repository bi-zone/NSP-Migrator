from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.mapping.application.dto import (
    CanonicalEntityDisplayDTO,
    CanonicalRuleDisplayDTO,
    CanonicalToSdwanEntityProjectionDTO,
    MappedSdwanEntityDisplayDTO,
    MappingCanonicalRuleProjectionDTO,
    MappingScopeRuleDisplayDTO,
    MappingScopeRulesProjectionDTO,
)
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
)
from app.modules.mapping.domain.enums import (
    MappedRuleStatus,
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleOperandRole,
)
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
    MappingModuleNotFoundError,
)
from app.modules.mapping.ports.canonical_reader.port import CanonicalReaderPort
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalRuleOperandRole,
    CanonicalScopeEntities,
    CanonicalService,
    CanonicalServiceKind,
    CanonicalZone,
)
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort
from app.modules.mapping.services.mapping_rules.canonical_addr_objs_index import (
    CanonicalAddrGroupMember,
    CanonicalAddrObjectIndex,
)
from app.modules.mapping.services.mapping_rules.canonical_services_index import (
    CanonicalServiceGroupMember,
    CanonicalServiceIndex,
)
from app.modules.mapping.services.mapping_rules.canonical_zones_index import (
    CanonicalZoneIndex,
)
from app.modules.mapping.services.mapping_rules.mapping_results_index import (
    MappingResultsIndex,
)
from app.modules.mapping.services.mapping_rules.sdwan_full_catalog_index import (
    SdwanEntityDTO,
    SdwanFullCatalogIndex,
)


@dataclass(frozen=True, slots=True)
class GetMappingScopeRulesProjectionQuery:
    """
    Query for building mapping scope rules projection.

    Attributes:
        mapping_scope_id:
            Mapping scope id whose canonical rules, mapped rules, mapping
            results, and SD-WAN display values should be collected into a
            UI-oriented projection.
    """

    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class GetMappingScopeRulesProjectionResult:
    """
    Result of GetMappingScopeRulesProjectionUseCase.

    Attributes:
        projection:
            Fully assembled projection for displaying canonical rules,
            mapped SD-WAN rule rows, and per-rule details.
    """

    projection: MappingScopeRulesProjectionDTO


class GetMappingScopeRulesProjectionUseCase:
    """
    Build UI-oriented projection of canonical rules and mapped scope rules.

    This use case is an application-layer orchestrator. It does not build the
    projection itself. Instead, it loads all required data from repositories,
    external gateways, and canonical snapshot reader, then delegates pure
    transformation logic to _MappingScopeRulesProjectionBuilder.

    Data flow:

        MappingScope
          ├─ MappingScopeRule[]
          └─ mapping_scope.canonical_snapshot_id

        MappingEntityResult[]
          └─ current mapping results for zones, address objects, and services

        CanonicalReader
          ├─ CanonicalRule[]
          └─ CanonicalScopeEntities
               ├─ zones
               ├─ address objects
               └─ services

        SD-WAN gateway
          └─ full SD-WAN catalog for display values

    Output:

        MappingScopeRulesProjectionDTO
          ├─ canonical_rules
          │    Short canonical rule rows.
          ├─ mapped_rules
          │    Short mapped SD-WAN rule rows.
          └─ details_by_rule_id
               Detailed canonical-to-SD-WAN rows for each mapping rule.

    Important distinction:

    - canonical_rules shows what was found in canonical source;
    - mapped_rules shows what the current SD-WAN mapping looks like;
    - details_by_rule_id connects every canonical operand to its SD-WAN match.
    """

    def __init__(
        self,
        uow: MappingUnitOfWorkPort,
        sdwan_gateway: MappingSDWANGatewayPort,
        canonical_reader: CanonicalReaderPort,
    ) -> None:
        self.uow = uow
        self.sdwan_gateway = sdwan_gateway
        self.canonical_reader = canonical_reader

    @async_transactional(read_only=True)
    async def execute(
        self,
        query: GetMappingScopeRulesProjectionQuery,
    ) -> GetMappingScopeRulesProjectionResult:
        """
        Load mapping scope data and build rules projection.

        Steps:

        1. Load MappingScope with its MappingScopeRule rows.
        2. Load MappingEntityResult rows for the same scope.
        3. Load canonical rules and canonical entities from the scope snapshot.
        4. Load full SD-WAN catalog for human-readable mapped values.
        5. Build UI projection through _MappingScopeRulesProjectionBuilder.

        Raises:
            MappingModuleNotFoundError:
                If mapping scope does not exist.
            MappingModuleDomainValidationError:
                If loaded data is structurally inconsistent.
        """

        mapping_scope: MappingScope | None = (
            await self.uow.mapping_scope_repo.get_scope_by_id(
                scope_id=query.mapping_scope_id,
                with_rules=True,
            )
        )
        if mapping_scope is None:
            raise MappingModuleNotFoundError(
                f"Mapping scope {query.mapping_scope_id} not found"
            )

        mapping_results: list[MappingEntityResult] = (
            await self.uow.mapping_result_repo.list_by_scope(
                scope_id=mapping_scope.id,
                with_candidates=True,
            )
        )

        if mapping_scope.rules is None:
            raise MappingModuleNotFoundError(
                f"Rules not provided for mapping scope {query.mapping_scope_id}"
            )

        mapping_rules: list[MappingScopeRule] = mapping_scope.rules
        canonical_rule_ids: list[UUID] = [
            rule.canonical_rule_id for rule in mapping_rules
        ]

        canonical_rules: list[CanonicalRule] = (
            await self.canonical_reader.get_canonical_scope_rules(
                canonical_snapshot_id=mapping_scope.canonical_snapshot_id,
                canonical_rules_ids=canonical_rule_ids,
            )
        )
        canonical_scope_entities: CanonicalScopeEntities = (
            await self.canonical_reader.get_canonical_scope_entities_data(
                canonical_snapshot_id=mapping_scope.canonical_snapshot_id,
                canonical_rules_ids=canonical_rule_ids,
            )
        )

        sdwan_full_catalog: SdwanFullCatalog = (
            await self.sdwan_gateway.get_sdwan_full_catalog()
        )

        projection = _MappingScopeRulesProjectionBuilder(
            mapping_scope=mapping_scope,
            canonical_rules=canonical_rules,
            canonical_scope_entities=canonical_scope_entities,
            mapping_rules=mapping_rules,
            mapping_results=mapping_results,
            sdwan_full_catalog=sdwan_full_catalog,
        ).build()

        return GetMappingScopeRulesProjectionResult(projection=projection)


class _MappingScopeRulesProjectionBuilder:
    """
    Build MappingScopeRulesProjectionDTO from already loaded domain data.

    This class is intentionally private: it is not an application use case,
    repository, or domain service. It is a projection builder that converts
    domain/canonical/SD-WAN objects into DTOs convenient for UI.

    The builder joins several independent models:

    1. Canonical model:
       - CanonicalRule
       - CanonicalRuleOperand
       - CanonicalZone
       - CanonicalAddrObject
       - CanonicalService

    2. Mapping model:
       - MappingScopeRule
       - MappingEntityResult

    3. SD-WAN catalog:
       - SD-WAN zones, address objects, services, and other display entities

    Conceptual output per rule:

        Canonical rule row
            src zones / dst zones / src objects / dst objects / services

        Mapped rule row
            selected SD-WAN entities and aggregated mapped status

        Rule details
            Canonical entity -> selected SD-WAN entity
            Canonical entity -> unresolved / ambiguous / matched status

    Group behavior:

        Canonical operand may point to either a leaf object or a group.

        Address object example:

            Group A
              Host 1
              Group B
                Host 2

        In canonical rule row:
            Group A

        In rule details:
            Group A, parent=None, sdwan=None
            Host 1,  parent=Group A, sdwan=<mapping result>
            Group B, parent=Group A, sdwan=None
            Host 2,  parent=Group B, sdwan=<mapping result>

        Groups are shown as canonical hierarchy nodes, but only leaf entities
        are mapped to concrete SD-WAN entities.
    """

    def __init__(
        self,
        *,
        mapping_scope: MappingScope,
        canonical_rules: list[CanonicalRule],
        canonical_scope_entities: CanonicalScopeEntities,
        mapping_rules: list[MappingScopeRule],
        mapping_results: list[MappingEntityResult],
        sdwan_full_catalog: SdwanFullCatalog,
    ) -> None:
        """
        Prepare lookup indexes used while building projection.

        Indexes make the actual build step mostly declarative:

        - canonical_rules_by_id finds canonical rule by MappingScopeRule link;
        - zones_index resolves canonical zone ids;
        - addr_index resolves and expands address object groups;
        - service_index resolves and expands service groups;
        - results_index finds mapping result by canonical entity id and type;
        - sdwan_index converts selected SD-WAN ids into display DTOs.
        """

        self.mapping_scope = mapping_scope
        self.canonical_rules_by_id: dict[UUID, CanonicalRule] = {
            rule.id: rule for rule in canonical_rules
        }
        self.mapping_rules = mapping_rules
        self.mapping_results = mapping_results
        self.mapping_results_by_id: dict[UUID, MappingEntityResult] = {
            result.id: result for result in mapping_results
        }

        self.zones_index = CanonicalZoneIndex(canonical_scope_entities.zones)
        self.addr_index = CanonicalAddrObjectIndex(
            canonical_scope_entities.addr_objects
        )
        self.service_index = CanonicalServiceIndex(canonical_scope_entities.services)
        self.results_index = MappingResultsIndex(mapping_results)
        self.sdwan_index = SdwanFullCatalogIndex(sdwan_full_catalog)

    def build(self) -> MappingScopeRulesProjectionDTO:
        """
        Build full projection for all rules in the mapping scope.

        For every MappingScopeRule this method builds three connected views:

        1. canonical_rule_rows
           Compact canonical rule representation.

        2. mapped_rule_rows
           Compact mapped rule representation with selected SD-WAN entities.

        3. details_by_rule_id
           Detailed per-role, per-entity canonical-to-SD-WAN mapping.

        details_by_rule_id is keyed by MappingScopeRule.id, because details
        belong to the mapping rule row shown in the current mapping scope.
        """

        canonical_rule_rows: list[CanonicalRuleDisplayDTO] = []
        mapped_rule_rows: list[MappingScopeRuleDisplayDTO] = []
        details_by_rule_id: dict[UUID, MappingCanonicalRuleProjectionDTO] = {}

        for mapping_rule in self.mapping_rules:
            canonical_rule = self._get_canonical_rule(mapping_rule.canonical_rule_id)
            details = self._build_rule_details(
                mapping_rule=mapping_rule,
                canonical_rule=canonical_rule,
            )

            canonical_rule_rows.append(
                self._build_canonical_rule_row(canonical_rule=canonical_rule)
            )
            mapped_rule_rows.append(
                self._build_mapped_rule_row(
                    mapping_rule=mapping_rule,
                    details=details,
                )
            )
            details_by_rule_id[mapping_rule.id] = details

        return MappingScopeRulesProjectionDTO(
            mapping_scope_id=self.mapping_scope.id,
            canonical_snapshot_id=self.mapping_scope.canonical_snapshot_id,
            sdwan_target_id=self.mapping_scope.sdwan_target_id,
            canonical_rules=canonical_rule_rows,
            mapped_rules=mapped_rule_rows,
            details_by_rule_id=details_by_rule_id,
        )

    def _get_canonical_rule(self, canonical_rule_id: UUID) -> CanonicalRule:
        """
        Return canonical rule by id.

        Raises:
            MappingModuleNotFoundError:
                If MappingScopeRule references canonical rule that was not
                returned by CanonicalReader.
        """

        canonical_rule = self.canonical_rules_by_id.get(canonical_rule_id)
        if canonical_rule is None:
            raise MappingModuleNotFoundError(
                f"Canonical rule {canonical_rule_id} not found for mapping projection"
            )
        return canonical_rule

    def _build_rule_details(
        self,
        *,
        mapping_rule: MappingScopeRule,
        canonical_rule: CanonicalRule,
    ) -> MappingCanonicalRuleProjectionDTO:
        """
        Build detailed canonical-to-SD-WAN projection for one rule.

        A rule is split into five UI roles:

        - source zones;
        - destination zones;
        - source address objects;
        - destination address objects;
        - services.

        Each role is built independently because canonical operand roles and
        mapping rule operand roles use different enums.

        After all role projections are built, the rule status is aggregated
        from all SD-WAN mapping statuses.
        """

        src_zones = self._build_role_projection(
            canonical_rule=canonical_rule,
            mapping_rule=mapping_rule,
            canonical_role=CanonicalRuleOperandRole.SRC_ZONE,
            mapped_role=MappingScopeRuleOperandRole.SRC_ZONE,
        )
        dst_zones = self._build_role_projection(
            canonical_rule=canonical_rule,
            mapping_rule=mapping_rule,
            canonical_role=CanonicalRuleOperandRole.DST_ZONE,
            mapped_role=MappingScopeRuleOperandRole.DST_ZONE,
        )
        src_addr_objects = self._build_role_projection(
            canonical_rule=canonical_rule,
            mapping_rule=mapping_rule,
            canonical_role=CanonicalRuleOperandRole.SRC_OBJECT,
            mapped_role=MappingScopeRuleOperandRole.SRC_ADDR_OBJECT,
        )
        dst_addr_objects = self._build_role_projection(
            canonical_rule=canonical_rule,
            mapping_rule=mapping_rule,
            canonical_role=CanonicalRuleOperandRole.DST_OBJECT,
            mapped_role=MappingScopeRuleOperandRole.DST_ADDR_OBJECT,
        )
        services = self._build_role_projection(
            canonical_rule=canonical_rule,
            mapping_rule=mapping_rule,
            canonical_role=CanonicalRuleOperandRole.SERVICE,
            mapped_role=MappingScopeRuleOperandRole.SERVICE,
        )

        status = self._aggregate_rule_status_by_roles(
            src_zones=src_zones,
            dst_zones=dst_zones,
            src_addr_objects=src_addr_objects,
            dst_addr_objects=dst_addr_objects,
            services=services,
        )

        return MappingCanonicalRuleProjectionDTO(
            mapping_scope_rule_id=mapping_rule.id,
            canonical_rule_id=canonical_rule.id,
            name=mapping_rule.name,
            action=mapping_rule.action,
            status=status,
            src_zones=src_zones,
            dst_zones=dst_zones,
            src_addr_objects=src_addr_objects,
            dst_addr_objects=dst_addr_objects,
            services=services,
        )

    def _build_role_projection(
        self,
        *,
        canonical_rule: CanonicalRule,
        mapping_rule: MappingScopeRule,
        canonical_role: CanonicalRuleOperandRole,
        mapped_role: MappingScopeRuleOperandRole,
    ) -> list[CanonicalToSdwanEntityProjectionDTO]:
        """
        Build projection rows for one logical rule role.

        The final list may contain two kinds of rows:

        1. Rows created from canonical operands.
           These represent entities from the canonical snapshot and their
           current SD-WAN mapping result.

        2. Rows created from manual mapping rule operands.
           These represent SD-WAN entities selected directly by an operator
           when there is no canonical counterpart.

        Example for zones:

            canonical src zone: Branch-LAN -> SD-WAN zone: vpn10
            manual src zone:   None       -> SD-WAN zone: vpn20
        """

        rows: list[CanonicalToSdwanEntityProjectionDTO] = []

        for operand in canonical_rule.operands:
            if operand.role != canonical_role:
                continue
            rows.extend(self._build_canonical_operand_projection(operand))

        rows.extend(
            self._build_manual_operand_projection(
                mapping_rule=mapping_rule,
                mapped_role=mapped_role,
            )
        )

        return rows

    def _build_canonical_operand_projection(
        self,
        operand: CanonicalRuleOperand,
    ) -> list[CanonicalToSdwanEntityProjectionDTO]:
        """
        Dispatch canonical operand projection by operand role.

        Zone operands are projected as single rows.

        Address and service operands may produce multiple rows if the operand
        points to a group, because groups are expanded into hierarchy members
        for detailed UI display.
        """

        match operand.role:
            case CanonicalRuleOperandRole.SRC_ZONE | CanonicalRuleOperandRole.DST_ZONE:
                return self._build_zone_operand_projection(operand)

            case (
                CanonicalRuleOperandRole.SRC_OBJECT
                | CanonicalRuleOperandRole.DST_OBJECT
            ):
                return self._build_addr_operand_projection(operand)

            case CanonicalRuleOperandRole.SERVICE:
                return self._build_service_operand_projection(operand)

            case _:
                raise MappingModuleDomainValidationError(
                    f"Unsupported canonical operand role: {operand.role}"
                )

    def _build_zone_operand_projection(
        self,
        operand: CanonicalRuleOperand,
    ) -> list[CanonicalToSdwanEntityProjectionDTO]:
        """
        Build projection for a canonical zone operand.

        Zone operands always point to target_zone_id and always produce one
        canonical-to-SD-WAN row.

        Missing mapping result is represented as unresolved SD-WAN display row.
        """

        if operand.target_zone_id is None:
            raise MappingModuleDomainValidationError(
                f"Zone operand {operand.id} has no target_zone_id"
            )

        zone = self.zones_index.get(operand.target_zone_id)
        mapping_result = self.results_index.get(
            entity_type=MappingEntityType.ZONE,
            canonical_entity_id=zone.id,
        )

        return [
            CanonicalToSdwanEntityProjectionDTO(
                canonical=self._canonical_zone_display(zone),
                sdwan=self._sdwan_result_display(mapping_result),
            )
        ]

    def _build_addr_operand_projection(
        self,
        operand: CanonicalRuleOperand,
    ) -> list[CanonicalToSdwanEntityProjectionDTO]:
        """
        Build projection for a canonical address object operand.

        If operand points to a leaf address object, one row is returned.

        If operand points to an address group, the group is expanded into
        flat hierarchy rows:

            Group A
              Host 1
              Group B
                Host 2

        Result rows:

            Group A -> sdwan=None
            Host 1  -> sdwan=<mapping result>
            Group B -> sdwan=None
            Host 2  -> sdwan=<mapping result>

        Group rows do not have SD-WAN mapping result because mapping is applied
        to effective leaf address objects.
        """

        if operand.target_object_id is None:
            raise MappingModuleDomainValidationError(
                f"Address object operand {operand.id} has no target_object_id"
            )

        addr_obj = self.addr_index.get(operand.target_object_id)
        if addr_obj.kind != CanonicalAddrObjKind.ADDR_GROUP:
            return [self._build_addr_object_projection(addr_obj, parent_id=None)]

        rows: list[CanonicalToSdwanEntityProjectionDTO] = []
        for member in self.addr_index.resolve_group_members(addr_obj.id):
            rows.append(self._build_addr_group_member_projection(member))
        return rows

    def _build_service_operand_projection(
        self,
        operand: CanonicalRuleOperand,
    ) -> list[CanonicalToSdwanEntityProjectionDTO]:
        """
        Build projection for a canonical service operand.

        If operand points to a leaf service, one row is returned.

        If operand points to a service group, the group is expanded into flat
        hierarchy rows:

            Group A
              HTTP
              Group B
                HTTPS

        Result rows:

            Group A -> sdwan=None
            HTTP    -> sdwan=<mapping result>
            Group B -> sdwan=None
            HTTPS   -> sdwan=<mapping result>

        Group rows do not have SD-WAN mapping result because mapping is applied
        to effective leaf services.
        """

        if operand.target_object_id is None:
            raise MappingModuleDomainValidationError(
                f"Service operand {operand.id} has no target_object_id"
            )

        service = self.service_index.get(operand.target_object_id)
        if service.kind != CanonicalServiceKind.SERVICE_GROUP:
            return [self._build_service_projection(service, parent_id=None)]

        rows: list[CanonicalToSdwanEntityProjectionDTO] = []
        for member in self.service_index.resolve_group_members(service.id):
            rows.append(self._build_service_group_member_projection(member))
        return rows

    def _build_addr_group_member_projection(
        self,
        member: CanonicalAddrGroupMember,
    ) -> CanonicalToSdwanEntityProjectionDTO:
        """Build projection row for one expanded address group member."""

        return self._build_addr_object_projection(
            member.obj, parent_id=member.parent_id
        )

    def _build_addr_object_projection(
        self,
        addr_obj: CanonicalAddrObject,
        *,
        parent_id: UUID | None,
    ) -> CanonicalToSdwanEntityProjectionDTO:
        """
        Build projection row for one canonical address object.

        Address groups are returned as canonical-only rows.

        Non-group address objects are joined with MappingEntityResult using:

            entity_type = MappingEntityType.ADDR
            canonical_entity_id = addr_obj.id
        """

        canonical = self._canonical_addr_display(addr_obj, parent_id=parent_id)

        if addr_obj.kind == CanonicalAddrObjKind.ADDR_GROUP:
            return CanonicalToSdwanEntityProjectionDTO(canonical=canonical, sdwan=None)

        mapping_result = self.results_index.get(
            entity_type=MappingEntityType.ADDR,
            canonical_entity_id=addr_obj.id,
        )
        return CanonicalToSdwanEntityProjectionDTO(
            canonical=canonical,
            sdwan=self._sdwan_result_display(mapping_result),
        )

    def _build_service_group_member_projection(
        self,
        member: CanonicalServiceGroupMember,
    ) -> CanonicalToSdwanEntityProjectionDTO:
        """Build projection row for one expanded service group member."""

        return self._build_service_projection(member.obj, parent_id=member.parent_id)

    def _build_service_projection(
        self,
        service: CanonicalService,
        *,
        parent_id: UUID | None,
    ) -> CanonicalToSdwanEntityProjectionDTO:
        """
        Build projection row for one canonical service.

        Service groups are returned as canonical-only rows.

        Non-group services are joined with MappingEntityResult using:

            entity_type = MappingEntityType.SERVICE
            canonical_entity_id = service.id
        """

        canonical = self._canonical_service_display(service, parent_id=parent_id)

        if service.kind == CanonicalServiceKind.SERVICE_GROUP:
            return CanonicalToSdwanEntityProjectionDTO(canonical=canonical, sdwan=None)

        mapping_result = self.results_index.get(
            entity_type=MappingEntityType.SERVICE,
            canonical_entity_id=service.id,
        )
        return CanonicalToSdwanEntityProjectionDTO(
            canonical=canonical,
            sdwan=self._sdwan_result_display(mapping_result),
        )

    def _build_manual_operand_projection(
        self,
        *,
        mapping_rule: MappingScopeRule,
        mapped_role: MappingScopeRuleOperandRole,
    ) -> list[CanonicalToSdwanEntityProjectionDTO]:
        """
        Build projection rows for manually added mapping operands.

        Manual operands are values selected directly on MappingScopeRule and
        not derived from canonical rule operands.

        Current intended use case:

            Canonical rule has no source or destination zone,
            but SD-WAN policy requires explicit source and destination zones.
            Operator manually assigns SD-WAN zone.
            Projection should show:

                canonical=None -> sdwan=<manually selected zone>

        Only mapping results without canonical entity links are treated as
        manual-only rows.

        Mapping result is considered manual-only when:

            result.canonical_zone_id is None
            result.canonical_object_id is None
        """

        rows: list[CanonicalToSdwanEntityProjectionDTO] = []

        for operand in mapping_rule.operands or []:
            if operand.role != mapped_role:
                continue

            mapping_result = self.mapping_results_by_id.get(
                operand.mapping_entity_result_id
            )
            if mapping_result is None:
                continue

            if not self._is_manual_result_without_canonical(mapping_result):
                continue

            rows.append(
                CanonicalToSdwanEntityProjectionDTO(
                    canonical=None,
                    sdwan=self._sdwan_result_display(mapping_result),
                )
            )

        return rows

    @staticmethod
    def _is_manual_result_without_canonical(result: MappingEntityResult) -> bool:
        """
        Return True if mapping result was not produced from canonical entity.

        Such result can still be attached to a MappingScopeRule operand and
        displayed as a manual SD-WAN-only selection.
        """

        return result.canonical_zone_id is None and result.canonical_object_id is None

    def _sdwan_result_display(
        self,
        mapping_result: MappingEntityResult | None,
    ) -> MappedSdwanEntityDisplayDTO | None:
        """
        Convert MappingEntityResult into SD-WAN display DTO.

        Behavior by mapping result state:

        1. mapping_result is None
           Entity has no mapping result yet.
           Return unresolved display row.

        2. result_status is not MATCHED
           Entity has a result, but no selected SD-WAN entity should be shown.
           Return status and selection method only.

        3. result_status is MATCHED
           Entity must have selected_sdwan_entity_id.
           Resolve selected SD-WAN entity in catalog and return display values.

        Raises:
            MappingModuleDomainValidationError:
                If result is MATCHED but selected_sdwan_entity_id is missing.
        """

        if mapping_result is None:
            return MappedSdwanEntityDisplayDTO(
                mapping_result_id=None,
                match_status=MappingResultStatus.UNRESOLVED,
                selection_method=None,
                sdwan_id=None,
                name=None,
                type=None,
                str_value=None,
            )

        if mapping_result.result_status != MappingResultStatus.MATCHED:
            return MappedSdwanEntityDisplayDTO(
                mapping_result_id=mapping_result.id,
                match_status=mapping_result.result_status,
                selection_method=mapping_result.selection_method,
                sdwan_id=None,
                name=None,
                type=None,
                str_value=None,
            )

        if mapping_result.selected_sdwan_entity_id is None:
            raise MappingModuleDomainValidationError(
                "Matched mapping result must have selected SD-WAN entity id: "
                f"{mapping_result.id}"
            )

        sdwan_display: SdwanEntityDTO = self.sdwan_index.get_display_entity(
            entity_type=mapping_result.entity_type,
            sdwan_entity_id=mapping_result.selected_sdwan_entity_id,
        )
        return MappedSdwanEntityDisplayDTO(
            mapping_result_id=mapping_result.id,
            match_status=mapping_result.result_status,
            selection_method=mapping_result.selection_method,
            sdwan_id=sdwan_display.sdwan_id,
            name=sdwan_display.name,
            type=sdwan_display.type,
            str_value=sdwan_display.str_value,
        )

    def _build_canonical_rule_row(
        self,
        *,
        canonical_rule: CanonicalRule,
    ) -> CanonicalRuleDisplayDTO:
        """
        Build compact canonical rule row.

        This row intentionally does not expand groups. It mirrors the canonical
        rule as it was originally parsed:

            Group A
            HTTP
            Branch-LAN

        Detailed group expansion happens only in _build_rule_details().
        """

        role_entities: dict[
            CanonicalRuleOperandRole, list[CanonicalEntityDisplayDTO]
        ] = defaultdict(list)

        for operand in canonical_rule.operands:
            role_entities[operand.role].extend(
                self._canonical_operand_summary_entities(operand)
            )

        return CanonicalRuleDisplayDTO(
            canonical_rule_id=canonical_rule.id,
            name=canonical_rule.name,
            action=canonical_rule.action,
            src_zones=role_entities[CanonicalRuleOperandRole.SRC_ZONE],
            dst_zones=role_entities[CanonicalRuleOperandRole.DST_ZONE],
            src_addr_objects=role_entities[CanonicalRuleOperandRole.SRC_OBJECT],
            dst_addr_objects=role_entities[CanonicalRuleOperandRole.DST_OBJECT],
            services=role_entities[CanonicalRuleOperandRole.SERVICE],
        )

    def _canonical_operand_summary_entities(
        self,
        operand: CanonicalRuleOperand,
    ) -> list[CanonicalEntityDisplayDTO]:
        """
        Convert one canonical operand into compact canonical display entities.

        Used only for the canonical rule row, not for detailed mapping rows.

        Important:
            Address and service groups are not expanded here. The UI summary
            should show the operand itself, while details show expanded members.
        """

        if operand.role in (
            CanonicalRuleOperandRole.SRC_ZONE,
            CanonicalRuleOperandRole.DST_ZONE,
        ):
            if operand.target_zone_id is None:
                return []
            return [
                self._canonical_zone_display(
                    self.zones_index.get(operand.target_zone_id)
                )
            ]

        if operand.role in (
            CanonicalRuleOperandRole.SRC_OBJECT,
            CanonicalRuleOperandRole.DST_OBJECT,
        ):
            if operand.target_object_id is None:
                return []
            return [
                self._canonical_addr_display(
                    self.addr_index.get(operand.target_object_id),
                    parent_id=None,
                )
            ]

        if operand.role == CanonicalRuleOperandRole.SERVICE:
            if operand.target_object_id is None:
                return []
            return [
                self._canonical_service_display(
                    self.service_index.get(operand.target_object_id),
                    parent_id=None,
                )
            ]

        raise MappingModuleDomainValidationError(
            f"Unsupported canonical operand role: {operand.role}"
        )

    def _build_mapped_rule_row(
        self,
        *,
        mapping_rule: MappingScopeRule,
        details: MappingCanonicalRuleProjectionDTO,
    ) -> MappingScopeRuleDisplayDTO:
        """
        Build compact mapped rule row from already built details.

        This method does not recalculate mapping. It extracts SD-WAN display
        entities from detailed role projections and reuses aggregated status.

        This keeps summary row and details consistent.
        """

        return MappingScopeRuleDisplayDTO(
            mapping_scope_rule_id=mapping_rule.id,
            canonical_rule_id=mapping_rule.canonical_rule_id,
            name=mapping_rule.name,
            action=mapping_rule.action,
            status=details.status,
            src_zones=self._extract_sdwan_entities(details.src_zones),
            dst_zones=self._extract_sdwan_entities(details.dst_zones),
            src_addr_objects=self._extract_sdwan_entities(details.src_addr_objects),
            dst_addr_objects=self._extract_sdwan_entities(details.dst_addr_objects),
            services=self._extract_sdwan_entities(details.services),
        )

    @staticmethod
    def _extract_sdwan_entities(
        rows: list[CanonicalToSdwanEntityProjectionDTO],
    ) -> list[MappedSdwanEntityDisplayDTO]:
        """
        Extract SD-WAN side from canonical-to-SD-WAN projection rows.

        Canonical-only group rows have sdwan=None and are skipped.
        """

        return [row.sdwan for row in rows if row.sdwan is not None]

    @classmethod
    def _aggregate_rule_status_by_roles(
        cls,
        *,
        src_zones: list[CanonicalToSdwanEntityProjectionDTO],
        dst_zones: list[CanonicalToSdwanEntityProjectionDTO],
        src_addr_objects: list[CanonicalToSdwanEntityProjectionDTO],
        dst_addr_objects: list[CanonicalToSdwanEntityProjectionDTO],
        services: list[CanonicalToSdwanEntityProjectionDTO],
    ) -> MappedRuleStatus:
        """
        Aggregate final mapped rule status from all role projections.

        Status is calculated from SD-WAN mapping statuses of all projected
        entities. Canonical-only group rows do not affect status because they
        have no SD-WAN side.

        Additional SD-WAN policy requirement:

            A mapped SD-WAN rule must have at least one selected source zone
            and at least one selected destination zone.

        Therefore, missing selected SRC or DST zone adds an artificial
        UNRESOLVED status even if canonical rule has no zone operands.
        """

        statuses: list[MappingResultStatus] = cls._extract_mapping_statuses(
            src_zones + dst_zones + src_addr_objects + dst_addr_objects + services
        )

        if not cls._has_selected_sdwan_entity(src_zones):
            statuses.append(MappingResultStatus.UNRESOLVED)

        if not cls._has_selected_sdwan_entity(dst_zones):
            statuses.append(MappingResultStatus.UNRESOLVED)

        return cls._aggregate_mapping_statuses(statuses)

    @staticmethod
    def _extract_mapping_statuses(
        rows: list[CanonicalToSdwanEntityProjectionDTO],
    ) -> list[MappingResultStatus]:
        """
        Extract mapping statuses from projection rows that have SD-WAN side.

        Rows without SD-WAN side are usually canonical group nodes and should
        not directly participate in status aggregation.
        """

        return [
            row.sdwan.match_status
            for row in rows
            if row.sdwan is not None and row.sdwan.match_status is not None
        ]

    @staticmethod
    def _has_selected_sdwan_entity(
        rows: list[CanonicalToSdwanEntityProjectionDTO],
    ) -> bool:
        """
        Return True if role has at least one matched SD-WAN entity.

        Used for mandatory source and destination zone checks.
        """

        return any(
            row.sdwan is not None
            and row.sdwan.match_status == MappingResultStatus.MATCHED
            and row.sdwan.sdwan_id is not None
            for row in rows
        )

    @staticmethod
    def _aggregate_mapping_statuses(
        statuses: list[MappingResultStatus],
    ) -> MappedRuleStatus:
        """
        Convert entity-level mapping statuses into rule-level status.

        Rules:

        - no statuses:
            UNRESOLVED

        - all statuses are MATCHED:
            MAPPED

        - at least one UNRESOLVED:
            PARTIAL if something else is matched or ambiguous,
            otherwise UNRESOLVED

        - no unresolved, but at least one AMBIGUOUS:
            AMBIGUOUS

        - fallback:
            PARTIAL
        """

        if not statuses:
            return MappedRuleStatus.UNRESOLVED

        matched_count = statuses.count(MappingResultStatus.MATCHED)
        unresolved_count = statuses.count(MappingResultStatus.UNRESOLVED)
        ambiguous_count = statuses.count(MappingResultStatus.AMBIGUOUS)

        if matched_count == len(statuses):
            return MappedRuleStatus.MAPPED

        if unresolved_count > 0:
            return (
                MappedRuleStatus.PARTIAL
                if matched_count > 0 or ambiguous_count > 0
                else MappedRuleStatus.UNRESOLVED
            )

        if ambiguous_count > 0:
            return MappedRuleStatus.AMBIGUOUS

        return MappedRuleStatus.PARTIAL

    @staticmethod
    def _canonical_zone_display(zone: CanonicalZone) -> CanonicalEntityDisplayDTO:
        """Convert canonical zone into display DTO."""

        return CanonicalEntityDisplayDTO(
            canonical_id=zone.id,
            parent_name=None,
            name=zone.name,
            type="zone",
            str_value=zone.zone_key,
        )

    def _canonical_addr_display(
        self,
        obj: CanonicalAddrObject,
        *,
        parent_id: UUID | None,
    ) -> CanonicalEntityDisplayDTO:
        """
        Convert canonical address object into display DTO.

        parent_id is used only for expanded group details. It lets the UI show
        where this object came from inside the group hierarchy.
        """

        parent_name = self._get_addr_parent_name(parent_id)
        return CanonicalEntityDisplayDTO(
            canonical_id=obj.id,
            parent_name=parent_name,
            name=obj.name,
            type=obj.kind.value,
            str_value=self._canonical_addr_str_value(obj),
        )

    def _canonical_service_display(
        self,
        obj: CanonicalService,
        *,
        parent_id: UUID | None,
    ) -> CanonicalEntityDisplayDTO:
        """
        Convert canonical service into display DTO.

        parent_id is used only for expanded group details. It lets the UI show
        where this service came from inside the group hierarchy.
        """

        parent_name = self._get_service_parent_name(parent_id)
        return CanonicalEntityDisplayDTO(
            canonical_id=obj.id,
            parent_name=parent_name,
            name=obj.name,
            type=obj.kind.value,
            str_value=self._canonical_service_str_value(obj),
        )

    def _get_addr_parent_name(self, parent_id: UUID | None) -> str | None:
        """Return address parent name for expanded group member display."""

        if parent_id is None:
            return None
        return self.addr_index.get(parent_id).name

    def _get_service_parent_name(self, parent_id: UUID | None) -> str | None:
        """Return service parent name for expanded group member display."""

        if parent_id is None:
            return None
        return self.service_index.get(parent_id).name

    @classmethod
    def _canonical_addr_str_value(cls, obj: CanonicalAddrObject) -> str | None:
        """
        Build human-readable value for canonical address object.

        Examples:

            HOST / SUBNET / ANY_ADDR:
                cidr

            RANGE:
                range_start-range_end

            FQDN:
                fqdn

            ADDR_GROUP:
                None, because group is a container
        """

        if obj.kind == CanonicalAddrObjKind.ADDR_GROUP:
            return None

        if obj.kind in (
            CanonicalAddrObjKind.HOST,
            CanonicalAddrObjKind.SUBNET,
            CanonicalAddrObjKind.ANY_ADDR,
        ):
            return obj.cidr

        if obj.kind == CanonicalAddrObjKind.RANGE:
            return f"{obj.range_start}-{obj.range_end}"

        if obj.kind == CanonicalAddrObjKind.FQDN:
            return obj.fqdn

        return obj.name

    @classmethod
    def _canonical_service_str_value(cls, obj: CanonicalService) -> str | None:
        """
        Build human-readable value for canonical service.

        Examples:

            SERVICE_GROUP:
                None

            ANY_SERVICE:
                object name

            TCP / UDP with port range:
                tcp/1000-2000

            ICMP:
                icmp/type=8/code=0 (or without code section)

            IP_PROTO:
                protocol or object name
        """

        if obj.kind == CanonicalServiceKind.SERVICE_GROUP:
            return None

        if obj.kind == CanonicalServiceKind.ANY_SERVICE:
            return obj.name

        if obj.kind in (CanonicalServiceKind.TCP, CanonicalServiceKind.UDP):
            return f"{obj.protocol}/{obj.port_from}-{obj.port_to}"

        if obj.kind == CanonicalServiceKind.ICMP:
            proto = obj.protocol or obj.kind.value
            parts = [proto]
            if obj.icmp_type is not None:
                parts.append(f"type={obj.icmp_type}")
            if obj.icmp_code is not None:
                parts.append(f"code={obj.icmp_code}")
            return "/".join(parts)

        if obj.kind == CanonicalServiceKind.IP_PROTO:
            return obj.protocol or obj.name

        if obj.kind == CanonicalServiceKind.UNRESOLVED_SERVICE:
            return obj.protocol or obj.name

        return obj.name
