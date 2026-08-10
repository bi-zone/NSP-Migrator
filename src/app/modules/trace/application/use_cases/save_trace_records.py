"""Internal write use case for persisting trace lineage rows."""

from __future__ import annotations

from app.infrastructure.db.transactional import async_transactional
from app.modules.trace.application.dto import (
    SaveTraceRecordsCommand,
    SaveTraceRecordsResult,
)
from app.modules.trace.ports.uow import TraceUoWPort


class SaveTraceRecordsUseCase:
    """Bulk-insert trace records produced by imports normalization.

    The use case is intentionally not exposed via HTTP. It is orchestrated by
    RunCiscoMappingUseCase after canonical snapshot persistence.
    """

    def __init__(self, uow: TraceUoWPort) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(self, command: SaveTraceRecordsCommand) -> SaveTraceRecordsResult:
        if not command.records:
            return SaveTraceRecordsResult(written=0)

        await self.uow.trace_raw_to_canonical.bulk_save(command.records)
        return SaveTraceRecordsResult(written=len(command.records))
