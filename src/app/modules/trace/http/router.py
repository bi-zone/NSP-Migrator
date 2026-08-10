"""Read-only HTTP routes for trace lineage queries."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.trace.application.dto import (
    GetTraceByLineRangeQuery,
    GetTraceForCanonicalSnapshotQuery,
    GetTraceForEntityQuery,
    GetTraceForSourceSnapshotQuery,
)
from app.modules.trace.application.use_cases.get_trace_by_line_range import (
    GetTraceByLineRangeUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_canonical_snapshot import (
    GetTraceForCanonicalSnapshotUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_entity import (
    GetTraceForEntityUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_source_snapshot import (
    GetTraceForSourceSnapshotUseCase,
)
from app.modules.trace.di.dependencies import (
    get_trace_by_line_range_use_case,
    get_trace_for_canonical_snapshot_use_case,
    get_trace_for_entity_use_case,
    get_trace_for_source_snapshot_use_case,
)
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.exceptions import TraceModuleValidationError
from app.modules.trace.http._responses import trace_list_response
from app.modules.trace.http.schemas import TraceListResponse

trace_router = APIRouter(prefix="/trace", tags=["trace"])


@trace_router.get("/raw-to-canonical", response_model=TraceListResponse)
async def list_trace_raw_to_canonical(
    canonical_snapshot_id: UUID | None = Query(default=None),
    source_snapshot_id: UUID | None = Query(default=None),
    canonical_kind: TraceCanonicalKind | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
    by_canonical_use_case: GetTraceForCanonicalSnapshotUseCase = Depends(
        get_trace_for_canonical_snapshot_use_case
    ),
    by_source_use_case: GetTraceForSourceSnapshotUseCase = Depends(
        get_trace_for_source_snapshot_use_case
    ),
) -> TraceListResponse:
    if canonical_snapshot_id is None and source_snapshot_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="either canonical_snapshot_id or source_snapshot_id must be provided",
        )
    if canonical_snapshot_id is not None and source_snapshot_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only one of canonical_snapshot_id / source_snapshot_id is allowed",
        )

    if canonical_snapshot_id is not None:
        rows = await by_canonical_use_case.execute(
            GetTraceForCanonicalSnapshotQuery(
                canonical_snapshot_id=canonical_snapshot_id,
                canonical_kind=canonical_kind,
                limit=limit,
                offset=offset,
            )
        )
    else:
        assert source_snapshot_id is not None
        rows = await by_source_use_case.execute(
            GetTraceForSourceSnapshotQuery(
                source_snapshot_id=source_snapshot_id,
                canonical_kind=canonical_kind,
                limit=limit,
                offset=offset,
            )
        )

    return trace_list_response(rows)


@trace_router.get("/raw-to-canonical/by-entity", response_model=TraceListResponse)
async def list_trace_for_entity(
    canonical_kind: TraceCanonicalKind = Query(...),
    canonical_id: UUID = Query(...),
    use_case: GetTraceForEntityUseCase = Depends(get_trace_for_entity_use_case),
) -> TraceListResponse:
    rows = await use_case.execute(
        GetTraceForEntityQuery(canonical_kind=canonical_kind, canonical_id=canonical_id)
    )
    return trace_list_response(rows)


@trace_router.get("/raw-to-canonical/by-lines", response_model=TraceListResponse)
async def list_trace_by_lines(
    source_snapshot_id: UUID = Query(...),
    line_from: int = Query(..., ge=1),
    line_to: int = Query(..., ge=1),
    use_case: GetTraceByLineRangeUseCase = Depends(get_trace_by_line_range_use_case),
) -> TraceListResponse:
    if line_to < line_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="line_to must be >= line_from",
        )
    try:
        rows = await use_case.execute(
            GetTraceByLineRangeQuery(
                source_snapshot_id=source_snapshot_id,
                line_from=line_from,
                line_to=line_to,
            )
        )
    except TraceModuleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return trace_list_response(rows)
