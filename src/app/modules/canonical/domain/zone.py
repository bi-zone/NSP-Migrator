"""Canonical security zone entity."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(slots=True)
class CanonicalZone:
    """Named zone within a snapshot."""

    id: UUID
    canonical_snapshot_id: UUID
    zone_key: str
    name: str
    direction_hint: str | None
    description: str | None

    @classmethod
    def create(
        cls,
        *,
        canonical_snapshot_id: UUID,
        zone_key: str,
        name: str,
        direction_hint: str | None = None,
        description: str | None = None,
    ) -> CanonicalZone:
        return cls(
            id=uuid4(),
            canonical_snapshot_id=canonical_snapshot_id,
            zone_key=zone_key,
            name=name,
            direction_hint=direction_hint,
            description=description,
        )
