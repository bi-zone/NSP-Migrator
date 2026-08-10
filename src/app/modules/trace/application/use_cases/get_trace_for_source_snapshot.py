from __future__ import annotations

from app.infrastructure.db.transactional import async_transactional
from app.modules.trace.application.dto import (
    GetTraceForSourceSnapshotQuery,
    TraceRecordDTO,
)
from app.modules.trace.ports.uow import TraceUoWPort


class GetTraceForSourceSnapshotUseCase:
    def __init__(self, uow: TraceUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self, query: GetTraceForSourceSnapshotQuery
    ) -> list[TraceRecordDTO]:
        rows = await self.uow.trace_raw_to_canonical.get_by_source_snapshot(
            source_snapshot_id=query.source_snapshot_id,
            canonical_kind=query.canonical_kind,
            limit=query.limit,
            offset=query.offset,
        )
        return [TraceRecordDTO.from_entity(r) for r in rows]
