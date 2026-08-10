from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(slots=True)
class SourceSnapshot:
    id: UUID
    source_id: UUID | None
    artifact_hash: str | None
    source_format: str | None
    is_latest: bool
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        source_id: UUID,
        artifact_hash: str,
        source_format: str,
        is_latest: bool = True,
    ) -> SourceSnapshot:
        return cls(
            id=uuid4(),
            source_id=source_id,
            artifact_hash=artifact_hash,
            source_format=source_format,
            is_latest=is_latest,
            created_at=datetime.now(UTC),
        )
