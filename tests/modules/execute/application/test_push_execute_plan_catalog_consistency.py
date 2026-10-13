from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanRulePriority,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import SdwanFullCatalog, SdwanZone
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesCommand,
    PushExecutePlanRulesUseCase,
)
from app.modules.execute.application.dto import CommitInfoDTO, PushRuleResultDTO
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import (
    ExecutePlanPushStatus,
    RuleMatchStatus,
    RulePushStatus,
    SdwanRuleAction,
)
from app.modules.execute.domain.value_objects import PlannedRuleDraft
from app.modules.execute.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.execute.ports.mapping_reader.schemas import MappingScopeData


class _ExecuteRepositoryStub:
    def __init__(self, plan: ExecutePlan, rules: list[ExecutePlanRule]) -> None:
        self._plan = plan
        self._rules = rules

    async def get_plan(self, plan_id: UUID) -> ExecutePlan | None:
        assert plan_id == self._plan.id
        return self._plan

    async def update_plan(self, *, plan: ExecutePlan) -> ExecutePlan:
        assert plan.id == self._plan.id
        self._plan = plan
        return plan

    async def update_plan_rule(self, *, rule: ExecutePlanRule) -> ExecutePlanRule:
        self._rules = [
            rule if existing_rule.id == rule.id else existing_rule
            for existing_rule in self._rules
        ]
        return rule

    async def list_plan_rules(
        self,
        *,
        plan_id: UUID,
        match_status: RuleMatchStatus | None = None,
        push_statuses: set[RulePushStatus] | None = None,
    ) -> list[ExecutePlanRule]:
        assert plan_id == self._plan.id
        return [
            rule
            for rule in self._rules
            if match_status is None or rule.match_status == match_status
            if push_statuses is None or rule.push_status in push_statuses
        ]


class _MappingReaderStub:
    def __init__(self, scope: MappingScopeData) -> None:
        self._scope = scope

    async def get_mapping_scope_data(self, mapping_scope_id: UUID) -> MappingScopeData:
        assert mapping_scope_id == self._scope.id
        return self._scope


class _GatewayStub:
    def __init__(
        self,
        catalog: SdwanFullCatalog,
        *,
        push_results: list[PushRuleResultDTO] | None = None,
    ) -> None:
        self._catalog = catalog
        self.push_results = push_results
        self.push_calls = 0
        self.push_kwargs: dict[str, object] | None = None
        self.pushed_plan_rules: list[list[ExecutePlanRule]] = []
        self.requested_rule_ids: list[int] | None = None
        self.commit_calls = 0

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return self._catalog

    async def push_rules(self, **kwargs: object) -> list[PushRuleResultDTO]:
        self.push_calls += 1
        self.push_kwargs = kwargs
        plan_rules = kwargs["plan_rules"]
        assert isinstance(plan_rules, list)
        self.pushed_plan_rules.append(plan_rules)
        if self.push_results is not None:
            return self.push_results
        return [
            PushRuleResultDTO(
                execute_plan_rule_id=plan_rules[0].id,
                rule_name=plan_rules[0].draft.name,
                sdwan_rule_id=901,
                error=None,
            )
        ]

    async def get_rules(self, rules_ids: list[int]) -> list:
        self.requested_rule_ids = rules_ids
        return []

    async def commit_csp_changes(self) -> CommitInfoDTO:
        self.commit_calls += 1
        return CommitInfoDTO(commit_id=1, name="test-commit", description="")


class _GatewayProviderStub:
    def __init__(self, gateway: _GatewayStub) -> None:
        self._gateway = gateway
        self.acquire_calls = 0

    @asynccontextmanager
    async def acquire(self, profile_id: UUID, vpc_id: str):
        self.acquire_calls += 1
        yield self._gateway


class _ReportsWriterStub:
    async def save_report(self, **kwargs: object) -> None:
        return None


def _catalog(*, zone_name: str) -> SdwanFullCatalog:
    return SdwanFullCatalog(
        zones=[
            SdwanZone(
                id=1,
                zone_id=1,
                name=zone_name,
                type=SdwanZoneType.LAN,
            )
        ],
        services=[],
        addr_objs=[],
        networks=[],
    )


