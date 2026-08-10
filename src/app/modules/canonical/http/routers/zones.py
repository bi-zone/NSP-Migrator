"""Canonical zone read endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.canonical.application.use_cases.get_canonical_zone import (
    GetCanonicalZoneQuery,
    GetCanonicalZoneUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zones import (
    GetCanonicalZonesQuery,
    GetCanonicalZonesUseCase,
)
from app.modules.canonical.di.dependencies import (
    get_canonical_zone_use_case,
    get_canonical_zones_use_case,
)
from app.modules.canonical.http.schemas import CanonicalZoneResponse

router = APIRouter(tags=["canonical"])


@router.get(
    "/snapshots/{snapshot_id}/zones",
    response_model=list[CanonicalZoneResponse],
    summary="List snapshot zones",
    description=(
        "Returns all zones for a canonical snapshot. Used by Streamlit and "
        "rule_scope consumers. Returns 404 when the snapshot does not exist."
    ),
)
async def get_snapshot_zones(
    snapshot_id: UUID,
    use_case: GetCanonicalZonesUseCase = Depends(get_canonical_zones_use_case),
) -> list[CanonicalZoneResponse]:
    result = await use_case.execute(
        GetCanonicalZonesQuery(canonical_snapshot_id=snapshot_id)
    )
    return [
        CanonicalZoneResponse.model_validate(zone, from_attributes=True)
        for zone in result.zones
    ]


@router.get(
    "/snapshots/{snapshot_id}/zones/{zone_id}",
    response_model=CanonicalZoneResponse,
    summary="Get snapshot zone by ID",
    description=(
        "Returns a single zone within a canonical snapshot. "
        "Returns 404 when the snapshot or zone does not exist."
    ),
)
async def get_snapshot_zone(
    snapshot_id: UUID,
    zone_id: UUID,
    use_case: GetCanonicalZoneUseCase = Depends(get_canonical_zone_use_case),
) -> CanonicalZoneResponse:
    result = await use_case.execute(
        GetCanonicalZoneQuery(canonical_snapshot_id=snapshot_id, zone_id=zone_id)
    )
    return CanonicalZoneResponse.model_validate(result.zone, from_attributes=True)
