from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
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


@pytest.fixture
def reports_uow_factory(
    session_factory: SQLAlchemySessionFactory,
) -> Callable[[], ReportsUnitOfWork]:
    def _factory() -> ReportsUnitOfWork:
        return ReportsUnitOfWork(session_factory)

    return _factory


@pytest_asyncio.fixture
async def csp_profile_id(db_session: AsyncSession) -> UUID:
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


@pytest.fixture
def report_factory(csp_profile_id: UUID) -> Callable[..., Report]:
    def _factory(
        *,
        title: str = "Branch migration",
        created_at: datetime | None = None,
        priorities: tuple[int, ...] = (10,),
    ) -> Report:
        report = Report.create(
            scope_title=title,
            csp_profile_id=csp_profile_id,
            environment=ReportEnvironmentSnapshot(
                project_name="Firewall migration",
                vpc_id="vpc-1",
                target_name="Branch gateway",
                target_id="target-1",
            ),
            rule_snapshots=tuple(
                ReportRuleSnapshot(
                    policy_name=f"policy-{priority}",
                    action=ReportRuleAction.ACCEPT,
                    priority=priority,
                    src_zone_names=("LAN",),
                    dst_zone_names=("WAN",),
                    src_addr_values=("10.10.0.0/24",),
                    dst_addr_values=("203.0.113.10",),
                    service_values=("tcp/443",),
                    migration_result=ReportRuleMigrationResult.PUSHED,
                    reason="Success",
                )
                for priority in priorities
            ),
        )
        if created_at is None:
            return report
        return replace(
            report,
            title=f"{title} — {created_at.isoformat(timespec='seconds')}",
            created_at=created_at.astimezone(UTC),
        )

    return _factory
