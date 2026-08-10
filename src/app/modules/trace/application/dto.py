from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord


@dataclass(slots=True)
class SaveTraceRecordsCommand:
    """"""

    records: list[TraceRawToCanonicalRecord]


@dataclass(slots=True)
class SaveTraceRecordsResult:
    written: int


@dataclass(slots=True)
class TraceRecordDTO:
    id: UUID
    source_snapshot_id: UUID
    canonical_snapshot_id: UUID
    vendor_code: str
    normalizer_code: str
    normalizer_version: str
    source_line_start: int
    source_line_end: int
    source_fragment: str | None
    canonical_kind: str
    canonical_id: UUID
    canonical_role: str | None
    note: str | None
    created_at: datetime

    @classmethod
    def from_entity(cls, entity: TraceRawToCanonicalRecord) -> TraceRecordDTO:
        return cls(
            id=entity.id,
            source_snapshot_id=entity.source_snapshot_id,
            canonical_snapshot_id=entity.canonical_snapshot_id,
            vendor_code=entity.vendor_code,
            normalizer_code=entity.normalizer_code,
            normalizer_version=entity.normalizer_version,
            source_line_start=entity.source_line_start,
            source_line_end=entity.source_line_end,
            source_fragment=entity.source_fragment,
            canonical_kind=entity.canonical_kind.value,
            canonical_id=entity.canonical_id,
            canonical_role=entity.canonical_role,
            note=entity.note,
            created_at=entity.created_at,
        )


@dataclass(slots=True)
class GetTraceForCanonicalSnapshotQuery:
    canonical_snapshot_id: UUID
    canonical_kind: TraceCanonicalKind | None = None
    limit: int = 1000
    offset: int = 0


@dataclass(slots=True)
class GetTraceForSourceSnapshotQuery:
    source_snapshot_id: UUID
    canonical_kind: TraceCanonicalKind | None = None
    limit: int = 1000
    offset: int = 0


@dataclass(slots=True)
class GetTraceForEntityQuery:
    canonical_kind: TraceCanonicalKind
    canonical_id: UUID


@dataclass(slots=True)
class GetTraceByLineRangeQuery:
    source_snapshot_id: UUID
    line_from: int
    line_to: int
