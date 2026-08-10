from __future__ import annotations

from app.infrastructure.db.transactional import async_transactional
from app.modules.trace.application.dto import (
    GetTraceForEntityQuery,
    TraceRecordDTO,
)
from app.modules.trace.ports.uow import TraceUoWPort


class GetTraceForEntityUseCase:
    def __init__(self, uow: TraceUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetTraceForEntityQuery) -> list[TraceRecordDTO]:
        rows = await self.uow.trace_raw_to_canonical.get_by_entity(
            canonical_kind=query.canonical_kind,
            canonical_id=query.canonical_id,
        )
        return [TraceRecordDTO.from_entity(r) for r in rows]
