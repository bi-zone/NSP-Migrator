from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.canonical.domain.zone import CanonicalZone


class CanonicalZoneRepositoryPort(IAsyncRepository[CanonicalZone, UUID]):
    """Zone catalog within a snapshot."""

    @abstractmethod
    async def bulk_save(self, zones: list[CanonicalZone]) -> None: ...

    @abstractmethod
    async def get_by_id_for_snapshot(
        self, *, canonical_snapshot_id: UUID, zone_id: UUID
    ) -> CanonicalZone | None: ...

    @abstractmethod
    async def get_by_snapshot(
        self, canonical_snapshot_id: UUID
    ) -> list[CanonicalZone]: ...

    @abstractmethod
    async def get_by_ids_for_snapshot(
        self, *, canonical_snapshot_id: UUID, zone_ids: list[UUID]
    ) -> list[CanonicalZone]: ...
