"""List all zones for a snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalZoneDTO
from app.modules.canonical.application.mappers import zone_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalZonesQuery:
    canonical_snapshot_id: UUID


@dataclass(slots=True)
class GetCanonicalZonesResult:
    zones: list[CanonicalZoneDTO]


class GetCanonicalZonesUseCase:
    """Read zone catalog for one snapshot."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalZonesQuery) -> GetCanonicalZonesResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        zones = await self.uow.zones.get_by_snapshot(query.canonical_snapshot_id)
        return GetCanonicalZonesResult(zones=[zone_to_dto(zone) for zone in zones])
