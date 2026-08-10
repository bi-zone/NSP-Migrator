"""Normalizer issue entity linked to a snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(slots=True)
class CanonicalIssue:
    """Diagnostic record from imports normalizer (stable issue_code)."""

    id: UUID
    canonical_snapshot_id: UUID
    entity_type: str
    entity_key: str | None
    issue_code: str
    message: str
    source_line_start: int | None
    source_line_end: int | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        canonical_snapshot_id: UUID,
        entity_type: str,
        issue_code: str,
        message: str,
        entity_key: str | None = None,
        source_line_start: int | None = None,
        source_line_end: int | None = None,
    ) -> CanonicalIssue:
        return cls(
            id=uuid4(),
            canonical_snapshot_id=canonical_snapshot_id,
            entity_type=entity_type,
            entity_key=entity_key,
            issue_code=issue_code,
            message=message,
            source_line_start=source_line_start,
            source_line_end=source_line_end,
            created_at=datetime.now(UTC),
        )
