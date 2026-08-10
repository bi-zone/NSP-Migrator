"""Repository port for raw-to-canonical lineage records."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord


class TraceRawToCanonicalRepositoryPort(
    IAsyncRepository[TraceRawToCanonicalRecord, UUID]
):
    """Persistence and query contract for append-only trace rows."""

    @abstractmethod
    async def bulk_save(self, records: list[TraceRawToCanonicalRecord]) -> None: ...

    @abstractmethod
    async def get_by_canonical_snapshot(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_kind: TraceCanonicalKind | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TraceRawToCanonicalRecord]: ...

    @abstractmethod
    async def get_by_source_snapshot(
        self,
        *,
        source_snapshot_id: UUID,
        canonical_kind: TraceCanonicalKind | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TraceRawToCanonicalRecord]: ...

    @abstractmethod
    async def get_by_entity(
        self,
        *,
        canonical_kind: TraceCanonicalKind,
        canonical_id: UUID,
    ) -> list[TraceRawToCanonicalRecord]: ...

    @abstractmethod
    async def get_by_line_range(
        self,
        *,
        source_snapshot_id: UUID,
        line_from: int,
        line_to: int,
    ) -> list[TraceRawToCanonicalRecord]: ...
