"""Integration coverage for trace persistence and read use cases.

These tests exercise the real TraceUoW and SQLAlchemy repositories against
the shared PostgreSQL database migrated by Alembic.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trace.adapters.db.uow import TraceUoW
from app.modules.trace.application.dto import (
    GetTraceByLineRangeQuery,
    GetTraceForCanonicalSnapshotQuery,
    GetTraceForEntityQuery,
    GetTraceForSourceSnapshotQuery,
    SaveTraceRecordsCommand,
)
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
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole
from tests.modules.test_utils.db_seed import seed_canonical_snapshot_graph
from tests.modules.trace.conftest import TraceScenario


@pytest.mark.asyncio
async def test_save_and_read_complete_trace_graph_through_real_adapters(
    trace_scenario_factory: Callable[..., object],
    trace_uow_factory: Callable[[], TraceUoW],
) -> None:
    """Persist lineage rows and read them back through every query use case."""
    scenario: TraceScenario = await trace_scenario_factory()

    by_canonical = await GetTraceForCanonicalSnapshotUseCase(
        trace_uow_factory()
    ).execute(
        GetTraceForCanonicalSnapshotQuery(
            canonical_snapshot_id=scenario.canonical_snapshot_id
        )
    )
    assert {row.id for row in by_canonical} == {
        scenario.records["rule"].id,
        scenario.records["object_header"].id,
        scenario.records["operand_service"].id,
        scenario.records["overlap"].id,
    }

    by_source = await GetTraceForSourceSnapshotUseCase(trace_uow_factory()).execute(
        GetTraceForSourceSnapshotQuery(source_snapshot_id=scenario.source_snapshot_id)
    )
    assert {row.id for row in by_source} == {row.id for row in by_canonical}

    by_entity = await GetTraceForEntityUseCase(trace_uow_factory()).execute(
        GetTraceForEntityQuery(
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=scenario.object_id,
        )
    )
    assert len(by_entity) == 1
    assert by_entity[0].id == scenario.records["object_header"].id
    assert by_entity[0].canonical_role == TraceCanonicalRole.HEADER.value
    assert by_entity[0].source_line_start == 20
    assert by_entity[0].source_line_end == 23
    assert "object network OBJ_APP" in (by_entity[0].source_fragment or "")

    by_lines = await GetTraceByLineRangeUseCase(trace_uow_factory()).execute(
        GetTraceByLineRangeQuery(
            source_snapshot_id=scenario.source_snapshot_id,
            line_from=10,
            line_to=10,
        )
    )
    assert {row.id for row in by_lines} == {
        scenario.records["rule"].id,
        scenario.records["operand_service"].id,
    }


@pytest.mark.asyncio
async def test_kind_filter_and_pagination_apply_to_snapshot_reads(
    trace_scenario_factory: Callable[..., object],
    trace_uow_factory: Callable[[], TraceUoW],
) -> None:
    """Filter by kind and page an ordered snapshot listing."""
    scenario: TraceScenario = await trace_scenario_factory()

    objects_only = await GetTraceForCanonicalSnapshotUseCase(
        trace_uow_factory()
    ).execute(
        GetTraceForCanonicalSnapshotQuery(
            canonical_snapshot_id=scenario.canonical_snapshot_id,
            canonical_kind=TraceCanonicalKind.OBJECT,
        )
    )
    assert [row.id for row in objects_only] == [scenario.records["object_header"].id]

    page = await GetTraceForCanonicalSnapshotUseCase(trace_uow_factory()).execute(
        GetTraceForCanonicalSnapshotQuery(
            canonical_snapshot_id=scenario.canonical_snapshot_id,
            limit=2,
            offset=0,
        )
    )
    assert len(page) == 2
    assert page[0].source_line_start <= page[1].source_line_start

    next_page = await GetTraceForCanonicalSnapshotUseCase(trace_uow_factory()).execute(
        GetTraceForCanonicalSnapshotQuery(
            canonical_snapshot_id=scenario.canonical_snapshot_id,
            limit=2,
            offset=2,
        )
    )
    assert len(next_page) == 2
    assert {row.id for row in page}.isdisjoint({row.id for row in next_page})


@pytest.mark.asyncio
async def test_line_range_uses_inclusive_overlap_semantics(
    trace_scenario_factory: Callable[..., object],
    trace_uow_factory: Callable[[], TraceUoW],
) -> None:
    """Rows overlap a query when start<=to and end>=from (inclusive)."""
    scenario: TraceScenario = await trace_scenario_factory()

    overlapping = await GetTraceByLineRangeUseCase(trace_uow_factory()).execute(
        GetTraceByLineRangeQuery(
            source_snapshot_id=scenario.source_snapshot_id,
            line_from=12,
            line_to=15,
        )
    )
    overlapping_ids = {row.id for row in overlapping}
    assert scenario.records["overlap"].id in overlapping_ids
    # rule/operand end at 10 — no overlap with 12–15
    assert scenario.records["rule"].id not in overlapping_ids
    assert scenario.records["operand_service"].id not in overlapping_ids
    # object_header 20–23 — no overlap
    assert scenario.records["object_header"].id not in overlapping_ids

    no_object_span = await GetTraceByLineRangeUseCase(trace_uow_factory()).execute(
        GetTraceByLineRangeQuery(
            source_snapshot_id=scenario.source_snapshot_id,
            line_from=10,
            line_to=12,
        )
    )
    no_object_ids = {row.id for row in no_object_span}
    assert scenario.records["rule"].id in no_object_ids
    assert scenario.records["overlap"].id in no_object_ids
    assert scenario.records["object_header"].id not in no_object_ids


@pytest.mark.asyncio
async def test_snapshot_reads_do_not_leak_rows_from_other_snapshots(
    trace_scenario_factory: Callable[..., object],
    trace_uow_factory: Callable[[], TraceUoW],
) -> None:
    """Primary snapshot queries never return the secondary snapshot's object."""
    scenario: TraceScenario = await trace_scenario_factory()

    by_canonical = await GetTraceForCanonicalSnapshotUseCase(
        trace_uow_factory()
    ).execute(
        GetTraceForCanonicalSnapshotQuery(
            canonical_snapshot_id=scenario.canonical_snapshot_id
        )
    )
    assert all(
        row.canonical_snapshot_id == scenario.canonical_snapshot_id
        for row in by_canonical
    )
    assert scenario.records["other_object"].id not in {row.id for row in by_canonical}

    by_source = await GetTraceForSourceSnapshotUseCase(trace_uow_factory()).execute(
        GetTraceForSourceSnapshotQuery(source_snapshot_id=scenario.source_snapshot_id)
    )
    assert scenario.records["other_object"].id not in {row.id for row in by_source}

    other = await GetTraceForCanonicalSnapshotUseCase(trace_uow_factory()).execute(
        GetTraceForCanonicalSnapshotQuery(
            canonical_snapshot_id=scenario.other_canonical_snapshot_id
        )
    )
    assert [row.id for row in other] == [scenario.records["other_object"].id]


