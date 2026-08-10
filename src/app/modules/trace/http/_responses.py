"""Build trace list HTTP responses with page-size total semantics."""

from __future__ import annotations

from app.modules.trace.application.dto import TraceRecordDTO
from app.modules.trace.http.schemas import TraceListResponse, TraceRecordResponse


def trace_list_response(rows: list[TraceRecordDTO]) -> TraceListResponse:
    """Map DTO rows to API list response.

    Note: total intentionally equals len(items) for the current page.
    """
    items = [TraceRecordResponse.model_validate(r, from_attributes=True) for r in rows]
    return TraceListResponse(items=items, total=len(items))
