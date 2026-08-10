from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog
from app.modules.mapping.application.dto import MappingResultsSummary
from app.modules.mapping.domain.entities import MappingEntityResult
from app.modules.mapping.domain.enums import MappingEntityType, MappingResultStatus
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObjKind,
    CanonicalScopeEntities,
    CanonicalServiceKind,
)
from app.modules.mapping.services.mapping_objects.matchers.addr_objs_matcher import (
    AddrObjectMatcher,
)
from app.modules.mapping.services.mapping_objects.matchers.services_matcher import (
    ServiceMatcher,
)
from app.modules.mapping.services.mapping_objects.matchers.zones_matcher import (
    ZoneMatcher,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.addr_objs_catalog_index import (
    SdwanAddrObjsCatalogIndex,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.services_catalog_index import (
    SdwanServicesCatalogIndex,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.zones_catalog_index import (
    SdwanZonesCatalogIndex,
)


class MappingObjectsService:
    """
    Builds object-level mapping results.

    This is the main service of mapping module.

    It does not:
    - create mapped rules;
    - create mapped rule entity links;
    - persist SD-WAN snapshots;
    - persist SD-WAN names;
    - call repositories.

    It only converts:
        CanonicalScopeEntities + SdwanFullCatalog
    into:
        list[MappingEntityResult]
    """

    @classmethod
    def build_results(
        cls,
        *,
        mapping_scope_id: UUID,
        canonical_scope_entities: CanonicalScopeEntities,
        sdwan_full_catalog: SdwanFullCatalog,
    ) -> list[MappingEntityResult]:
        """
        Build mapping results for zones, address objects and services.

        Result semantics:
        - no candidates -> UNRESOLVED;
        - one candidate -> MATCHED;
        - multiple candidates -> AMBIGUOUS.
        """
        zones_index = SdwanZonesCatalogIndex(sdwan_full_catalog.zones)
        addr_index = SdwanAddrObjsCatalogIndex(sdwan_full_catalog.addr_objs)
        services_index = SdwanServicesCatalogIndex(sdwan_full_catalog.services)

        zone_matcher = ZoneMatcher(zones_index)
        addr_matcher = AddrObjectMatcher(addr_index)
        service_matcher = ServiceMatcher(services_index)

        results: list[MappingEntityResult] = []

        # -- match zones
        for zone in canonical_scope_entities.zones:
            candidates = zone_matcher.match(zone)

            results.append(
                cls._build_result(
                    mapping_scope_id=mapping_scope_id,
                    entity_type=MappingEntityType.ZONE,
                    canonical_entity_id=zone.id,
                    candidates=candidates,
                )
            )

        # -- match addr objects
        for addr_object in canonical_scope_entities.addr_objects:

            # ignore addr groups, work only with flat objects array
            if addr_object.kind == CanonicalAddrObjKind.ADDR_GROUP:
                continue

            candidates = addr_matcher.match(addr_object)

            results.append(
                cls._build_result(
                    mapping_scope_id=mapping_scope_id,
                    entity_type=MappingEntityType.ADDR,
                    canonical_entity_id=addr_object.id,
                    candidates=candidates,
                )
            )

        # -- match services
        for service in canonical_scope_entities.services:

            # ignore addr groups, work only with flat objects array
            if service.kind == CanonicalServiceKind.SERVICE_GROUP:
                continue

            candidates = service_matcher.match(service)

            results.append(
                cls._build_result(
                    mapping_scope_id=mapping_scope_id,
                    entity_type=MappingEntityType.SERVICE,
                    canonical_entity_id=service.id,
                    candidates=candidates,
                )
            )

        return results

    @staticmethod
    def _build_result(
        *,
        mapping_scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
        candidates: list[MappingEntityCandidatePayload],
    ) -> MappingEntityResult:
        """
        Convert candidate list to MappingEntityResult.

        The rule is intentionally simple and visible:
        - 0 candidates => unresolved;
        - 1 candidate  => auto matched;
        - 2+ candidates => ambiguous.
        """
        if not candidates:
            return MappingEntityResult.create_unresolved(
                mapping_scope_id=mapping_scope_id,
                entity_type=entity_type,
                canonical_entity_id=canonical_entity_id,
            )

        if len(candidates) == 1:
            return MappingEntityResult.create_matched_auto(
                mapping_scope_id=mapping_scope_id,
                entity_type=entity_type,
                canonical_entity_id=canonical_entity_id,
                candidate_payload=candidates[0],
            )

        return MappingEntityResult.create_ambiguous(
            mapping_scope_id=mapping_scope_id,
            entity_type=entity_type,
            canonical_entity_id=canonical_entity_id,
            candidates_payloads=candidates,
        )

    # -- extra methods (not required for mapping process)
    @staticmethod
    def build_results_summary(
        results: list[MappingEntityResult],
    ) -> MappingResultsSummary:
        zones = [item for item in results if item.entity_type == MappingEntityType.ZONE]
        addr = [item for item in results if item.entity_type == MappingEntityType.ADDR]
        services = [
            item for item in results if item.entity_type == MappingEntityType.SERVICE
        ]

        def _count_status(
            _results: list[MappingEntityResult],
            status: MappingResultStatus,
        ) -> int:
            return sum(1 for item in _results if item.result_status == status)

        return MappingResultsSummary(
            total_entities=len(results),
            matched_entities=_count_status(
                results,
                MappingResultStatus.MATCHED,
            ),
            ambiguous=_count_status(
                results,
                MappingResultStatus.AMBIGUOUS,
            ),
            unresolved=_count_status(
                results,
                MappingResultStatus.UNRESOLVED,
            ),
            zones_total=len(zones),
            zones_matched=_count_status(
                zones,
                MappingResultStatus.MATCHED,
            ),
            addr_total=len(addr),
            addr_matched=_count_status(
                addr,
                MappingResultStatus.MATCHED,
            ),
            services_total=len(services),
            services_matched=_count_status(
                services,
                MappingResultStatus.MATCHED,
            ),
        )
