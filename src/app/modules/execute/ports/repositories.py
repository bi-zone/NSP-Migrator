from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.execute.domain.entities import (
    ExecutePlan,
    ExecutePlanRule,
)
from app.modules.execute.domain.enums import RuleMatchStatus, RulePushStatus


class ExecuteRepositoryPort(ABC):
    """Repository for execute runtime data."""

    @abstractmethod
    async def add_plan_with_rules(
        self,
        *,
        plan: ExecutePlan,
        rules: list[ExecutePlanRule],
    ) -> ExecutePlan:
        """Persist prepared execute plan with its rules as one graph."""
        ...

    @abstractmethod
    async def get_plan(self, plan_id: UUID) -> ExecutePlan | None:
        """Return execute plan by id."""
        ...

    @abstractmethod
    async def update_plan(self, *, plan: ExecutePlan) -> ExecutePlan:
        """Persist a changed execute plan in its graph entry."""
        ...

    @abstractmethod
    async def update_plan_rule(self, *, rule: ExecutePlanRule) -> ExecutePlanRule:
        """Persist a changed execute-plan rule in its plan graph."""
        ...

    @abstractmethod
    async def list_plan_rules(
        self,
        *,
        plan_id: UUID,
        match_status: RuleMatchStatus | None = None,
        push_statuses: set[RulePushStatus] | None = None,
    ) -> list[ExecutePlanRule]:
        """Return execute plan rules, optionally filtered by match and push status."""
        ...