@pytest.mark.asyncio
async def test_empty_save_writes_zero_rows(
    db_session: AsyncSession,
    trace_uow_factory: Callable[[], TraceUoW],
) -> None:
    """Empty command is a no-op at the application boundary."""
    parents = await seed_canonical_snapshot_graph(db_session, label="empty")

    result = await SaveTraceRecordsUseCase(trace_uow_factory()).execute(
        SaveTraceRecordsCommand(records=[])
    )
    assert result.written == 0

    count = await db_session.scalar(
        text(
            """
            SELECT count(*)
            FROM trace_raw_to_canonical
            WHERE canonical_snapshot_id = :canonical_snapshot_id
            """
        ),
        {"canonical_snapshot_id": parents.canonical_snapshot_id},
    )
    assert count == 0


@pytest.mark.asyncio
async def test_db_check_rejects_invalid_line_range(
    db_session: AsyncSession,
) -> None:
    """DB CHECK ck_trace_r2c_line_range mirrors domain line-range invariants."""
    parents = await seed_canonical_snapshot_graph(db_session, label="check")

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                """
                INSERT INTO trace_raw_to_canonical
                    (
                        id,
                        source_snapshot_id,
                        canonical_snapshot_id,
                        vendor_code,
                        normalizer_code,
                        normalizer_version,
                        source_line_start,
                        source_line_end,
                        canonical_kind,
                        canonical_id
                    )
                VALUES
                    (
                        :id,
                        :source_snapshot_id,
                        :canonical_snapshot_id,
                        'cisco_asa',
                        'cisco_asa',
                        '1',
                        10,
                        5,
                        'rule',
                        :canonical_id
                    )
                """
            ),
            {
                "id": uuid4(),
                "source_snapshot_id": parents.source_snapshot_id,
                "canonical_snapshot_id": parents.canonical_snapshot_id,
                "canonical_id": uuid4(),
            },
        )
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_deleting_canonical_snapshot_cascades_trace_rows(
    trace_scenario_factory: Callable[..., object],
    db_session: AsyncSession,
) -> None:
    """FK ondelete=CASCADE removes lineage rows with the canonical snapshot."""
    scenario: TraceScenario = await trace_scenario_factory(label="cascade")

    before = await db_session.scalar(
        text(
            """
            SELECT count(*)
            FROM trace_raw_to_canonical
            WHERE canonical_snapshot_id = :canonical_snapshot_id
            """
        ),
        {"canonical_snapshot_id": scenario.canonical_snapshot_id},
    )
    assert before == 4

    await db_session.execute(
        text("DELETE FROM canonical_snapshot WHERE id = :id"),
        {"id": scenario.canonical_snapshot_id},
    )
    await db_session.commit()

    after = await db_session.scalar(
        text(
            """
            SELECT count(*)
            FROM trace_raw_to_canonical
            WHERE canonical_snapshot_id = :canonical_snapshot_id
            """
        ),
        {"canonical_snapshot_id": scenario.canonical_snapshot_id},
    )
    assert after == 0
