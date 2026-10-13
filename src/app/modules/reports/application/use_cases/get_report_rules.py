"""List saved policy outcomes belonging to one migration report."""

from dataclasses import dataclass, field
from uuid import UUID

from app.core.querying import Pagination
from app.infrastructure.db.transactional import async_transactional
from app.modules.reports.application.dto import PaginationDTO, ReportRuleDTO
from app.modules.reports.application.mappers import report_rule_to_dto
from app.modules.reports.domain.exceptions import ReportsModuleNotFoundError
from app.modules.reports.ports.report_repository import (
    ReportRuleFilters,
    ReportRulesPage,
)
from app.modules.reports.ports.uow import ReportsUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class GetReportRulesQuery:
    """One report identifier with filters and page bounds for its policies."""

    report_id: UUID
    filters: ReportRuleFilters = field(default_factory=ReportRuleFilters)
    pagination: Pagination = field(default_factory=Pagination)


@dataclass(frozen=True, slots=True)
class GetReportRulesResult:
    rules: list[ReportRuleDTO]
    pagination: PaginationDTO


class GetReportRulesUseCase:
    """Read filtered report policies without loading the Report aggregate."""

    def __init__(self, uow: ReportsUnitOfWorkPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetReportRulesQuery) -> GetReportRulesResult:
        page: ReportRulesPage | None = await self.uow.reports.list_report_rules(
            query.report_id,
            query.pagination,
            filters=query.filters,
        )
        if page is None:
            raise ReportsModuleNotFoundError(f"Report {query.report_id} not found")

        return GetReportRulesResult(
            rules=[report_rule_to_dto(rule) for rule in page.rules],
            pagination=PaginationDTO(
                limit=query.pagination.limit,
                offset=query.pagination.offset,
                total=page.total,
            ),
        )
