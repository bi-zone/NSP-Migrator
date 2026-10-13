from dataclasses import dataclass

from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)


@dataclass(frozen=True, slots=True)
class ReportEnvironmentSnapshot:
    """VPC and install-target values retained with a report."""

    project_name: str
    vpc_id: str
    target_name: str
    target_id: str


@dataclass(frozen=True, slots=True)
class ReportRuleSnapshot:
    """Resolved policy values and outcome before they receive report identity."""

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
