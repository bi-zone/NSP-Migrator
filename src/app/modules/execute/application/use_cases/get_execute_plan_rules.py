from dataclasses import dataclass
from uuid import UUID

from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.ports.repositories import ExecuteRepositoryPort


@dataclass(frozen=True, slots=True)
class GetExecutePlanRulesQuery:
    execute_plan_id: UUID
    match_status: RuleMatchStatus | None = None


@dataclass(frozen=True, slots=True)
class GetExecutePlanRulesResult:
    plan_rules: list[ExecutePlanRule]


class GetExecutePlanRulesUseCase:
    """Read prepared execute plan rules from persistence."""

    def __init__(self, execute_repo: ExecuteRepositoryPort) -> None:
        self.execute_repo = execute_repo

    async def execute(
        self,
        query: GetExecutePlanRulesQuery,
    ) -> GetExecutePlanRulesResult:
        """Return plan rules for UI/API, optionally filtered by match status."""
        plan_rules: list[ExecutePlanRule] = await self.execute_repo.list_plan_rules(
            plan_id=query.execute_plan_id,
            match_status=query.match_status,
        )
        return GetExecutePlanRulesResult(plan_rules)
