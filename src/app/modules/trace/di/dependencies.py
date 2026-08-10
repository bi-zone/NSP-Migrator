from fastapi import Depends, Request

from app.di.dependencies import get_di_container
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
from app.modules.trace.di.container import TraceModuleContainer


def get_trace_module_container(request: Request) -> TraceModuleContainer:
    return get_di_container(request).trace_module()


def get_trace_for_canonical_snapshot_use_case(
    container: TraceModuleContainer = Depends(get_trace_module_container),
) -> GetTraceForCanonicalSnapshotUseCase:
    return container.get_trace_for_canonical_snapshot_use_case()


def get_trace_for_source_snapshot_use_case(
    container: TraceModuleContainer = Depends(get_trace_module_container),
) -> GetTraceForSourceSnapshotUseCase:
    return container.get_trace_for_source_snapshot_use_case()


def get_trace_for_entity_use_case(
    container: TraceModuleContainer = Depends(get_trace_module_container),
) -> GetTraceForEntityUseCase:
    return container.get_trace_for_entity_use_case()


def get_trace_by_line_range_use_case(
    container: TraceModuleContainer = Depends(get_trace_module_container),
) -> GetTraceByLineRangeUseCase:
    return container.get_trace_by_line_range_use_case()
