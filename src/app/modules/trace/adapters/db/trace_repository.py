from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.trace.adapters.db import mappers, models
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord
from app.modules.trace.ports.trace_repository import (
    TraceRawToCanonicalRepositoryPort,
)


class SQLAlchemyTraceRawToCanonicalRepository(
    SqlAlchemyRepository[models.TraceRawToCanonicalModel, UUID],
    TraceRawToCanonicalRepositoryPort,
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.TraceRawToCanonicalModel)

    async def bulk_save(self, records: list[TraceRawToCanonicalRecord]) -> None:
        if not records:
            return
        self.session.add_all([mappers.record_to_model(r) for r in records])
        await self.session.flush()

    async def get_by_canonical_snapshot(
        self,
        *,
        canonical_snapshot_id: UUID,
        canonical_kind: TraceCanonicalKind | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TraceRawToCanonicalRecord]:
        return await self._list_by_snapshot_filter(
            models.TraceRawToCanonicalModel.canonical_snapshot_id,
            canonical_snapshot_id,
            canonical_kind=canonical_kind,
            limit=limit,
            offset=offset,
        )

    async def get_by_source_snapshot(
        self,
        *,
        source_snapshot_id: UUID,
        canonical_kind: TraceCanonicalKind | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[TraceRawToCanonicalRecord]:
        return await self._list_by_snapshot_filter(
            models.TraceRawToCanonicalModel.source_snapshot_id,
            source_snapshot_id,
            canonical_kind=canonical_kind,
            limit=limit,
            offset=offset,
        )

    async def get_by_entity(
        self,
        *,
        canonical_kind: TraceCanonicalKind,
        canonical_id: UUID,
    ) -> list[TraceRawToCanonicalRecord]:
        q = (
            select(models.TraceRawToCanonicalModel)
            .where(
                models.TraceRawToCanonicalModel.canonical_kind == canonical_kind.value,
                models.TraceRawToCanonicalModel.canonical_id == canonical_id,
            )
            .order_by(
                models.TraceRawToCanonicalModel.source_line_start.asc(),
                models.TraceRawToCanonicalModel.source_line_end.asc(),
            )
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.record_to_entity(m) for m in rows]

    async def get_by_line_range(
        self,
        *,
        source_snapshot_id: UUID,
        line_from: int,
        line_to: int,
    ) -> list[TraceRawToCanonicalRecord]:
        q = (
            select(models.TraceRawToCanonicalModel)
            .where(
                models.TraceRawToCanonicalModel.source_snapshot_id
                == source_snapshot_id,
                models.TraceRawToCanonicalModel.source_line_start <= line_to,
                models.TraceRawToCanonicalModel.source_line_end >= line_from,
            )
            .order_by(
                models.TraceRawToCanonicalModel.source_line_start.asc(),
                models.TraceRawToCanonicalModel.source_line_end.asc(),
            )
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.record_to_entity(m) for m in rows]

    async def _list_by_snapshot_filter(
        self,
        snapshot_column,
        snapshot_id: UUID,
        *,
        canonical_kind: TraceCanonicalKind | None,
        limit: int,
        offset: int,
    ) -> list[TraceRawToCanonicalRecord]:
        q = select(models.TraceRawToCanonicalModel).where(
            snapshot_column == snapshot_id
        )
        if canonical_kind is not None:
            q = q.where(
                models.TraceRawToCanonicalModel.canonical_kind == canonical_kind.value
            )
        q = (
            q.order_by(
                models.TraceRawToCanonicalModel.source_line_start.asc(),
                models.TraceRawToCanonicalModel.source_line_end.asc(),
                models.TraceRawToCanonicalModel.created_at.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.record_to_entity(m) for m in rows]
