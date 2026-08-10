from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.trace.adapters.db.trace_repository import (
    SQLAlchemyTraceRawToCanonicalRepository,
)
from app.modules.trace.ports.uow import TraceUoWPort


class TraceUoW(SQLAlchemyUnitOfWork, TraceUoWPort):
    def bind_repositories(self) -> None:
        if self.session is None:
            raise RuntimeError("TraceUoW session is not initialized")
        self.trace_raw_to_canonical = SQLAlchemyTraceRawToCanonicalRepository(
            self.session
        )

    async def __aenter__(self):
        await super().__aenter__()
        self.bind_repositories()
        return self