def _plan(catalog: SdwanFullCatalog) -> ExecutePlan:
    return ExecutePlan.create(
        mapping_scope_id=uuid4(),
        catalog_fingerprint=catalog.get_fingerprint(),
    )


def _new_rule(plan: ExecutePlan, *, priority: int = 10) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=plan.id,
        mapping_scope_rule_id=uuid4(),
        priority=priority,
        draft=PlannedRuleDraft(
            name="planned-rule",
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[1],
            src_addr_objects=[10],
            dst_addr_objects=[20],
            services=[100],
        ),
        matched_sdwan_rule_id=None,
        match_status=RuleMatchStatus.NEW,
        match_info="Clearly new rule for migration",
    )


def _scope(
    plan: ExecutePlan, *, catalog_fingerprint: str | None = None
) -> MappingScopeData:
    return MappingScopeData(
        id=plan.mapping_scope_id,
        title="mapping-scope",
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=SdwanRulePriority.LOCAL,
        catalog_fingerprint=catalog_fingerprint or plan.catalog_fingerprint,
    )


@pytest.mark.asyncio
async def test_push_rejects_changed_sdwan_catalog_without_creating_rules() -> None:
    prepared_catalog = _catalog(zone_name="LAN")
    current_catalog = _catalog(zone_name="DMZ")
    plan = _plan(prepared_catalog)
    gateway = _GatewayStub(current_catalog)
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=_ExecuteRepositoryStub(plan, [_new_rule(plan)]),  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(_scope(plan)),  # type: ignore[arg-type]
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    with pytest.raises(ConflictError, match="SD-WAN catalog changed"):
        await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert gateway.push_calls == 0


@pytest.mark.asyncio
async def test_push_rejects_plan_after_mapping_catalog_baseline_change() -> None:
    catalog = _catalog(zone_name="LAN")
    plan = _plan(catalog)
    gateway = _GatewayStub(catalog)
    provider = _GatewayProviderStub(gateway)
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=_ExecuteRepositoryStub(plan, [_new_rule(plan)]),  # type: ignore[arg-type]
        sdwan_gateway_provider=provider,  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(  # type: ignore[arg-type]
            _scope(plan, catalog_fingerprint="new-catalog-fingerprint")
        ),
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    with pytest.raises(ConflictError, match="catalog baseline changed"):
        await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert provider.acquire_calls == 0
    assert gateway.push_calls == 0


@pytest.mark.asyncio
async def test_push_sends_only_new_rules_and_reads_created_policies() -> None:
    catalog = _catalog(zone_name="LAN")
    plan = _plan(catalog)
    new_rule = _new_rule(plan)
    exact_rule = ExecutePlanRule.create(
        execute_plan_id=plan.id,
        mapping_scope_rule_id=uuid4(),
        priority=new_rule.priority,
        draft=new_rule.draft,
        matched_sdwan_rule_id=500,
        match_status=RuleMatchStatus.EXACT_MATCH,
        match_info="exact",
    )
    gateway = _GatewayStub(catalog)
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=_ExecuteRepositoryStub(plan, [new_rule, exact_rule]),  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(_scope(plan)),  # type: ignore[arg-type]
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    result = await use_case.execute(
        PushExecutePlanRulesCommand(execute_plan_id=plan.id)
    )

    assert result.rules == []
    assert [(item.sdwan_rule_id, item.error) for item in result.push_results] == [
        (901, None)
    ]
    assert gateway.push_calls == 1
    assert gateway.commit_calls == 1
    assert result.commit_info.commit_id == 1
    assert gateway.push_kwargs is not None
    assert gateway.push_kwargs["sdwan_target_id"] == "target-1"
    assert gateway.push_kwargs["plan_rules"] == [new_rule]
    assert gateway.push_kwargs["priority"] == SdwanRulePriority.LOCAL
    assert gateway.requested_rule_ids == [901]


@pytest.mark.asyncio
async def test_push_sorts_rules_by_canonical_priority() -> None:
    catalog = _catalog(zone_name="LAN")
    plan = _plan(catalog)
    later_rule = _new_rule(plan, priority=20)
    earlier_rule = _new_rule(plan, priority=10)
    gateway = _GatewayStub(catalog)
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=_ExecuteRepositoryStub(plan, [later_rule, earlier_rule]),  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(_scope(plan)),  # type: ignore[arg-type]
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert gateway.pushed_plan_rules == [[earlier_rule, later_rule]]


