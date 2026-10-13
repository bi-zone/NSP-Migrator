"""Integration coverage for canonical graph persistence and read use cases.

These tests exercise the real canonical UoW and SQLAlchemy repositories against
the shared PostgreSQL database migrated by Alembic.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.canonical.adapters.db.uow import CanonicalUoW
from app.modules.canonical.application.use_cases.get_canonical_issues import (
    GetCanonicalIssuesQuery,
    GetCanonicalIssuesUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
    GetCanonicalObjectUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_objects import (
    GetCanonicalObjectsQuery,
    GetCanonicalObjectsUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule import (
    GetCanonicalRuleQuery,
    GetCanonicalRuleUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_snapshot import (
    GetCanonicalSnapshotQuery,
    GetCanonicalSnapshotUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zone import (
    GetCanonicalZoneQuery,
    GetCanonicalZoneUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_zones import (
    GetCanonicalZonesQuery,
    GetCanonicalZonesUseCase,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceQuery,
    GetLatestCanonicalSnapshotForSourceUseCase,
)
from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotCommand,
    SaveCanonicalSnapshotUseCase,
)
from app.modules.canonical.domain import (
    CanonicalRule,
    CanonicalRuleOperand,
    OperandRole,
)
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from tests.modules.canonical.conftest import CanonicalScenario


@pytest.mark.asyncio
async def test_save_and_read_complete_canonical_graph_through_real_adapters(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Persist counts and read every canonical aggregate projection back."""
    scenario: CanonicalScenario = await canonical_scenario_factory()

    snapshot_result = await GetCanonicalSnapshotUseCase(
        canonical_uow_factory()
    ).execute(GetCanonicalSnapshotQuery(scenario.snapshot_id))
    snapshot = snapshot_result.snapshot
    assert snapshot.status == "success"
    assert snapshot.zones_total == len(scenario.zones)
    assert snapshot.objects_total == len(scenario.objects)
    assert snapshot.rules_total == len(scenario.rules)
    assert snapshot.issues_total == len(scenario.issues)
    assert {zone.id for zone in snapshot_result.zones} == {
        zone.id for zone in scenario.zones.values()
    }
    assert {obj.id for obj in snapshot_result.objects} == {
        obj.id for obj in scenario.objects.values()
    }
    assert {rule.id for rule in snapshot_result.rules} == {
        rule.id for rule in scenario.rules.values()
    }
    assert sum(len(rule.operands or []) for rule in snapshot_result.rules) == len(
        scenario.operands
    )

    zones = await GetCanonicalZonesUseCase(canonical_uow_factory()).execute(
        GetCanonicalZonesQuery(scenario.snapshot_id)
    )
    objects = await GetCanonicalObjectsUseCase(canonical_uow_factory()).execute(
        GetCanonicalObjectsQuery(scenario.snapshot_id)
    )
    issues = await GetCanonicalIssuesUseCase(canonical_uow_factory()).execute(
        GetCanonicalIssuesQuery(scenario.snapshot_id)
    )
    assert {zone.id for zone in zones.zones} == {
        zone.id for zone in scenario.zones.values()
    }
    assert {obj.id for obj in objects.objects} == {
        obj.id for obj in scenario.objects.values()
    }
    assert [issue.issue_code for issue in issues.issues] == ["CANONICAL_TEST_WARNING"]
    assert issues.issues[0].source_line_start == 40

    latest = await GetLatestCanonicalSnapshotForSourceUseCase(
        canonical_uow_factory()
    ).execute(GetLatestCanonicalSnapshotForSourceQuery(scenario.source_snapshot_id))
    assert latest.snapshot is not None
    assert latest.snapshot.id == scenario.snapshot_id


