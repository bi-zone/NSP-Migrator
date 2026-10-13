"""Trace integration-test fixtures backed by the migrated PostgreSQL DB.

Shared module fixtures own database creation, Alembic migration, and cleanup.
This file adds only trace-specific wiring and a representative lineage graph.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.modules.trace.adapters.db.uow import TraceUoW
from app.modules.trace.application.dto import SaveTraceRecordsCommand
from app.modules.trace.application.use_cases.save_trace_records import (
    SaveTraceRecordsUseCase,
)
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole
from app.modules.trace.domain.record import TraceRawToCanonicalRecord
from tests.modules.test_utils.db_seed import (
    CanonicalSnapshotGraphIds,
    seed_canonical_snapshot_graph,
)


@dataclass(frozen=True, slots=True)
class TraceScenario:
    """Persisted trace rows plus stable handles used by assertions."""

    source_snapshot_id: UUID
    canonical_snapshot_id: UUID
    other_source_snapshot_id: UUID
    other_canonical_snapshot_id: UUID
    rule_id: UUID
    object_id: UUID
    operand_id: UUID
    overlap_id: UUID
    other_object_id: UUID
    records: dict[str, TraceRawToCanonicalRecord]


@pytest.fixture
def trace_uow_factory(
    session_factory: SQLAlchemySessionFactory,
) -> Callable[[], TraceUoW]:
    """Return fresh real trace UoWs so each use case owns its transaction."""

    def _factory() -> TraceUoW:
        return TraceUoW(session_factory)

    return _factory


@pytest.fixture
def make_trace_record() -> Callable[..., TraceRawToCanonicalRecord]:
    """Build a valid TraceRawToCanonicalRecord with sensible defaults."""

    def _factory(
        *,
        source_snapshot_id: UUID,
        canonical_snapshot_id: UUID,
        canonical_kind: TraceCanonicalKind = TraceCanonicalKind.RULE,
        canonical_id: UUID | None = None,
        source_line_start: int = 1,
        source_line_end: int | None = None,
        source_fragment: str | None = None,
        canonical_role: str | None = None,
        vendor_code: str = "cisco_asa",
        normalizer_code: str = "cisco_asa",
        normalizer_version: str = "1",
        note: str | None = None,
    ) -> TraceRawToCanonicalRecord:
        return TraceRawToCanonicalRecord.create(
            source_snapshot_id=source_snapshot_id,
            canonical_snapshot_id=canonical_snapshot_id,
            vendor_code=vendor_code,
            normalizer_code=normalizer_code,
            normalizer_version=normalizer_version,
            source_line_start=source_line_start,
            source_line_end=(
                source_line_end if source_line_end is not None else source_line_start
            ),
            canonical_kind=canonical_kind,
            canonical_id=canonical_id or uuid4(),
            source_fragment=source_fragment,
            canonical_role=canonical_role,
            note=note,
        )

    return _factory


@pytest.fixture
def trace_scenario_factory(
    db_session,
    trace_uow_factory: Callable[[], TraceUoW],
    make_trace_record: Callable[..., TraceRawToCanonicalRecord],
) -> Callable[..., object]:
    """Persist a representative trace graph through the real save use case."""

    async def _create(*, label: str = "primary") -> TraceScenario:
        primary: CanonicalSnapshotGraphIds = await seed_canonical_snapshot_graph(
            db_session, label=label
        )
        other: CanonicalSnapshotGraphIds = await seed_canonical_snapshot_graph(
            db_session, label=f"{label}-other"
        )

        rule_id = uuid4()
        object_id = uuid4()
        operand_id = uuid4()
        overlap_canonical_id = uuid4()
        other_object_id = uuid4()

        records = {
            "rule": make_trace_record(
                source_snapshot_id=primary.source_snapshot_id,
                canonical_snapshot_id=primary.canonical_snapshot_id,
                canonical_kind=TraceCanonicalKind.RULE,
                canonical_id=rule_id,
                source_line_start=10,
                source_line_end=10,
                source_fragment="access-list ACL_IN extended permit tcp any any",
            ),
            "object_header": make_trace_record(
                source_snapshot_id=primary.source_snapshot_id,
                canonical_snapshot_id=primary.canonical_snapshot_id,
                canonical_kind=TraceCanonicalKind.OBJECT,
                canonical_id=object_id,
                source_line_start=20,
                source_line_end=23,
                source_fragment=(
                    "object network OBJ_APP\n"
                    " host 10.0.0.1\n"
                    " description app host\n"
                    "!"
                ),
                canonical_role=TraceCanonicalRole.HEADER.value,
            ),
            "operand_service": make_trace_record(
                source_snapshot_id=primary.source_snapshot_id,
                canonical_snapshot_id=primary.canonical_snapshot_id,
                canonical_kind=TraceCanonicalKind.RULE_OPERAND,
                canonical_id=operand_id,
                source_line_start=10,
                source_line_end=10,
                source_fragment="tcp",
                canonical_role=TraceCanonicalRole.SERVICE.value,
            ),
            "overlap": make_trace_record(
                source_snapshot_id=primary.source_snapshot_id,
                canonical_snapshot_id=primary.canonical_snapshot_id,
                canonical_kind=TraceCanonicalKind.ZONE,
                canonical_id=overlap_canonical_id,
                source_line_start=12,
                source_line_end=15,
                source_fragment="access-group ACL_IN in interface outside",
                canonical_role=TraceCanonicalRole.FROM_ACCESS_GROUP_BINDING.value,
            ),
            "other_object": make_trace_record(
                source_snapshot_id=other.source_snapshot_id,
                canonical_snapshot_id=other.canonical_snapshot_id,
                canonical_kind=TraceCanonicalKind.OBJECT,
                canonical_id=other_object_id,
                source_line_start=5,
                source_line_end=5,
                source_fragment="object network OTHER",
                canonical_role=TraceCanonicalRole.HEADER.value,
            ),
        }

        await SaveTraceRecordsUseCase(trace_uow_factory()).execute(
            SaveTraceRecordsCommand(records=list(records.values()))
        )

        return TraceScenario(
            source_snapshot_id=primary.source_snapshot_id,
            canonical_snapshot_id=primary.canonical_snapshot_id,
            other_source_snapshot_id=other.source_snapshot_id,
            other_canonical_snapshot_id=other.canonical_snapshot_id,
            rule_id=rule_id,
            object_id=object_id,
            operand_id=operand_id,
            overlap_id=overlap_canonical_id,
            other_object_id=other_object_id,
            records=records,
        )

    return _create
