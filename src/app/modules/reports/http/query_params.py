"""Query parameter models for report-header history."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.fastapi.querying import PaginationQuery
from app.core.querying import SortDirection, Sorting
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersQuery,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesQuery,
)
from app.modules.reports.domain.enums import ReportRuleMigrationResult
from app.modules.reports.ports.report_repository import (
    ReportHeaderFilters,
    ReportHeaderSortField,
    ReportRuleFilters,
)


class ReportHeadersPaginationQuery(PaginationQuery):
    """Pagination constraints for report-header history."""

    limit: Annotated[
        int | None,
        Field(
            ge=1,
            le=200,
            description="Page size, omit to return all matching reports.",
        ),
    ] = None


class ReportHeadersSortingQuery(BaseModel):
    """Whitelisted sorting parameters for report-header history."""

    sort_by: Annotated[
        ReportHeaderSortField,
        Field(description="Only report creation time is currently sortable."),
    ] = ReportHeaderSortField.CREATED_AT
    sort_dir: Annotated[
        SortDirection,
        Field(description="Sort direction."),
    ] = SortDirection.DESC

    def to_sorting(self) -> Sorting[ReportHeaderSortField]:
        """Map whitelisted HTTP sorting to the application value object."""
        return Sorting(field=self.sort_by, direction=self.sort_dir)


class ReportHeadersFilterQuery(BaseModel):
    """HTTP names and validation for report-header filters."""

    search_by_name: Annotated[
        str | None,
        Field(description="Case-insensitive partial match for report title."),
    ] = None
    created_from: Annotated[
        date | None,
        Field(description="UTC calendar date lower bound."),
    ] = None
    created_to: Annotated[
        date | None,
        Field(description="UTC calendar date upper bound."),
    ] = None
    csp_profile_id: Annotated[
        UUID | None,
        Field(description="CSP profile that produced the report."),
    ] = None
    vpc_id: Annotated[
        str | None,
        Field(description="VPC identifier captured in the report."),
    ] = None
    target_id: Annotated[
        list[str] | None,
        Field(description="One or more installation device identifiers."),
    ] = None

    def to_filters(self) -> ReportHeaderFilters:
        """Map HTTP fields to the Reports repository contract."""
        return ReportHeaderFilters(
            search_by_name=self.search_by_name,
            created_from=self.created_from,
            created_to=self.created_to,
            csp_profile_id=self.csp_profile_id,
            vpc_id=self.vpc_id,
            target_ids=tuple(self.target_id or ()),
        )


class ReportHeadersQueryParams(
    ReportHeadersPaginationQuery,
    ReportHeadersSortingQuery,
    ReportHeadersFilterQuery,
):
    """Flat query model composed from reusable report-list concerns."""

    model_config = ConfigDict(extra="forbid")

    def to_application_query(self) -> GetReportHeadersQuery:
        """Map transport parameters explicitly to the Reports use case."""
        return GetReportHeadersQuery(
            filters=self.to_filters(),
            sorting=self.to_sorting(),
            pagination=self.to_pagination(),
        )


class ReportRulesPaginationQuery(PaginationQuery):
    """Pagination constraints for saved policy outcomes."""

    limit: Annotated[
        int | None,
        Field(
            ge=1,
            le=200,
            description="Page size, omit to return all matching policies.",
        ),
    ] = None


class ReportRulesFilterQuery(BaseModel):
    """HTTP names and validation for one report's policy filters."""

    search_by_policy_name: Annotated[
        str | None,
        Field(description="Case-insensitive partial match for policy name."),
    ] = None
    search_by_object_value: Annotated[
        str | None,
        Field(
            description=(
                "Case-insensitive partial match for a saved zone, address, "
                "or service value."
            )
        ),
    ] = None
    migration_result: Annotated[
        list[ReportRuleMigrationResult] | None,
        Field(description="One or more saved policy migration statuses."),
    ] = None

    def to_filters(self) -> ReportRuleFilters:
        """Map HTTP fields to the Reports repository contract."""
        return ReportRuleFilters(
            search_by_policy_name=self.search_by_policy_name,
            search_by_object_value=self.search_by_object_value,
            migration_results=tuple(self.migration_result or ()),
        )


class ReportRulesQueryParams(ReportRulesPaginationQuery, ReportRulesFilterQuery):
    """Flat query model for one report's policy results."""

    model_config = ConfigDict(extra="forbid")

    def to_application_query(self, report_id: UUID) -> GetReportRulesQuery:
        """Map transport parameters explicitly to the Reports use case."""
        return GetReportRulesQuery(
            report_id=report_id,
            filters=self.to_filters(),
            pagination=self.to_pagination(),
        )
