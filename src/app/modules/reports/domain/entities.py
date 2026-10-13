from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.modules.common.domain.utils import get_utc_now
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.exceptions import ReportsModuleDomainValidationError
from app.modules.reports.domain.value_objects import (
    ReportEnvironmentSnapshot,
    ReportRuleSnapshot,
)


@dataclass(frozen=True, slots=True)
class ReportRule:
    """One immutable policy outcome belonging to a migration report."""

    id: UUID
    report_id: UUID
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

    @classmethod
    def create(cls, *, report_id: UUID, snapshot: ReportRuleSnapshot) -> Self:
        return cls(
            id=uuid4(),
            report_id=report_id,
            policy_name=snapshot.policy_name,
            action=snapshot.action,
            priority=snapshot.priority,
            src_zone_names=snapshot.src_zone_names,
            dst_zone_names=snapshot.dst_zone_names,
            src_addr_values=snapshot.src_addr_values,
            dst_addr_values=snapshot.dst_addr_values,
            service_values=snapshot.service_values,
            migration_result=snapshot.migration_result,
            reason=snapshot.reason,
        )


@dataclass(frozen=True, slots=True)
class Report:
    """Immutable aggregate recording one completed SD-WAN migration attempt."""

    id: UUID
    title: str
    created_at: datetime
    csp_profile_id: UUID
    commit_id: int | None
    environment: ReportEnvironmentSnapshot
    rules: tuple[ReportRule, ...] | None = None

    @classmethod
    def create(
        cls,
        *,
        scope_title: str,
        csp_profile_id: UUID,
        environment: ReportEnvironmentSnapshot,
        rule_snapshots: tuple[ReportRuleSnapshot, ...],
        commit_id: int | None = None,
    ) -> Self:
        if not scope_title.strip():
            raise ReportsModuleDomainValidationError("scope_title must not be blank")
        if not rule_snapshots:
            raise ReportsModuleDomainValidationError(
                "report must contain at least one rule"
            )

        report_id = uuid4()
        created_at = get_utc_now()
        normalized_scope_title = scope_title.strip()
        return cls(
            id=report_id,
            title=_build_title(
                scope_title=normalized_scope_title,
                created_at=created_at,
            ),
            created_at=created_at,
            csp_profile_id=csp_profile_id,
            commit_id=commit_id,
            environment=environment,
            rules=tuple(
                ReportRule.create(report_id=report_id, snapshot=snapshot)
                for snapshot in rule_snapshots
            ),
        )

    def attach_rules(self, rules: tuple[ReportRule, ...]) -> Self:
        if not rules:
            raise ReportsModuleDomainValidationError(
                "report must contain at least one rule"
            )
        if any(rule.report_id != self.id for rule in rules):
            raise ReportsModuleDomainValidationError(
                "all report rules must belong to the report"
            )
        return replace(self, rules=rules)


def _build_title(*, scope_title: str, created_at: datetime) -> str:
    """Make the report title distinct for repeated scope executions."""
    return f"{scope_title} — {created_at.strftime('%d.%m.%Y-%H:%M:%S')}"
