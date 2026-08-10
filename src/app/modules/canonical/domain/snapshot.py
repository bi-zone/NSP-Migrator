"""Canonical snapshot aggregate root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.canonical.domain.enums import SnapshotStatus


@dataclass(slots=True)
class CanonicalSnapshot:
    """Header row for one normalized policy graph."""

    id: UUID
    source_snapshot_id: UUID
    normalizer_code: str
    normalizer_version: str
    status: SnapshotStatus
    zones_total: int
    objects_total: int
    rules_total: int
    issues_total: int
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        source_snapshot_id: UUID,
        normalizer_code: str,
        normalizer_version: str,
        status: SnapshotStatus = SnapshotStatus.PENDING,
        zones_total: int = 0,
        objects_total: int = 0,
        rules_total: int = 0,
        issues_total: int = 0,
    ) -> CanonicalSnapshot:
        return cls(
            # TODO:: consider shared factory helpers for uuid4/datetime.now(UTC)
            # instead of inline defaults in every entity create() method.
            id=uuid4(),
            source_snapshot_id=source_snapshot_id,
            normalizer_code=normalizer_code,
            normalizer_version=normalizer_version,
            status=status,
            zones_total=zones_total,
            objects_total=objects_total,
            rules_total=rules_total,
            issues_total=issues_total,
            created_at=datetime.now(UTC),
        )
