"""Single object read with optional group members."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalObjectDTO
from app.modules.canonical.application.mappers import object_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.domain.object import CanonicalObjectMember
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalObjectQuery:
    canonical_snapshot_id: UUID
    object_id: UUID
    include_members: bool = True


@dataclass(slots=True)
class GetCanonicalObjectResult:
    object: CanonicalObjectDTO
    members: list[CanonicalObjectMember]


class GetCanonicalObjectUseCase:
    """Load one object; members populated when include_members is true."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalObjectQuery) -> GetCanonicalObjectResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        obj = await self.uow.objects.get_by_id_for_snapshot(
            canonical_snapshot_id=query.canonical_snapshot_id,
            object_id=query.object_id,
        )
        if obj is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical object not found: {query.object_id}"
            )

        members: list[CanonicalObjectMember] = []
        if query.include_members:
            members = await self.uow.objects.get_members_by_parent(
                canonical_snapshot_id=query.canonical_snapshot_id,
                parent_object_id=query.object_id,
            )

        return GetCanonicalObjectResult(object=object_to_dto(obj), members=members)
