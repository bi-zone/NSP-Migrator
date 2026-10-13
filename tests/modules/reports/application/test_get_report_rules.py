from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.querying import Pagination
from app.modules.reports.application.dto import PaginationDTO, ReportRuleDTO
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesQuery,
    GetReportRulesUseCase,
)
from app.modules.reports.domain.entities import ReportRule
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError
from app.modules.reports.ports.report_repository import (
    ReportRuleFilters,
    ReportRulesPage,
)


class _ReportsRepository:
    def __init__(self, page: ReportRulesPage | None) -> None:
        self.page = page
        self.calls: list[tuple[UUID, Pagination, ReportRuleFilters]] = []

    async def list_report_rules(
        self,
        report_id: UUID,
        pagination: Pagination,
        *,
        filters: ReportRuleFilters,
    ) -> ReportRulesPage | None:
        self.calls.append((report_id, pagination, filters))
        return self.page


class _Uow:
    def __init__(self, reports: _ReportsRepository) -> None:
        self.session = None
        self.reports = reports

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    def __call__(self, reuse_session: bool = False) -> _Uow:
        return self

    async def commit(self) -> None:
        pass


def _rule(*, report_id: UUID) -> ReportRule:
    return ReportRule(
        id=uuid4(),
        report_id=report_id,
        policy_name="allow-web",
        action=ReportRuleAction.ACCEPT,
        priority=10,
        src_zone_names=("LAN",),
        dst_zone_names=("WAN",),
        src_addr_values=("10.10.0.0/24",),
        dst_addr_values=("203.0.113.10",),
        service_values=("tcp/443",),
        migration_result=ReportRuleMigrationResult.PUSHED,
        reason="Success",
    )


@pytest.mark.asyncio
async def test_get_report_rules_forwards_query_and_projects_policy_data() -> None:
    report_id = uuid4()
    rule = _rule(report_id=report_id)
    repository = _ReportsRepository(ReportRulesPage(rules=(rule,), total=3))
    use_case = GetReportRulesUseCase(_Uow(repository))  # type: ignore[arg-type]
    filters = ReportRuleFilters(
        search_by_policy_name="web",
        search_by_object_value="10.10",
        migration_results=(
            ReportRuleMigrationResult.PUSHED,
            ReportRuleMigrationResult.FAILED,
        ),
    )
    pagination = Pagination(limit=25, offset=50)

    result = await use_case.execute(
        GetReportRulesQuery(
            report_id=report_id,
            filters=filters,
            pagination=pagination,
        )
    )

    assert repository.calls == [(report_id, pagination, filters)]
    assert result.pagination == PaginationDTO(limit=25, offset=50, total=3)
    assert result.rules == [
        ReportRuleDTO(
            policy_name="allow-web",
            action=ReportRuleAction.ACCEPT,
            priority=10,
            src_zone_names=("LAN",),
            dst_zone_names=("WAN",),
            src_addr_values=("10.10.0.0/24",),
            dst_addr_values=("203.0.113.10",),
            service_values=("tcp/443",),
            migration_result=ReportRuleMigrationResult.PUSHED,
            reason="Success",
        )
    ]


@pytest.mark.asyncio
async def test_get_report_rules_returns_empty_page_for_existing_report() -> None:
    report_id = uuid4()
    repository = _ReportsRepository(ReportRulesPage(rules=(), total=0))
    use_case = GetReportRulesUseCase(_Uow(repository))  # type: ignore[arg-type]

    result = await use_case.execute(GetReportRulesQuery(report_id=report_id))

    assert result.rules == []
    assert result.pagination == PaginationDTO(limit=None, offset=0, total=0)
    assert repository.calls == [(report_id, Pagination(), ReportRuleFilters())]


@pytest.mark.asyncio
async def test_get_report_rules_raises_not_found_for_missing_report() -> None:
    report_id = uuid4()
    repository = _ReportsRepository(None)
    use_case = GetReportRulesUseCase(_Uow(repository))  # type: ignore[arg-type]

    with pytest.raises(ReportsModuleNotFoundError, match=str(report_id)):
        await use_case.execute(GetReportRulesQuery(report_id=report_id))

    assert repository.calls == [(report_id, Pagination(), ReportRuleFilters())]
