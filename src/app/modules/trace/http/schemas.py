from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.trace.domain.enums import TraceCanonicalKind


class TraceRecordResponse(BaseModel):
    id: UUID
    source_snapshot_id: UUID
    canonical_snapshot_id: UUID
    vendor_code: str
    normalizer_code: str
    normalizer_version: str
    source_line_start: int
    source_line_end: int
    source_fragment: str | None
    canonical_kind: TraceCanonicalKind
    canonical_id: UUID
    canonical_role: str | None
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TraceListResponse(BaseModel):
    items: list[TraceRecordResponse]
    total: int
