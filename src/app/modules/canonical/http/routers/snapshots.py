"""Canonical snapshot read endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.canonical.application.use_cases.get_canonical_snapshot import (
    GetCanonicalSnapshotQuery,
    GetCanonicalSnapshotUseCase,
)
from app.modules.canonical.di.dependencies import get_canonical_snapshot_use_case
from app.modules.canonical.http.schemas import CanonicalSnapshotResponse

router = APIRouter(tags=["canonical"])


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=CanonicalSnapshotResponse,
    summary="Get canonical snapshot header",
    description=(
        "Returns snapshot metadata and aggregate counts (zones, objects, rules, issues). "
        "Does not include the full zone/object/rule graph; use dedicated list endpoints "
        "or rule_scope for projections. Returns 404 when the snapshot does not exist."
    ),
)
async def get_snapshot(
    snapshot_id: UUID,
    use_case: GetCanonicalSnapshotUseCase = Depends(get_canonical_snapshot_use_case),
) -> CanonicalSnapshotResponse:
    result = await use_case.execute(
        GetCanonicalSnapshotQuery(canonical_snapshot_id=snapshot_id)
    )
    return CanonicalSnapshotResponse.model_validate(
        result.snapshot, from_attributes=True
    )
