from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeCommand,
    AssignZoneForScopeResult,
    AssignZoneForScopeUseCase,
)
from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeCommand,
    AutoSelectEntitiesWithCreateForScopeResult,
    AutoSelectEntitiesWithCreateForScopeUseCase,
)
from app.modules.mapping.application.get_sdwan_addr_objects import (
    GetSdwanAddrObjectsResult,
    GetSdwanAddrObjectsUseCase,
)
from app.modules.mapping.application.get_sdwan_services import (
    GetSdwanServicesResult,
    GetSdwanServicesUseCase,
)
from app.modules.mapping.application.get_sdwan_targets import (
    GetSdwanTargetsResult,
    GetSdwanTargetsUseCase,
)
from app.modules.mapping.application.get_sdwan_zones import (
    GetSdwanZonesResult,
    GetSdwanZonesUseCase,
)
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanCommand,
    MapCanonicalToSdwanResult,
    MapCanonicalToSdwanUseCase,
)
from app.modules.mapping.application.select_entity_candidate import (
    SelectEntityCandidateCommand,
    SelectEntityCandidateResult,
    SelectEntityCandidateUseCase,
)
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanCommand,
    SelectEntityWithCreateOnSdwanResult,
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.application.select_sdwan_entity_directly import (
    SelectSdwanEntityDirectlyCommand,
    SelectSdwanEntityDirectlyResult,
    SelectSdwanEntityDirectlyUseCase,
)
from app.modules.mapping.di.dependencies import (
    get_assign_zone_for_scope_use_case,
    get_auto_select_entities_with_create_use_case,
    get_map_canonical_to_sdwan_use_case,
    get_sdwan_addr_objects_use_case_dep,
    get_sdwan_services_use_case_dep,
    get_sdwan_targets_use_case_dep,
    get_sdwan_zones_use_case_dep,
    get_select_entity_candidate_use_case,
    get_select_entity_with_create_on_sdwan_use_case,
    get_select_sdwan_entity_directly_use_case,
)
from app.modules.mapping.domain.enums import SDWANZoneDirection
from app.modules.mapping.http.schemas import (
    AutoSelectWithCreateResponseSchema,
    MapCanonicalRulesResponseSchema,
    MappingEntityResultSchema,
    MappingEntityResultWithCandidatesSchema,
    SdwanAddrObjectsResponseSchema,
    SdwanServiceResponseSchema,
    SdwanTargetResponse,
    SdwanZoneResponseSchema,
)

mapping_router = APIRouter(prefix="/mapping", tags=["mapping"])


@mapping_router.post("/map-canonical-to-sdwan")
async def map_canonical_rules_to_sdwan(
    mapping_scope_title: str = Query(..., description="mapping scope title"),
    sdwan_target_id: str = Query(
        ...,
        description="sdwan target id (dev obj id)",
    ),
    canonical_snapshot_id: UUID = Query(
        ...,
        description="canonical snapshot id",
    ),
    canonical_rules_ids: list[UUID] = Query(
        ...,
        description="canonical rules ids",
    ),
    map_canonical_to_sdwan_use_case: MapCanonicalToSdwanUseCase = Depends(
        get_map_canonical_to_sdwan_use_case
    ),
) -> MapCanonicalRulesResponseSchema:
    """Map canonical to sd-wan"""
    res: MapCanonicalToSdwanResult = await map_canonical_to_sdwan_use_case.execute(
        command=MapCanonicalToSdwanCommand(
            mapping_scope_title=mapping_scope_title,
            canonical_snapshot_id=canonical_snapshot_id,
            canonical_rules_ids=canonical_rules_ids,
            sdwan_target_id=sdwan_target_id,
        )
    )
    return MapCanonicalRulesResponseSchema.model_validate(res)


# TODO: endpoint for mapped rules list view / canonical-mapping projection


@mapping_router.post("/scopes/{mapping_scope_id}/assign-zone")
async def assign_zone_for_rules_of_scope(
    mapping_scope_id: UUID = Path(
        ...,
        description="mapping scope id",
    ),
    zone_sdwan_id: int = Query(..., description="zone sdwan id"),
    zone_direction: SDWANZoneDirection = Query(..., description="zone direction"),
    assign_zone_for_scope_use_case: AssignZoneForScopeUseCase = Depends(
        get_assign_zone_for_scope_use_case
    ),
) -> MappingEntityResultSchema:

    res: AssignZoneForScopeResult = await assign_zone_for_scope_use_case.execute(
        AssignZoneForScopeCommand(
            zone_direction=zone_direction,
            zone_sdwan_id=zone_sdwan_id,
            mapping_scope_id=mapping_scope_id,
        )
    )

    return MappingEntityResultSchema.model_validate(res.mapping_result)


