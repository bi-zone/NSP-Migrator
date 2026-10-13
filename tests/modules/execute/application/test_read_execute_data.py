from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import SdwanRulePriority
from app.modules.execute.application.dto import SdwanRuleDTO
from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesQuery,
    GetExecutePlanRulesUseCase,
)
from app.modules.execute.application.use_cases.get_sdwan_rules import (
    GetSdwanRulesQuery,
    GetSdwanRulesUseCase,
)
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction
from app.modules.execute.domain.value_objects import PlannedRuleDraft
from app.modules.execute.ports.mapping_reader.schemas import MappingScopeData


def _plan_rule(plan_id: UUID, *, status: RuleMatchStatus) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=plan_id,
        mapping_scope_rule_id=uuid4(),
        priority=0,
        draft=PlannedRuleDraft(
            name="allow-web",
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=[],
            dst_addr_objects=[],
            services=[],
        ),
        matched_sdwan_rule_id=None,
        match_status=status,
        match_info="new",
    )


class _ExecuteRepositoryFake:
    def __init__(self, rules: list[ExecutePlanRule]) -> None:
        self._rules = rules
        self.last_plan_id: UUID | None = None
        self.last_status: RuleMatchStatus | None = None

    async def list_plan_rules(
        self,
        *,
        plan_id: UUID,
        match_status: RuleMatchStatus | None = None,
    ) -> list[ExecutePlanRule]:
        self.last_plan_id = plan_id
        self.last_status = match_status
        return [
            rule
            for rule in self._rules
            if match_status is None or rule.match_status == match_status
        ]


@pytest.mark.asyncio
async def test_get_execute_plan_rules_passes_optional_match_status_to_repository() -> (
    None
):
    plan = ExecutePlan.create(mapping_scope_id=uuid4(), catalog_fingerprint="catalog")
    new_rule = _plan_rule(plan.id, status=RuleMatchStatus.NEW)
    repo = _ExecuteRepositoryFake(
        [new_rule, _plan_rule(plan.id, status=RuleMatchStatus.EXACT_MATCH)]
    )

    result = await GetExecutePlanRulesUseCase(repo).execute(
        GetExecutePlanRulesQuery(
            execute_plan_id=plan.id,
            match_status=RuleMatchStatus.NEW,
        )
    )

    assert result.plan_rules == [new_rule]
    assert repo.last_plan_id == plan.id
    assert repo.last_status == RuleMatchStatus.NEW


def _sdwan_rule(rule_id: int) -> SdwanRuleDTO:
    return SdwanRuleDTO(
        type="policy",
        policy_id=rule_id,
        parents=[],
        order="1",
        priority="post",
        name="existing-rule",
        description="",
        tags=[],
        activated=True,
        action=SdwanRuleAction.ACCEPT,
        log=False,
        l4_inspection=False,
        ambiguous=False,
        ambiguous_reason=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        snat=None,
        dnat=None,
        ingress_zone=[1],
        egress_zone=[2],
        src_address=[],
        dst_address=[],
        service=[],
        src_idents=[],
        dst_idents=[],
    )


class _MappingReaderFake:
    def __init__(self, scope: MappingScopeData) -> None:
        self._scope = scope

    async def get_mapping_scope_data(self, mapping_scope_id: UUID) -> MappingScopeData:
        assert mapping_scope_id == self._scope.id
        return self._scope


class _GatewayFake:
    def __init__(self, rules: list[SdwanRuleDTO]) -> None:
        self._rules = rules
        self.requested_ids: list[int] | None = None

    async def get_rules(self, rules_ids: list[int]) -> list[SdwanRuleDTO]:
        self.requested_ids = rules_ids
        return self._rules


class _GatewayProviderFake:
    def __init__(self, gateway: _GatewayFake) -> None:
        self._gateway = gateway
        self.acquired_for: tuple[UUID, str] | None = None

    @asynccontextmanager
    async def acquire(self, profile_id: UUID, vpc_id: str):  # type: ignore[no-untyped-def]
        self.acquired_for = profile_id, vpc_id
        yield self._gateway


@pytest.mark.asyncio
async def test_get_sdwan_rules_uses_profile_and_vpc_of_mapping_scope() -> None:
    profile_id = uuid4()
    scope = MappingScopeData(
        id=uuid4(),
        title="mapping-scope",
        csp_profile_id=profile_id,
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=SdwanRulePriority.POST,
        catalog_fingerprint="fingerprint",
    )
    gateway = _GatewayFake([_sdwan_rule(101)])
    provider = _GatewayProviderFake(gateway)
    use_case = GetSdwanRulesUseCase(provider, _MappingReaderFake(scope))  # type: ignore[arg-type]

    result = await use_case.execute(
        GetSdwanRulesQuery(mapping_scope_id=scope.id, rules_ids=[101])
    )

    assert result.rules == [_sdwan_rule(101)]
    assert gateway.requested_ids == [101]
    assert provider.acquired_for == (profile_id, "vpc-1")
