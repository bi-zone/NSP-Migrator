from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.core.querying import Pagination, SortDirection, Sorting
from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.domain.enums import ReportRuleMigrationResult


@dataclass(frozen=True, slots=True)
class ReportHeadersPage:
    """One ordered report-header slice and the total number of reports."""

    reports: tuple[Report, ...]
    total: int


class ReportHeaderSortField(StrEnum):
    """Columns available for report-header ordering."""

    CREATED_AT = "created_at"


def default_report_header_sorting() -> Sorting[ReportHeaderSortField]:
    """Return the standard newest-first order for report-history lists."""
    return Sorting(
        field=ReportHeaderSortField.CREATED_AT,
        direction=SortDirection.DESC,
    )


@dataclass(frozen=True, slots=True)
class ReportHeaderFilters:
    """Filters over immutable report-header snapshots."""

    search_by_name: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    csp_profile_id: UUID | None = None
    vpc_id: str | None = None
    target_ids: tuple[str, ...] = field(default_factory=tuple)

    def normalized_search_by_name(self) -> str | None:
        """Return a trimmed title search or omit a blank value."""
        if self.search_by_name and self.search_by_name.strip():
            return self.search_by_name.strip()
        return None


@dataclass(frozen=True, slots=True)
class ReportRuleFilters:
    """Filters over saved policy outcomes belonging to one report."""

    search_by_policy_name: str | None = None
    search_by_object_value: str | None = None
    migration_results: tuple[ReportRuleMigrationResult, ...] = field(
        default_factory=tuple
    )

    def normalized_search_by_policy_name(self) -> str | None:
        """Return a trimmed policy-name search or omit a blank value."""
        return _normalized_search_value(self.search_by_policy_name)

    def normalized_search_by_object_value(self) -> str | None:
        """Return a trimmed object-value prefix search or omit a blank value."""
        return _normalized_search_value(self.search_by_object_value)


@dataclass(frozen=True, slots=True)
class ReportRulesPage:
    """One priority-ordered report-rule slice and its matching total."""

    rules: tuple[ReportRule, ...]
    total: int


class ReportsRepositoryPort(IAsyncRepository[Report, UUID], Protocol):
    """Persistence seam for the Report aggregate and its header listing."""

    async def save_report(self, report: Report) -> Report: ...

    async def get_report_by_id(self, report_id: UUID) -> Report | None: ...

    async def list_report_headers(
        self,
        pagination: Pagination,
        *,
        filters: ReportHeaderFilters,
        sorting: Sorting[ReportHeaderSortField],
    ) -> ReportHeadersPage: ...

    async def list_report_rules(
        self,
        report_id: UUID,
        pagination: Pagination,
        *,
        filters: ReportRuleFilters,
    ) -> ReportRulesPage | None:
        """List one report's rules, or return None when its header is absent."""
        ...

    async def delete_report_by_id(self, report_id: UUID) -> None: ...


def _normalized_search_value(value: str | None) -> str | None:
    if value and value.strip():
        return value.strip()
    return None
