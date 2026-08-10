from app.infrastructure.interfaces.db import IAsyncUnitOfWork
from app.modules.trace.ports.trace_repository import (
    TraceRawToCanonicalRepositoryPort,
)


class TraceUoWPort(IAsyncUnitOfWork):
    trace_raw_to_canonical: TraceRawToCanonicalRepositoryPort
