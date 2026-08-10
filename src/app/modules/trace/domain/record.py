"""Trace lineage record entity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.trace.domain.enums import TraceCanonicalKind


@dataclass(slots=True)
class TraceRawToCanonicalRecord:
    """One lineage link from raw config lines to a canonical entity."""

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

    @classmethod
    def create(
        cls,
        *,
        source_snapshot_id: UUID,
        canonical_snapshot_id: UUID,
        vendor_code: str,
        normalizer_code: str,
        normalizer_version: str,
        source_line_start: int,
        source_line_end: int,
        canonical_kind: TraceCanonicalKind,
        canonical_id: UUID,
        source_fragment: str | None = None,
        canonical_role: str | None = None,
        note: str | None = None,
    ) -> TraceRawToCanonicalRecord:
        if source_line_start < 1:
            raise ValueError(f"source_line_start must be >= 1, got {source_line_start}")
        if source_line_end < source_line_start:
            raise ValueError(
                f"source_line_end ({source_line_end}) must be >= "
                f"source_line_start ({source_line_start})"
            )

        return cls(
            id=uuid4(),
            source_snapshot_id=source_snapshot_id,
            canonical_snapshot_id=canonical_snapshot_id,
            vendor_code=vendor_code,
            normalizer_code=normalizer_code,
            normalizer_version=normalizer_version,
            source_line_start=source_line_start,
            source_line_end=source_line_end,
            source_fragment=source_fragment,
            canonical_kind=canonical_kind,
            canonical_id=canonical_id,
            canonical_role=canonical_role,
            note=note,
            created_at=datetime.now(UTC),
        )

    def with_canonical_snapshot_id(
        self, canonical_snapshot_id: UUID
    ) -> TraceRawToCanonicalRecord:
        """Return a copy bound to persisted canonical snapshot id."""
        return replace(self, canonical_snapshot_id=canonical_snapshot_id)
