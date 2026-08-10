from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID


@dataclass(slots=True)
class SourceArtifact:
    snapshot_id: UUID
    raw_text: str
    line_count: int
    size_bytes: int
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: UUID,
        raw_text: str,
    ) -> SourceArtifact:
        return cls(
            snapshot_id=snapshot_id,
            raw_text=raw_text,
            line_count=raw_text.count("\n") + 1 if raw_text else 0,
            size_bytes=len(raw_text.encode("utf-8")),
            created_at=datetime.now(UTC),
        )
