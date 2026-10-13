from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.querying import Pagination, SortDirection, Sorting
from app.modules.reports.adapters.db.uow import ReportsUnitOfWork
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.value_objects import (
    ReportEnvironmentSnapshot,
    ReportRuleSnapshot,
)
from app.modules.reports.ports.report_repository import (
    ReportHeaderFilters,
    ReportHeaderSortField,
    ReportRuleFilters,
    default_report_header_sorting,
)


def _rule_snapshot(
    *,
    policy_name: str,
    priority: int,
    src_zone_names: tuple[str, ...] = (),
    dst_zone_names: tuple[str, ...] = (),
    src_addr_values: tuple[str, ...] = (),
    dst_addr_values: tuple[str, ...] = (),
    service_values: tuple[str, ...] = (),
    migration_result: ReportRuleMigrationResult = ReportRuleMigrationResult.PUSHED,
    reason: str = "Success",
) -> ReportRuleSnapshot:
    return ReportRuleSnapshot(
        policy_name=policy_name,
        action=ReportRuleAction.ACCEPT,
        priority=priority,
        src_zone_names=src_zone_names,
        dst_zone_names=dst_zone_names,
        src_addr_values=src_addr_values,
        dst_addr_values=dst_addr_values,
        service_values=service_values,
        migration_result=migration_result,
        reason=reason,
    )


def _report(
    *,
    csp_profile_id: UUID,
    title: str,
    created_at: datetime,
    vpc_id: str = "vpc-1",
    target_id: str = "target-1",
    rule_snapshots: tuple[ReportRuleSnapshot, ...] | None = None,
) -> Report:
    report = Report.create(
        scope_title=title,
        csp_profile_id=csp_profile_id,
        commit_id=42,
        environment=ReportEnvironmentSnapshot(
            project_name="Firewall migration",
            vpc_id=vpc_id,
            target_name=f"Gateway {target_id}",
            target_id=target_id,
        ),
        rule_snapshots=rule_snapshots
        or (_rule_snapshot(policy_name="policy", priority=10),),
    )
    return replace(report, title=title, created_at=created_at)