@pytest.mark.asyncio
async def test_detail_reads_preserve_membership_order_and_hydrate_operands(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Read a group, a zone, and a rule with resolved zone/object summaries."""
    scenario: CanonicalScenario = await canonical_scenario_factory()

    zone_result = await GetCanonicalZoneUseCase(canonical_uow_factory()).execute(
        GetCanonicalZoneQuery(
            canonical_snapshot_id=scenario.snapshot_id,
            zone_id=scenario.zones["outside"].id,
        )
    )
    assert zone_result.zone.name == "Perimeter primary"

    object_result = await GetCanonicalObjectUseCase(canonical_uow_factory()).execute(
        GetCanonicalObjectQuery(
            canonical_snapshot_id=scenario.snapshot_id,
            object_id=scenario.objects["outer_group"].id,
        )
    )
    assert object_result.object.name == "Finance Bundle primary"
    assert [member.child_object_id for member in object_result.members] == [
        scenario.objects["inner_group"].id
    ]

    rule_result = await GetCanonicalRuleUseCase(canonical_uow_factory()).execute(
        GetCanonicalRuleQuery(
            canonical_snapshot_id=scenario.snapshot_id,
            rule_id=scenario.rules["nested"].id,
        )
    )
    operands = rule_result.rule.operands or []
    assert len(operands) == 4
    hydrated_zone_names = {
        operand.target_zone.name
        for operand in operands
        if getattr(operand, "target_zone", None) is not None
    }
    hydrated_object_names = {
        operand.target_object.name
        for operand in operands
        if getattr(operand, "target_object", None) is not None
    }
    assert hydrated_zone_names == {"Perimeter primary", "Trusted primary"}
    assert hydrated_object_names == {"Finance Bundle primary", "HTTPS primary"}


@pytest.mark.asyncio
async def test_detail_reads_enforce_snapshot_boundaries_and_missing_snapshot_errors(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> None:
    """Prevent IDs from another snapshot from leaking through scoped lookups."""
    first: CanonicalScenario = await canonical_scenario_factory(label="first")
    second: CanonicalScenario = await canonical_scenario_factory(label="second")

    with pytest.raises(
        CanonicalModuleNotFoundError, match="Canonical object not found"
    ):
        await GetCanonicalObjectUseCase(canonical_uow_factory()).execute(
            GetCanonicalObjectQuery(
                canonical_snapshot_id=first.snapshot_id,
                object_id=second.objects["payroll_host"].id,
            )
        )

    with pytest.raises(CanonicalModuleNotFoundError, match="Canonical rule not found"):
        await GetCanonicalRuleUseCase(canonical_uow_factory()).execute(
            GetCanonicalRuleQuery(
                canonical_snapshot_id=first.snapshot_id,
                rule_id=second.rules["nested"].id,
            )
        )

    with pytest.raises(
        CanonicalModuleNotFoundError, match="Canonical snapshot not found"
    ):
        await GetCanonicalSnapshotUseCase(canonical_uow_factory()).execute(
            GetCanonicalSnapshotQuery(uuid4())
        )


@pytest.mark.asyncio
async def test_save_is_idempotent_for_successful_source_and_normalizer_key(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
    db_session: AsyncSession,
) -> None:
    """Reuse a successful snapshot without duplicating its persisted graph."""
    scenario: CanonicalScenario = await canonical_scenario_factory(label="idem")
    result = await SaveCanonicalSnapshotUseCase(canonical_uow_factory()).execute(
        SaveCanonicalSnapshotCommand(
            source_snapshot_id=scenario.source_snapshot_id,
            normalizer_code="canonical_test",
            normalizer_version="1-idem",
            zones=[],
            objects=[],
            object_members=[],
            rules=[],
            operands=[],
            issues=[],
        )
    )

    assert result.created is False
    assert result.canonical_snapshot_id == scenario.snapshot_id
    count = await db_session.scalar(
        text(
            """
            SELECT count(*)
            FROM canonical_snapshot
            WHERE source_snapshot_id = :source_snapshot_id
              AND normalizer_code = 'canonical_test'
              AND normalizer_version = '1-idem'
            """
        ),
        {"source_snapshot_id": scenario.source_snapshot_id},
    )
    assert count == 1


@pytest.mark.asyncio
async def test_save_rolls_back_whole_graph_when_operand_constraint_fails(
    canonical_scenario_factory: Callable[..., object],
    canonical_uow_factory: Callable[[], CanonicalUoW],
    db_session: AsyncSession,
) -> None:
    """Prove header and children do not commit after a late graph write failure."""
    scenario: CanonicalScenario = await canonical_scenario_factory(label="rollback")
    rule = CanonicalRule.create(
        canonical_snapshot_id=uuid4(),
        rule_key="rollback-candidate",
        name="Rollback Candidate",
        action="permit",
        enabled=True,
        priority=1,
    )
    invalid_operand = CanonicalRuleOperand.create(
        rule_id=rule.id,
        operand_role=OperandRole.DST_OBJECT,
    )

    with pytest.raises(IntegrityError):
        await SaveCanonicalSnapshotUseCase(canonical_uow_factory()).execute(
            SaveCanonicalSnapshotCommand(
                source_snapshot_id=scenario.source_snapshot_id,
                normalizer_code="canonical_test",
                normalizer_version="broken-write",
                zones=[],
                objects=[],
                object_members=[],
                rules=[rule],
                operands=[invalid_operand],
                issues=[],
            )
        )

    count = await db_session.scalar(
        text(
            """
            SELECT count(*)
            FROM canonical_snapshot
            WHERE source_snapshot_id = :source_snapshot_id
              AND normalizer_version = 'broken-write'
            """
        ),
        {"source_snapshot_id": scenario.source_snapshot_id},
    )
    assert count == 0
