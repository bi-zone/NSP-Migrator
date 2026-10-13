from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.interfaces.cache import RuntimeCacheStorePort
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus, RulePushStatus
from app.modules.execute.ports.repositories import ExecuteRepositoryPort

_EXECUTE_PLAN_NAMESPACE = "execute.plan"


@dataclass(frozen=True, slots=True)
class _ExecutePlanCacheEntry:
    plan: ExecutePlan
    rules: dict[UUID, ExecutePlanRule]


class RuntimeCacheExecuteRepository(ExecuteRepositoryPort):
    """
    Runtime-cache repository over one execute plan graph entry.

    The implementation performs synchronous in-process cache operations under
    the hood. Public methods stay async to satisfy the module repository port
    and keep application use cases independent from the current storage backend:
    the same port can later be backed by async storage without changing callers.
    """

    def __init__(self, cache_store: RuntimeCacheStorePort) -> None:
        self._cache_store = cache_store

    def _get_plan_entry(
        self,
        plan_id: UUID,
        *,
        touch: bool,
    ) -> _ExecutePlanCacheEntry | None:
        return self._cache_store.get(
            _EXECUTE_PLAN_NAMESPACE,
            plan_id,
            touch=touch,
        )

    def _set_plan_entry(
        self,
        plan_id: UUID,
        entry: _ExecutePlanCacheEntry,
    ) -> None:
        self._cache_store.set(
            _EXECUTE_PLAN_NAMESPACE,
            plan_id,
            entry,
        )

    async def add_plan_with_rules(
        self,
        *,
        plan: ExecutePlan,
        rules: list[ExecutePlanRule],
    ) -> ExecutePlan:
        if self._get_plan_entry(plan.id, touch=False) is not None:
            raise ValueError(f"Execute plan {plan.id} already exists")

        rules_by_id: dict[UUID, ExecutePlanRule] = {}
        for rule in rules:
            if rule.execute_plan_id != plan.id:
                raise ValueError("ExecutePlanRule belongs to another plan")
            if rule.id in rules_by_id:
                raise ValueError(f"Execute plan rule {rule.id} already exists")
            rules_by_id[rule.id] = rule

        self._set_plan_entry(
            plan.id,
            _ExecutePlanCacheEntry(
                plan=plan,
                rules=rules_by_id,
            ),
        )
        return plan

    async def get_plan(self, plan_id: UUID) -> ExecutePlan | None:
        entry = self._get_plan_entry(plan_id, touch=True)
        if entry is None:
            return None

        return entry.plan

    async def update_plan(self, *, plan: ExecutePlan) -> ExecutePlan:
        entry = self._get_plan_entry(plan.id, touch=True)
        if entry is None:
            raise ValueError(f"Execute plan {plan.id} not found")

        self._set_plan_entry(
            plan.id,
            _ExecutePlanCacheEntry(plan=plan, rules=entry.rules),
        )
        return plan

    async def update_plan_rule(self, *, rule: ExecutePlanRule) -> ExecutePlanRule:
        entry = self._get_plan_entry(rule.execute_plan_id, touch=True)
        if entry is None:
            raise ValueError(f"Execute plan {rule.execute_plan_id} not found")
        if rule.id not in entry.rules:
            raise ValueError(f"Execute plan rule {rule.id} not found")

        updated_rules = entry.rules.copy()
        updated_rules[rule.id] = rule
        self._set_plan_entry(
            rule.execute_plan_id,
            _ExecutePlanCacheEntry(plan=entry.plan, rules=updated_rules),
        )
        return rule

    async def list_plan_rules(
        self,
        *,
        plan_id: UUID,
        match_status: RuleMatchStatus | None = None,
        push_statuses: set[RulePushStatus] | None = None,
    ) -> list[ExecutePlanRule]:
        entry = self._get_plan_entry(plan_id, touch=True)
        if entry is None:
            return []

        def _matches_filters(rule: ExecutePlanRule) -> bool:
            if match_status is not None and rule.match_status != match_status:
                return False

            if push_statuses is not None and rule.push_status not in push_statuses:
                return False

            return True

        return sorted(
            filter(_matches_filters, entry.rules.values()),
            key=lambda rule: rule.priority,
        )