async def _create_csp_profile(db_session: AsyncSession) -> UUID:
    profile_id = uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO csp_profile (id, name, base_url, username, is_active)
            VALUES (:id, :name, :base_url, :username, true)
            """
        ),
        {
            "id": profile_id,
            "name": f"reports-profile-{profile_id}",
            "base_url": "https://sdwan.example.test",
            "username": "reports-user",
        },
    )
    await db_session.commit()
    return profile_id


async def _save_reports(
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
    *reports: Report,
) -> None:
    async with reports_uow_factory() as uow:
        for report in reports:
            await uow.reports.save_report(report)
        await uow.commit()


@pytest.mark.asyncio
async def test_save_and_get_report_by_id_persists_complete_report_graph(
    report_factory: Callable[..., Report],
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
) -> None:
    report = report_factory(priorities=(20, 10))

    async with reports_uow_factory() as uow:
        await uow.reports.save_report(report)
        await uow.commit()

    async with reports_uow_factory() as uow:
        restored = await uow.reports.get_report_by_id(report.id)

    assert restored is not None
    assert restored.id == report.id
    assert restored.environment == report.environment
    assert restored.rules is not None
    assert [rule.priority for rule in restored.rules] == [10, 20]
    assert restored.rules[0].src_addr_values == ("10.10.0.0/24",)
    assert restored.rules[0].migration_result == report.rules[0].migration_result


@pytest.mark.asyncio
async def test_list_report_headers_is_paginated_and_does_not_load_rules(
    report_factory: Callable[..., Report],
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
) -> None:
    older = report_factory(
        title="Older",
        created_at=datetime(2026, 9, 7, 10, 0, tzinfo=UTC),
    )
    newer = report_factory(
        title="Newer",
        created_at=datetime(2026, 9, 7, 11, 0, tzinfo=UTC),
    )
    async with reports_uow_factory() as uow:
        await uow.reports.save_report(older)
        await uow.reports.save_report(newer)
        await uow.commit()

    async with reports_uow_factory() as uow:
        page = await uow.reports.list_report_headers(
            Pagination(limit=1, offset=0),
            filters=ReportHeaderFilters(),
            sorting=default_report_header_sorting(),
        )
        all_headers = await uow.reports.get_list()

    assert page.total == 2
    assert [report.id for report in page.reports] == [newer.id]
    assert all(report.rules is None for report in page.reports)
    assert [report.id for report in all_headers] == [newer.id, older.id]
    assert all(report.rules is None for report in all_headers)


@pytest.mark.asyncio
async def test_list_report_headers_combines_filters_escapes_search_and_includes_end_date(
    csp_profile_id: UUID,
    db_session: AsyncSession,
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
) -> None:
    other_profile_id = await _create_csp_profile(db_session)
    matching_older = _report(
        csp_profile_id=csp_profile_id,
        title="BrAnCh%_ migration",
        created_at=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        vpc_id="vpc-branch",
        target_id="target-1",
    )
    matching_newer = _report(
        csp_profile_id=csp_profile_id,
        title="BrAnCh%_ migration",
        created_at=datetime(2026, 9, 10, 23, 59, tzinfo=UTC),
        vpc_id="vpc-branch",
        target_id="target-2",
    )
    await _save_reports(
        reports_uow_factory,
        matching_older,
        matching_newer,
        _report(
            csp_profile_id=csp_profile_id,
            title="BrAnCh%_ migration",
            created_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
            vpc_id="vpc-branch",
            target_id="target-3",
        ),
        _report(
            csp_profile_id=other_profile_id,
            title="BrAnCh%_ migration",
            created_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
            vpc_id="vpc-branch",
            target_id="target-1",
        ),
        _report(
            csp_profile_id=csp_profile_id,
            title="BrAnCh%_ migration",
            created_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
            vpc_id="vpc-other",
            target_id="target-1",
        ),
        _report(
            csp_profile_id=csp_profile_id,
            title="BrAnCh%_ migration",
            created_at=datetime(2026, 9, 11, 0, tzinfo=UTC),
            vpc_id="vpc-branch",
            target_id="target-1",
        ),
    )

    async with reports_uow_factory() as uow:
        page = await uow.reports.list_report_headers(
            Pagination(limit=1, offset=1),
            filters=ReportHeaderFilters(
                search_by_name="branch%_",
                created_from=date(2026, 9, 10),
                created_to=date(2026, 9, 10),
                csp_profile_id=csp_profile_id,
                vpc_id="vpc-branch",
                target_ids=("target-1", "target-2"),
            ),
            sorting=default_report_header_sorting(),
        )

    assert page.total == 2
    assert [report.id for report in page.reports] == [matching_older.id]
    assert page.reports[0].rules is None


@pytest.mark.asyncio
async def test_list_report_headers_uses_report_id_as_stable_timestamp_tiebreaker(
    csp_profile_id: UUID,
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
) -> None:
    created_at = datetime(2026, 9, 10, 12, tzinfo=UTC)
    first = _report(
        csp_profile_id=csp_profile_id,
        title="Same time",
        created_at=created_at,
    )
    second = _report(
        csp_profile_id=csp_profile_id,
        title="Same time",
        created_at=created_at,
    )
    await _save_reports(reports_uow_factory, first, second)

    async with reports_uow_factory() as uow:
        page = await uow.reports.list_report_headers(
            Pagination(),
            filters=ReportHeaderFilters(),
            sorting=Sorting(
                field=ReportHeaderSortField.CREATED_AT,
                direction=SortDirection.ASC,
            ),
        )

    assert [report.id for report in page.reports] == sorted([first.id, second.id])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_by_object_value", "expected_policy_name"),
    [
        ("src%_Z", "source-zone-policy"),
        ("destination-zone", "destination-zone-policy"),
        ("10.10.0", "source-address-policy"),
        ("203.0.113", "destination-address-policy"),
        ("TCP/443", "service-policy"),
    ],
)
async def test_list_report_rules_searches_each_operand_array(
    csp_profile_id: UUID,
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
    search_by_object_value: str,
    expected_policy_name: str,
) -> None:
    report = _report(
        csp_profile_id=csp_profile_id,
        title="Operand search",
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
        rule_snapshots=(
            _rule_snapshot(
                policy_name="source-zone-policy",
                priority=10,
                src_zone_names=("src%_zone",),
            ),
            _rule_snapshot(
                policy_name="destination-zone-policy",
                priority=20,
                dst_zone_names=("destination-zone",),
            ),
            _rule_snapshot(
                policy_name="source-address-policy",
                priority=30,
                src_addr_values=("10.10.0.0/24",),
            ),
            _rule_snapshot(
                policy_name="destination-address-policy",
                priority=40,
                dst_addr_values=("203.0.113.10",),
            ),
            _rule_snapshot(
                policy_name="service-policy",
                priority=50,
                service_values=("tcp/443",),
            ),
        ),
    )
    await _save_reports(reports_uow_factory, report)

    async with reports_uow_factory() as uow:
        page = await uow.reports.list_report_rules(
            report.id,
            Pagination(),
            filters=ReportRuleFilters(search_by_object_value=search_by_object_value),
        )

    assert page is not None
    assert page.total == 1
    assert [rule.policy_name for rule in page.rules] == [expected_policy_name]


@pytest.mark.asyncio
async def test_list_report_rules_combines_filters_preserves_outcomes_and_handles_empty_page(
    csp_profile_id: UUID,
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
) -> None:
    report = _report(
        csp_profile_id=csp_profile_id,
        title="Outcome search",
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
        rule_snapshots=(
            _rule_snapshot(
                policy_name="Admin%_ validation",
                priority=10,
                migration_result=ReportRuleMigrationResult.ERROR,
                reason="Validation failed: service is unavailable",
            ),
            _rule_snapshot(
                policy_name="Admin%_ push",
                priority=20,
                migration_result=ReportRuleMigrationResult.FAILED,
                reason="SD-WAN rejected policy: destination is invalid",
            ),
            _rule_snapshot(
                policy_name="Admin ordinary",
                priority=10,
                migration_result=ReportRuleMigrationResult.PUSHED,
            ),
        ),
    )
    assert report.rules is not None
    await _save_reports(reports_uow_factory, report)

    async with reports_uow_factory() as uow:
        all_rules = await uow.reports.list_report_rules(
            report.id,
            Pagination(),
            filters=ReportRuleFilters(),
        )
        filtered_page = await uow.reports.list_report_rules(
            report.id,
            Pagination(limit=1, offset=1),
            filters=ReportRuleFilters(
                search_by_policy_name="admin%_",
                migration_results=(
                    ReportRuleMigrationResult.ERROR,
                    ReportRuleMigrationResult.FAILED,
                ),
            ),
        )
        empty_page = await uow.reports.list_report_rules(
            report.id,
            Pagination(),
            filters=ReportRuleFilters(search_by_policy_name="does-not-exist"),
        )
        missing_page = await uow.reports.list_report_rules(
            uuid4(),
            Pagination(),
            filters=ReportRuleFilters(),
        )

    assert all_rules is not None
    assert [(rule.priority, rule.id) for rule in all_rules.rules] == sorted(
        (rule.priority, rule.id) for rule in report.rules
    )
    assert {(rule.migration_result, rule.reason) for rule in all_rules.rules} >= {
        (
            ReportRuleMigrationResult.ERROR,
            "Validation failed: service is unavailable",
        ),
        (
            ReportRuleMigrationResult.FAILED,
            "SD-WAN rejected policy: destination is invalid",
        ),
    }
    assert filtered_page is not None
    assert filtered_page.total == 2
    assert [(rule.migration_result, rule.reason) for rule in filtered_page.rules] == [
        (
            ReportRuleMigrationResult.FAILED,
            "SD-WAN rejected policy: destination is invalid",
        )
    ]
    assert empty_page is not None
    assert empty_page.rules == ()
    assert empty_page.total == 0
    assert missing_page is None


@pytest.mark.asyncio
async def test_delete_report_by_id_cascades_to_report_rules(
    report_factory: Callable[..., Report],
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
    db_session: AsyncSession,
) -> None:
    report = report_factory(priorities=(10, 20))
    async with reports_uow_factory() as uow:
        await uow.reports.save_report(report)
        await uow.commit()

    async with reports_uow_factory() as uow:
        await uow.reports.delete_report_by_id(report.id)
        await uow.commit()

    rule_count = await db_session.scalar(
        text("SELECT count(*) FROM report_rule WHERE report_id = :report_id"),
        {"report_id": report.id},
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM report WHERE id = :report_id"),
            {"report_id": report.id},
        )
        == 0
    )
    assert rule_count == 0


@pytest.mark.asyncio
async def test_failed_rule_insert_rolls_back_report_header(
    report_factory: Callable[..., Report],
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
    db_session: AsyncSession,
) -> None:
    persisted = report_factory()
    async with reports_uow_factory() as uow:
        await uow.reports.save_report(persisted)
        await uow.commit()

    conflicting = report_factory(title="Conflicting")
    assert persisted.rules is not None
    assert conflicting.rules is not None
    conflicting_rule = replace(
        conflicting.rules[0],
        id=persisted.rules[0].id,
        report_id=conflicting.id,
    )
    conflicting = replace(conflicting, rules=(conflicting_rule,))

    with pytest.raises(IntegrityError):
        async with reports_uow_factory() as uow:
            await uow.reports.save_report(conflicting)

    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM report WHERE id = :report_id"),
            {"report_id": conflicting.id},
        )
        == 0
    )


@pytest.mark.asyncio
async def test_profile_with_reports_cannot_be_deleted(
    csp_profile_id: UUID,
    report_factory: Callable[..., Report],
    reports_uow_factory: Callable[[], ReportsUnitOfWork],
    db_session: AsyncSession,
) -> None:
    report = report_factory()
    async with reports_uow_factory() as uow:
        await uow.reports.save_report(report)
        await uow.commit()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("DELETE FROM csp_profile WHERE id = :profile_id"),
            {"profile_id": csp_profile_id},
        )
        await db_session.commit()

    await db_session.rollback()