@pytest.mark.asyncio
async def test_push_marks_plan_executed_and_rejects_repeat_after_partial_failure() -> (
    None
):
    catalog = _catalog(zone_name="LAN")
    plan = _plan(catalog)
    succeeded_rule = _new_rule(plan)
    failed_rule = _new_rule(plan)
    gateway = _GatewayStub(
        catalog,
        push_results=[
            PushRuleResultDTO(
                execute_plan_rule_id=succeeded_rule.id,
                rule_name=succeeded_rule.draft.name,
                sdwan_rule_id=901,
                error=None,
            ),
            PushRuleResultDTO(
                execute_plan_rule_id=failed_rule.id,
                rule_name=failed_rule.draft.name,
                sdwan_rule_id=None,
                error="SD-WAN rejected policy",
            ),
        ],
    )
    repository = _ExecuteRepositoryStub(plan, [succeeded_rule, failed_rule])
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=repository,  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(_scope(plan)),  # type: ignore[arg-type]
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert [
        (rule.push_status, rule.pushed_sdwan_rule_id, rule.push_error)
        for rule in repository._rules
    ] == [
        (RulePushStatus.SUCCEEDED, 901, None),
        (RulePushStatus.FAILED, None, "SD-WAN rejected policy"),
    ]
    assert repository._plan.push_status == ExecutePlanPushStatus.EXECUTED

    with pytest.raises(DomainValidationError, match="was already pushed"):
        await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert [
        [rule.id for rule in pushed_rules] for pushed_rules in gateway.pushed_plan_rules
    ] == [
        [succeeded_rule.id, failed_rule.id],
    ]


@pytest.mark.asyncio
async def test_push_marks_plan_executed_when_every_policy_creation_fails() -> None:
    catalog = _catalog(zone_name="LAN")
    plan = _plan(catalog)
    failed_rule = _new_rule(plan)
    gateway = _GatewayStub(
        catalog,
        push_results=[
            PushRuleResultDTO(
                execute_plan_rule_id=failed_rule.id,
                rule_name=failed_rule.draft.name,
                sdwan_rule_id=None,
                error="SD-WAN rejected policy",
            )
        ],
    )
    repository = _ExecuteRepositoryStub(plan, [failed_rule])
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=repository,  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(gateway),  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(_scope(plan)),  # type: ignore[arg-type]
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert repository._plan.push_status == ExecutePlanPushStatus.EXECUTED
    assert repository._rules[0].push_status == RulePushStatus.FAILED
    with pytest.raises(DomainValidationError, match="was already pushed"):
        await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert gateway.push_calls == 1


@pytest.mark.asyncio
async def test_push_rejects_plan_without_new_rules_before_acquiring_gateway() -> None:
    catalog = _catalog(zone_name="LAN")
    plan = _plan(catalog)
    gateway = _GatewayStub(catalog)
    provider = _GatewayProviderStub(gateway)
    use_case = PushExecutePlanRulesUseCase(
        execute_repo=_ExecuteRepositoryStub(plan, []),  # type: ignore[arg-type]
        sdwan_gateway_provider=provider,  # type: ignore[arg-type]
        mapping_reader=_MappingReaderStub(_scope(plan)),  # type: ignore[arg-type]
        reports_writer=_ReportsWriterStub(),  # type: ignore[arg-type]
    )

    with pytest.raises(DomainValidationError, match="has no rules for push"):
        await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan.id))

    assert provider.acquire_calls == 0


@pytest.mark.asyncio
async def test_push_rejects_unknown_execute_plan() -> None:
    class _MissingPlanRepository:
        async def get_plan(self, plan_id: UUID) -> None:
            return None

    use_case = PushExecutePlanRulesUseCase(
        execute_repo=_MissingPlanRepository(),  # type: ignore[arg-type]
        sdwan_gateway_provider=None,  # type: ignore[arg-type]
        mapping_reader=None,  # type: ignore[arg-type]
        reports_writer=None,  # type: ignore[arg-type]
    )
    plan_id = uuid4()

    with pytest.raises(NotFoundError, match=str(plan_id)):
        await use_case.execute(PushExecutePlanRulesCommand(execute_plan_id=plan_id))
