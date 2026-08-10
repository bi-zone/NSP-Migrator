"""Single zone read within a snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalZoneDTO
from app.modules.canonical.application.mappers import zone_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalZoneQuery:
    canonical_snapshot_id: UUID
    zone_id: UUID


@dataclass(slots=True)
class GetCanonicalZoneResult:
    zone: CanonicalZoneDTO


class GetCanonicalZoneUseCase:
    """Load one zone by id within snapshot bounds."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalZoneQuery) -> GetCanonicalZoneResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        zone = await self.uow.zones.get_by_id_for_snapshot(
            canonical_snapshot_id=query.canonical_snapshot_id,
            zone_id=query.zone_id,
        )
        if zone is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical zone not found: {query.zone_id}"
            )

        return GetCanonicalZoneResult(zone=zone_to_dto(zone))
