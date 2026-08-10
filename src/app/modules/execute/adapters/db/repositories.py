from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.execute.adapters.db.mappers import (
    ExecutePlanDomainModelMapper,
    ExecutePlanRuleDomainModelMapper,
)
from app.modules.execute.adapters.db.models import (
    ExecutePlanModel,
    ExecutePlanRuleModel,
)
from app.modules.execute.domain.entities import (
    ExecutePlan,
    ExecutePlanRule,
)
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.ports.repositories import (
    ExecutePlanRepositoryPort,
    ExecutePlanRuleRepositoryPort,
)


class SqlAlchemyExecutePlanRepository(
    SqlAlchemyRepository[ExecutePlanModel, UUID],
    ExecutePlanRepositoryPort,
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExecutePlanModel)
        self.mapper = ExecutePlanDomainModelMapper()

    async def add_plan(self, plan: ExecutePlan) -> ExecutePlan:
        """Persist a prepared execute plan."""
        await self.add(self.mapper.to_model(plan))
        return plan

    async def get_plan(self, plan_id: UUID) -> ExecutePlan | None:
        """Return execute plan by UUID or None."""
        plan: ExecutePlanModel | None = await self.get_by_id(plan_id)
        if not plan:
            return None
        return self.mapper.to_domain(plan)


class SqlAlchemyExecutePlanRuleRepository(
    SqlAlchemyRepository[ExecutePlanRuleModel, UUID],
    ExecutePlanRuleRepositoryPort,
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExecutePlanRuleModel)
        self.mapper = ExecutePlanRuleDomainModelMapper()

    async def add_plan_rule(self, plan_rule: ExecutePlanRule) -> ExecutePlanRule:
        """Persist one execute plan rule."""
        await self.add(self.mapper.to_model(plan_rule))
        return plan_rule

    async def add_plan_rules_bulk(self, plan_rules: list[ExecutePlanRule]) -> None:
        """Persist prepared execute plan rules in one flush."""
        await self.add_bulk([self.mapper.to_model(rule) for rule in plan_rules])

    async def get_plan_rule(self, plan_rule_id: UUID) -> ExecutePlanRule | None:
        """Return execute plan rule by UUID or None."""
        plan_rule: ExecutePlanRuleModel | None = await self.get_by_id(plan_rule_id)
        if not plan_rule:
            return None
        return self.mapper.to_domain(plan_rule)

    async def list_by_plan(
        self,
        plan_id: UUID,
        match_status: RuleMatchStatus | None = None,
    ) -> list[ExecutePlanRule]:
        """List plan rules, optionally filtered by comparison status."""
        stmt = select(self.model).where(self.model.execute_plan_id == plan_id)

        if match_status:
            stmt = stmt.where(self.model.match_status == match_status.value)

        res = await self.session.execute(stmt)
        plan_rules = res.scalars().all()
        return [self.mapper.to_domain(rule) for rule in plan_rules]

    async def save(self, plan_rule: ExecutePlanRule) -> None:
        """Merge changed plan rule into current session."""
        await self.session.merge(self.mapper.to_model(plan_rule))
        await self.session.flush()
