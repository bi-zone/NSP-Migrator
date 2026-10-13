"""OpenAPI response models for report-header history."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.fastapi.querying import PaginationResponse
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)


class CSPProfileHeaderResponse(BaseModel):
    """CSP profile summary attached to a report header."""

    id: UUID = Field(description="CSP profile identifier.")
    name: str = Field(description="Current CSP profile name.")
    base_url: str = Field(description="Current CSP profile base URL.")

    model_config = ConfigDict(from_attributes=True)


class ReportHeaderResponse(BaseModel):
    """Historical report metadata without rule-result payload."""

    id: UUID = Field(description="Report identifier.")
    title: str = Field(description="Migration report name.")
    csp_profile: CSPProfileHeaderResponse = Field(
        description="CSP profile used for the migration."
    )
    project_name: str = Field(description="Project name captured at migration time.")
    vpc_id: str = Field(
        description="Project / VPC identifier captured at migration time."
    )
    target_name: str = Field(
        description="Installation device name captured at migration time."
    )
    target_id: str = Field(description="Installation device identifier.")
    created_at: datetime = Field(description="UTC time when the report was created.")

    model_config = ConfigDict(from_attributes=True)


class ReportHeadersListResponse(BaseModel):
    """Paginated report-header history."""

    reports: list[ReportHeaderResponse] = Field(
        description="Reports matching filters and sorting."
    )
    pagination: PaginationResponse = Field(
        description="Pagination totals for the report slice."
    )

    model_config = ConfigDict(from_attributes=True)


class ReportRuleResponse(BaseModel):
    """One saved policy outcome in a migration report."""

    policy_name: str = Field(description="Saved policy name.")
    action: ReportRuleAction = Field(description="Saved policy action.")
    priority: int = Field(description="Saved policy priority.")
    src_zone_names: list[str] = Field(description="Saved source-zone names.")
    dst_zone_names: list[str] = Field(description="Saved destination-zone names.")
    src_addr_values: list[str] = Field(description="Saved source-address values.")
    dst_addr_values: list[str] = Field(description="Saved destination-address values.")
    service_values: list[str] = Field(description="Saved service values.")
    migration_result: ReportRuleMigrationResult = Field(
        description="Saved migration outcome."
    )
    reason: str = Field(description="Saved migration outcome explanation.")

    model_config = ConfigDict(from_attributes=True)


class ReportRulesListResponse(BaseModel):
    """Paginated saved policy outcomes for one migration report."""

    rules: list[ReportRuleResponse] = Field(
        description="Policies matching the report-rule filters."
    )
    pagination: PaginationResponse = Field(
        description="Pagination totals for the policy slice."
    )

    model_config = ConfigDict(from_attributes=True)
