from __future__ import annotations

from app.infrastructure.db.transactional import async_transactional
from app.modules.trace.application.dto import (
    GetTraceByLineRangeQuery,
    TraceRecordDTO,
)
from app.modules.trace.domain.exceptions import TraceModuleValidationError
from app.modules.trace.ports.uow import TraceUoWPort


class GetTraceByLineRangeUseCase:
    def __init__(self, uow: TraceUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetTraceByLineRangeQuery) -> list[TraceRecordDTO]:
        if query.line_from < 1 or query.line_to < query.line_from:
            raise TraceModuleValidationError(
                f"invalid line range: from={query.line_from} to={query.line_to}"
            )
        rows = await self.uow.trace_raw_to_canonical.get_by_line_range(
            source_snapshot_id=query.source_snapshot_id,
            line_from=query.line_from,
            line_to=query.line_to,
        )
        return [TraceRecordDTO.from_entity(r) for r in rows]