@mapping_router.post("/scopes/{mapping_scope_id}/auto-select-entities-with-create")
async def auto_select_with_create_for_scope(
    mapping_scope_id: UUID = Path(
        ...,
        description="mapping scope id",
    ),
    auto_select_entities_with_create_use_case: AutoSelectEntitiesWithCreateForScopeUseCase = Depends(
        get_auto_select_entities_with_create_use_case
    ),
) -> AutoSelectWithCreateResponseSchema:

    res: AutoSelectEntitiesWithCreateForScopeResult = (
        await auto_select_entities_with_create_use_case.execute(
            command=AutoSelectEntitiesWithCreateForScopeCommand(
                mapping_scope_id=mapping_scope_id
            )
        )
    )

    return AutoSelectWithCreateResponseSchema.model_validate(res)


@mapping_router.post("/mapping-results/{mapping_result_id}/select_candidate")
async def select_candidate(
    mapping_result_id: UUID = Path(..., description="mapping entity result id"),
    candidate_id: UUID = Query(..., description="candidate id"),
    select_entity_candidate_use_case: SelectEntityCandidateUseCase = Depends(
        get_select_entity_candidate_use_case
    ),
) -> MappingEntityResultWithCandidatesSchema:

    res: SelectEntityCandidateResult = await select_entity_candidate_use_case.execute(
        SelectEntityCandidateCommand(
            mapping_entity_result_id=mapping_result_id,
            candidate_id=candidate_id,
        )
    )
    return MappingEntityResultWithCandidatesSchema.model_validate(
        res.mapping_entity_result
    )


@mapping_router.get("/sdwan_zones")
async def get_sdwan_zones(
    get_sdwan_zones_use_case: GetSdwanZonesUseCase = Depends(
        get_sdwan_zones_use_case_dep
    ),
) -> list[SdwanZoneResponseSchema]:
    res: GetSdwanZonesResult = await get_sdwan_zones_use_case.execute()
    return [SdwanZoneResponseSchema.model_validate(z) for z in res.zones]


@mapping_router.get("/sdwan_services")
async def get_sdwan_services(
    get_sdwan_services_use_case: GetSdwanServicesUseCase = Depends(
        get_sdwan_services_use_case_dep
    ),
) -> list[SdwanServiceResponseSchema]:
    res: GetSdwanServicesResult = await get_sdwan_services_use_case.execute()
    return [SdwanServiceResponseSchema.model_validate(s) for s in res.services]


@mapping_router.get("/sdwan_addr_objects")
async def get_sdwan_addr_objects(
    get_sdwan_addr_objects_use_case: GetSdwanAddrObjectsUseCase = Depends(
        get_sdwan_addr_objects_use_case_dep
    ),
) -> SdwanAddrObjectsResponseSchema:
    res: GetSdwanAddrObjectsResult = await get_sdwan_addr_objects_use_case.execute()
    return SdwanAddrObjectsResponseSchema.model_validate(res)


@mapping_router.get("/sdwan_targets")
async def get_sdwan_targets(
    get_sdwan_targets_use_case: GetSdwanTargetsUseCase = Depends(
        get_sdwan_targets_use_case_dep
    ),
) -> list[SdwanTargetResponse]:
    result: GetSdwanTargetsResult = await get_sdwan_targets_use_case.execute()
    return [SdwanTargetResponse.model_validate(t) for t in result.targets]


@mapping_router.post("/mapping-results/{mapping_result_id}/select_sdwan_directly")
async def select_sdwan_entity_for_mapped_directly(
    mapping_result_id: UUID = Path(..., description="mapping entity result id"),
    sdwan_entity_id: int = Query(..., description="sdwan entity id"),
    select_sdwan_entity_directly_use_case: SelectSdwanEntityDirectlyUseCase = Depends(
        get_select_sdwan_entity_directly_use_case
    ),
) -> MappingEntityResultWithCandidatesSchema:

    res: SelectSdwanEntityDirectlyResult = (
        await select_sdwan_entity_directly_use_case.execute(
            SelectSdwanEntityDirectlyCommand(
                mapping_result_id=mapping_result_id,
                sdwan_entity_id=sdwan_entity_id,
            )
        )
    )
    return MappingEntityResultWithCandidatesSchema.model_validate(res.mapping_result)


@mapping_router.post("/mapping-results/{mapping_result_id}/select_with_create_on_sdwan")
async def select_sdwan_entity_with_create_on_sdwan(
    mapping_result_id: UUID = Path(..., description="mapping entity result id"),
    select_entity_with_create_on_sdwan_use_case: SelectEntityWithCreateOnSdwanUseCase = Depends(
        get_select_entity_with_create_on_sdwan_use_case
    ),
) -> MappingEntityResultSchema:

    res: SelectEntityWithCreateOnSdwanResult = (
        await select_entity_with_create_on_sdwan_use_case.execute(
            command=SelectEntityWithCreateOnSdwanCommand(
                mapping_result_id=mapping_result_id,
            )
        )
    )
    return MappingEntityResultSchema.model_validate(res.mapping_result)
