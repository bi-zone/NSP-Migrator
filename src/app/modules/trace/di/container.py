from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.trace.adapters.db.uow import TraceUoW
from app.modules.trace.application.use_cases.get_trace_by_line_range import (
    GetTraceByLineRangeUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_canonical_snapshot import (
    GetTraceForCanonicalSnapshotUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_entity import (
    GetTraceForEntityUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_source_snapshot import (
    GetTraceForSourceSnapshotUseCase,
)
from app.modules.trace.application.use_cases.save_trace_records import (
    SaveTraceRecordsUseCase,
)


class TraceModuleContainer(DeclarativeContainer):
    session_factory: providers.Dependency = providers.Dependency()

    uow = providers.Factory(TraceUoW, session_factory=session_factory)

    save_trace_records_use_case = providers.Factory(SaveTraceRecordsUseCase, uow=uow)
    get_trace_for_canonical_snapshot_use_case = providers.Factory(
        GetTraceForCanonicalSnapshotUseCase, uow=uow
    )
    get_trace_for_source_snapshot_use_case = providers.Factory(
        GetTraceForSourceSnapshotUseCase, uow=uow
    )
    get_trace_for_entity_use_case = providers.Factory(GetTraceForEntityUseCase, uow=uow)
    get_trace_by_line_range_use_case = providers.Factory(
        GetTraceByLineRangeUseCase, uow=uow
    )
