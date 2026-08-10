"""List all objects for a snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalObjectDTO
from app.modules.canonical.application.mappers import object_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalObjectsQuery:
    canonical_snapshot_id: UUID


@dataclass(slots=True)
class GetCanonicalObjectsResult:
    objects: list[CanonicalObjectDTO]


class GetCanonicalObjectsUseCase:
    """Read object catalog for one snapshot."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self, query: GetCanonicalObjectsQuery
    ) -> GetCanonicalObjectsResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        objects = await self.uow.objects.get_by_snapshot(query.canonical_snapshot_id)
        return GetCanonicalObjectsResult(objects=[object_to_dto(o) for o in objects])
