"""Canonical normalizer issue read endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.canonical.application.use_cases.get_canonical_issues import (
    GetCanonicalIssuesQuery,
    GetCanonicalIssuesUseCase,
)
from app.modules.canonical.di.dependencies import get_canonical_issues_use_case
from app.modules.canonical.http.schemas import CanonicalIssueResponse

router = APIRouter(tags=["canonical"])


@router.get(
    "/snapshots/{snapshot_id}/issues",
    response_model=list[CanonicalIssueResponse],
    summary="List snapshot normalizer issues",
    description=(
        "Returns issues recorded while materializing the canonical snapshot "
        "(warnings, unresolved references, parse anomalies). Issue codes are "
        "stable for UI filtering. Returns 404 when the snapshot does not exist."
    ),
)
async def get_snapshot_issues(
    snapshot_id: UUID,
    use_case: GetCanonicalIssuesUseCase = Depends(get_canonical_issues_use_case),
) -> list[CanonicalIssueResponse]:
    result = await use_case.execute(
        GetCanonicalIssuesQuery(canonical_snapshot_id=snapshot_id)
    )
    return [
        CanonicalIssueResponse.model_validate(issue, from_attributes=True)
        for issue in result.issues
    ]
