from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.canonical.domain.object import CanonicalObject, CanonicalObjectMember


class CanonicalObjectRepositoryPort(IAsyncRepository[CanonicalObject, UUID]):
    """Objects plus membership edges; get_members_by_parents feeds group BFS."""

    @abstractmethod
    async def bulk_save(self, objects: list[CanonicalObject]) -> None: ...

    @abstractmethod
    async def bulk_save_members(self, members: list[CanonicalObjectMember]) -> None: ...

    @abstractmethod
    async def get_by_id_for_snapshot(
        self, *, canonical_snapshot_id: UUID, object_id: UUID
    ) -> CanonicalObject | None: ...

    @abstractmethod
    async def get_members_by_parent(
        self, *, canonical_snapshot_id: UUID, parent_object_id: UUID
    ) -> list[CanonicalObjectMember]: ...

    @abstractmethod
    async def get_by_snapshot(
        self, canonical_snapshot_id: UUID
    ) -> list[CanonicalObject]: ...

    @abstractmethod
    async def get_by_ids_for_snapshot(
        self, *, canonical_snapshot_id: UUID, object_ids: list[UUID]
    ) -> list[CanonicalObject]: ...

    @abstractmethod
    async def get_members_by_parents(
        self, *, canonical_snapshot_id: UUID, parent_object_ids: list[UUID]
    ) -> list[CanonicalObjectMember]: ...
