from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.modules.common.domain.utils import get_utc_now
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.domain.value_objects import PlannedRuleDraft


@dataclass(slots=True)
class ExecutePlan:
    """Prepared execution plan for one mapping scope."""

    id: UUID
    mapping_scope_id: UUID
    created_at: datetime

    @classmethod
    def create(cls, mapping_scope_id: UUID) -> Self:
        """Create a new plan aggregate with generated UUID."""
        return cls(
            id=uuid4(),
            mapping_scope_id=mapping_scope_id,
            created_at=get_utc_now(),
        )


@dataclass(slots=True)
class ExecutePlanRule:
    """One planned SD-WAN rule with comparison result.

    The rule belongs to an execute plan and mirrors one mapping scope rule. The
    actual SD-WAN catalog used for comparison is not persisted here; only the
    planned draft and flat match result are stored.
    """

    id: UUID
    execute_plan_id: UUID
    mapping_scope_rule_id: UUID
    draft: PlannedRuleDraft
    matched_sdwan_rule_id: int | None
    match_status: RuleMatchStatus
    match_info: str

    @classmethod
    def create(
        cls,
        *,
        execute_plan_id: UUID,
        mapping_scope_rule_id: UUID,
        draft: PlannedRuleDraft,
        matched_sdwan_rule_id: int | None,
        match_status: RuleMatchStatus,
        match_info: str,
    ) -> Self:
        """Create a new plan rule with generated UUID."""
        return cls(
            id=uuid4(),
            execute_plan_id=execute_plan_id,
            mapping_scope_rule_id=mapping_scope_rule_id,
            draft=draft,
            match_status=match_status,
            matched_sdwan_rule_id=matched_sdwan_rule_id,
            match_info=match_info,
        )
