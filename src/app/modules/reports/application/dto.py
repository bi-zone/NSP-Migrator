"""Read projections returned by Reports application use cases."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO


@dataclass(frozen=True, slots=True)
class ReportHeaderDTO:
    """One report header without its ReportRule payload."""

    id: UUID
    title: str
    csp_profile: CSPProfileHeaderDTO
    project_name: str
    vpc_id: str
    target_name: str
    target_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReportRuleDTO:
    """One saved policy outcome displayed in a report detail list."""

    policy_name: str
    action: ReportRuleAction
    priority: int
    src_zone_names: tuple[str, ...]
    dst_zone_names: tuple[str, ...]
    src_addr_values: tuple[str, ...]
    dst_addr_values: tuple[str, ...]
    service_values: tuple[str, ...]
    migration_result: ReportRuleMigrationResult
    reason: str


@dataclass(frozen=True, slots=True)
class PaginationDTO:
    """Pagination metadata for Reports read projections."""

    limit: int | None
    offset: int
    total: int
