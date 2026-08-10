from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.ports.uow import ExecuteUnitOfWorkPort


@dataclass(frozen=True, slots=True)
class GetExecutePlanRulesQuery:
    execute_plan_id: UUID
    match_status: RuleMatchStatus | None = None


@dataclass(frozen=True, slots=True)
class GetExecutePlanRulesResult:
    plan_rules: list[ExecutePlanRule]


class GetExecutePlanRulesUseCase:
    """Read prepared execute plan rules from persistence."""

    def __init__(self, uow: ExecuteUnitOfWorkPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self,
        query: GetExecutePlanRulesQuery,
    ) -> GetExecutePlanRulesResult:
        """Return plan rules for UI/API, optionally filtered by match status."""
        plan_rules: list[ExecutePlanRule] = await self.uow.plan_rule_repo.list_by_plan(
            plan_id=query.execute_plan_id,
            match_status=query.match_status,
        )
        return GetExecutePlanRulesResult(plan_rules)
