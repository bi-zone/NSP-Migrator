from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.execute.domain.entities import (
    ExecutePlan,
    ExecutePlanRule,
)
from app.modules.execute.domain.enums import RuleMatchStatus


class ExecutePlanRepositoryPort(IAsyncRepository[ExecutePlan, UUID]):
    @abstractmethod
    async def add_plan(self, plan: ExecutePlan) -> ExecutePlan: ...

    @abstractmethod
    async def get_plan(self, plan_id: UUID) -> ExecutePlan | None: ...


class ExecutePlanRuleRepositoryPort(IAsyncRepository[ExecutePlanRule, UUID]):
    @abstractmethod
    async def add_plan_rule(self, plan_rule: ExecutePlanRule) -> ExecutePlanRule: ...

    @abstractmethod
    async def add_plan_rules_bulk(self, plan_rules: list[ExecutePlanRule]) -> None: ...

    @abstractmethod
    async def get_plan_rule(self, plan_rule_id: UUID) -> ExecutePlanRule | None: ...

    @abstractmethod
    async def list_by_plan(
        self,
        plan_id: UUID,
        match_status: RuleMatchStatus | None = None,
    ) -> list[ExecutePlanRule]: ...

    @abstractmethod
    async def save(self, plan_rule: ExecutePlanRule) -> None: ...
