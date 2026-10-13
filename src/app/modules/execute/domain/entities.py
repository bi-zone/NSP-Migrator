from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.modules.common.domain.utils import get_utc_now
from app.modules.execute.domain.enums import (
    ExecutePlanPushStatus,
    RuleMatchStatus,
    RulePushStatus,
)
from app.modules.execute.domain.value_objects import CoverageDetail, PlannedRuleDraft


@dataclass(frozen=True, slots=True)
class ExecutePlan:
    """Prepared execution plan for one mapping scope."""

    id: UUID
    mapping_scope_id: UUID
    catalog_fingerprint: str
    created_at: datetime
    push_status: ExecutePlanPushStatus

    @classmethod
    def create(
        cls,
        *,
        mapping_scope_id: UUID,
        catalog_fingerprint: str,
    ) -> Self:
        """Create a new plan aggregate with generated UUID."""
        return cls(
            id=uuid4(),
            mapping_scope_id=mapping_scope_id,
            catalog_fingerprint=catalog_fingerprint,
            created_at=get_utc_now(),
            push_status=ExecutePlanPushStatus.PENDING,
        )

    def mark_push_executed(self) -> Self:
        """Return the plan after its one permitted push has started."""
        return replace(self, push_status=ExecutePlanPushStatus.EXECUTED)


@dataclass(frozen=True, slots=True)
class ExecutePlanRule:
    """One planned SD-WAN rule with comparison result.

    The rule belongs to an execute plan and mirrors one mapping scope rule. The
    actual SD-WAN catalog used for comparison is not persisted here; only the
    planned draft, result and coverage delta are stored.
    """

    id: UUID
    execute_plan_id: UUID
    mapping_scope_rule_id: UUID
    priority: int
    draft: PlannedRuleDraft
    matched_sdwan_rule_id: int | None
    match_status: RuleMatchStatus
    match_info: str
    coverage_details: tuple[CoverageDetail, ...]
    push_status: RulePushStatus
    pushed_sdwan_rule_id: int | None
    push_error: str | None

    @classmethod
    def create(
        cls,
        *,
        execute_plan_id: UUID,
        mapping_scope_rule_id: UUID,
        priority: int,
        draft: PlannedRuleDraft,
        matched_sdwan_rule_id: int | None,
        match_status: RuleMatchStatus,
        match_info: str,
        coverage_details: tuple[CoverageDetail, ...] = (),
    ) -> Self:
        """Create a new plan rule with generated UUID."""
        return cls(
            id=uuid4(),
            execute_plan_id=execute_plan_id,
            mapping_scope_rule_id=mapping_scope_rule_id,
            priority=priority,
            draft=draft,
            match_status=match_status,
            matched_sdwan_rule_id=matched_sdwan_rule_id,
            match_info=match_info,
            coverage_details=coverage_details,
            push_status=RulePushStatus.PENDING,
            pushed_sdwan_rule_id=None,
            push_error=None,
        )

    def mark_push_succeeded(self, sdwan_rule_id: int) -> Self:
        """Return the rule with its confirmed SD-WAN creation outcome."""
        return replace(
            self,
            push_status=RulePushStatus.SUCCEEDED,
            pushed_sdwan_rule_id=sdwan_rule_id,
            push_error=None,
        )

    def mark_push_failed(self, error: str) -> Self:
        """Return the rule with its failed SD-WAN creation outcome."""
        return replace(
            self,
            push_status=RulePushStatus.FAILED,
            pushed_sdwan_rule_id=None,
            push_error=error,
        )
