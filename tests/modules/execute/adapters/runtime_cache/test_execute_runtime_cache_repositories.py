from uuid import uuid4

import pytest

from app.infrastructure.cache import InMemoryTTLStore
from app.modules.execute.adapters.runtime_cache import RuntimeCacheExecuteRepository
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import (
    CoverageField,
    ExecutePlanPushStatus,
    RuleMatchStatus,
    RulePushStatus,
    SdwanRuleAction,
)
from app.modules.execute.domain.value_objects import (
    CoverageDetail,
    CoverageValue,
    PlannedRuleDraft,
)


def _repository() -> RuntimeCacheExecuteRepository:
    return RuntimeCacheExecuteRepository(
        InMemoryTTLStore(ttl_seconds=60, max_entries=100)
    )


def _plan() -> ExecutePlan:
    return ExecutePlan.create(
        mapping_scope_id=uuid4(),
        catalog_fingerprint="catalog-fingerprint",
    )


def _draft() -> PlannedRuleDraft:
    return PlannedRuleDraft(
        name="planned-rule",
        action=SdwanRuleAction.ACCEPT,
        src_zones=[1],
        dst_zones=[2],
        src_addr_objects=[10],
        dst_addr_objects=[20],
        services=[100],
    )


def test_planned_rule_draft_json_round_trip_keeps_name() -> None:
    draft = _draft()

    restored = PlannedRuleDraft.from_dict(draft.to_dict())

    assert restored == draft


def _rule(
    plan: ExecutePlan,
    *,
    priority: int = 0,
    match_status: RuleMatchStatus = RuleMatchStatus.NEW,
    coverage_details: tuple[CoverageDetail, ...] = (),
) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=plan.id,
        mapping_scope_rule_id=uuid4(),
        priority=priority,
        draft=_draft(),
        matched_sdwan_rule_id=None,
        match_status=match_status,
        match_info="",
        coverage_details=coverage_details,
    )


@pytest.mark.asyncio
async def test_repository_stores_plan_with_rules() -> None:
    repository = _repository()
    plan = _plan()
    new_rule = _rule(plan, match_status=RuleMatchStatus.NEW)
    covered_rule = _rule(
        plan,
        match_status=RuleMatchStatus.COVERED_MATCH,
        coverage_details=(
            CoverageDetail(
                field=CoverageField.SERVICES,
                covering_value=CoverageValue(
                    object_id=100,
                    object_name="TCP_ANY",
                    value="tcp/1-65535",
                ),
                covered_values=(
                    CoverageValue(
                        object_id=101,
                        object_name="tcp/443",
                        value="tcp/443",
                    ),
                ),
            ),
        ),
    )

    stored = await repository.add_plan_with_rules(
        plan=plan,
        rules=[new_rule, covered_rule],
    )

    loaded_plan = await repository.get_plan(plan.id)
    plan_rules = await repository.list_plan_rules(plan_id=plan.id)

    assert stored == plan
    assert loaded_plan == plan
    assert plan_rules == [new_rule, covered_rule]


@pytest.mark.asyncio
async def test_repository_updates_plan_push_status() -> None:
    repository = _repository()
    plan = _plan()
    await repository.add_plan_with_rules(plan=plan, rules=[])

    updated_plan = await repository.update_plan(plan=plan.mark_push_executed())

    assert updated_plan.push_status == ExecutePlanPushStatus.EXECUTED
    assert await repository.get_plan(plan.id) == updated_plan


@pytest.mark.asyncio
async def test_repository_filters_plan_rules_by_match_status() -> None:
    repository = _repository()
    plan = _plan()
    new_rule = _rule(plan, match_status=RuleMatchStatus.NEW)
    matched_rule = _rule(plan, match_status=RuleMatchStatus.EXACT_MATCH)

    await repository.add_plan_with_rules(
        plan=plan,
        rules=[new_rule, matched_rule],
    )

    new_rules = await repository.list_plan_rules(
        plan_id=plan.id,
        match_status=RuleMatchStatus.NEW,
    )

    assert new_rules == [new_rule]


@pytest.mark.asyncio
async def test_repository_filters_plan_rules_by_push_statuses() -> None:
    repository = _repository()
    plan = _plan()
    pending_rule = _rule(plan)
    succeeded_rule = _rule(plan).mark_push_succeeded(901)
    failed_rule = _rule(plan).mark_push_failed("SD-WAN rejected policy")
    await repository.add_plan_with_rules(
        plan=plan,
        rules=[pending_rule, succeeded_rule, failed_rule],
    )

    retryable_rules = await repository.list_plan_rules(
        plan_id=plan.id,
        push_statuses={RulePushStatus.PENDING, RulePushStatus.FAILED},
    )

    assert retryable_rules == [pending_rule, failed_rule]


@pytest.mark.asyncio
async def test_repository_filters_plan_rules_by_match_and_push_statuses() -> None:
    repository = _repository()
    plan = _plan()
    pending_new_rule = _rule(plan)
    failed_new_rule = _rule(plan).mark_push_failed("SD-WAN rejected policy")
    succeeded_new_rule = _rule(plan).mark_push_succeeded(901)
    failed_matched_rule = _rule(
        plan,
        match_status=RuleMatchStatus.EXACT_MATCH,
    ).mark_push_failed("SD-WAN rejected policy")
    await repository.add_plan_with_rules(
        plan=plan,
        rules=[
            pending_new_rule,
            failed_new_rule,
            succeeded_new_rule,
            failed_matched_rule,
        ],
    )

    rules_for_push = await repository.list_plan_rules(
        plan_id=plan.id,
        match_status=RuleMatchStatus.NEW,
        push_statuses={RulePushStatus.PENDING, RulePushStatus.FAILED},
    )

    assert rules_for_push == [pending_new_rule, failed_new_rule]


@pytest.mark.asyncio
async def test_repository_sorts_filtered_plan_rules_by_canonical_priority() -> None:
    repository = _repository()
    plan = _plan()
    later_rule = _rule(plan, priority=20)
    first_earlier_rule = _rule(plan, priority=10)
    second_earlier_rule = _rule(plan, priority=10)
    matched_rule = _rule(plan, priority=5, match_status=RuleMatchStatus.EXACT_MATCH)
    await repository.add_plan_with_rules(
        plan=plan,
        rules=[later_rule, matched_rule, first_earlier_rule, second_earlier_rule],
    )

    rules_for_push = await repository.list_plan_rules(
        plan_id=plan.id,
        match_status=RuleMatchStatus.NEW,
        push_statuses={RulePushStatus.PENDING},
    )

    assert rules_for_push == [
        first_earlier_rule,
        second_earlier_rule,
        later_rule,
    ]


@pytest.mark.asyncio
async def test_repository_updates_push_outcome_for_plan_rule() -> None:
    repository = _repository()
    plan = _plan()
    rule = _rule(plan)
    await repository.add_plan_with_rules(plan=plan, rules=[rule])

    updated_rule = await repository.update_plan_rule(rule=rule.mark_push_succeeded(901))
    loaded_rules = await repository.list_plan_rules(plan_id=plan.id)

    assert updated_rule.push_status == RulePushStatus.SUCCEEDED
    assert updated_rule.pushed_sdwan_rule_id == 901
    assert updated_rule.push_error is None
    assert loaded_rules == [updated_rule]


@pytest.mark.asyncio
async def test_repository_returns_empty_values_for_missing_plan() -> None:
    repository = _repository()
    plan_id = uuid4()

    loaded_plan = await repository.get_plan(plan_id)
    plan_rules = await repository.list_plan_rules(plan_id=plan_id)

    assert loaded_plan is None
    assert plan_rules == []


@pytest.mark.asyncio
async def test_repository_rejects_duplicate_plan() -> None:
    repository = _repository()
    plan = _plan()

    await repository.add_plan_with_rules(plan=plan, rules=[])

    with pytest.raises(ValueError, match="already exists"):
        await repository.add_plan_with_rules(plan=plan, rules=[])


@pytest.mark.asyncio
async def test_repository_rejects_rule_from_another_plan() -> None:
    repository = _repository()
    plan = _plan()
    another_plan = _plan()

    with pytest.raises(ValueError, match="another plan"):
        await repository.add_plan_with_rules(
            plan=plan,
            rules=[_rule(another_plan)],
        )


@pytest.mark.asyncio
async def test_repository_rejects_duplicate_rule_ids() -> None:
    repository = _repository()
    plan = _plan()
    rule = _rule(plan)

    with pytest.raises(ValueError, match="already exists"):
        await repository.add_plan_with_rules(
            plan=plan,
            rules=[rule, rule],
        )
