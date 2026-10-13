from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanDeviceObjectType,
    SdwanRulePriority,
)
from app.integrations.sdwan_csp_api.gateways.models import SdwanDeviceObject
from app.integrations.sdwan_csp_api.schemas import CreatePolicyRequest, RuleAction
from app.modules.execute.adapters.sdwan_gateway import ExecuteSDWANGateway
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction
from app.modules.execute.domain.exceptions import ExecuteModuleNotFoundError
from app.modules.execute.domain.value_objects import PlannedRuleDraft


@dataclass(slots=True)
class _HttpClientStub:
    created_policies: list[CreatePolicyRequest] = field(default_factory=list)

    async def create_policy(self, payload: CreatePolicyRequest) -> int:
        self.created_policies.append(payload)
        return len(self.created_policies)


@dataclass(slots=True)
class _PartiallyFailingHttpClientStub:
    failed_policy_name: str
    attempted_policy_names: list[str] = field(default_factory=list)
    created_policies: list[CreatePolicyRequest] = field(default_factory=list)

    async def create_policy(self, payload: CreatePolicyRequest) -> int:
        self.attempted_policy_names.append(payload.name)
        if payload.name == self.failed_policy_name:
            raise RuntimeError("SD-WAN rejected policy")

        self.created_policies.append(payload)
        return len(self.created_policies)


@dataclass(slots=True)
class _CatalogGatewayStub:
    target: SdwanDeviceObject | None

    async def get_sdwan_device_object(
        self, dev_obj_id: str
    ) -> SdwanDeviceObject | None:
        if self.target is not None:
            assert dev_obj_id == self.target.dev_obj_id
        return self.target


def _plan_rule(plan: ExecutePlan, *, name: str) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=plan.id,
        mapping_scope_rule_id=uuid4(),
        priority=0,
        draft=PlannedRuleDraft(
            name=name,
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=[10],
            dst_addr_objects=[20],
            services=[100],
        ),
        matched_sdwan_rule_id=None,
        match_status=RuleMatchStatus.NEW,
        match_info="Clearly new rule for migration",
    )


@pytest.mark.asyncio
async def test_push_rules_uses_name_from_execute_plan_draft() -> None:
    target = SdwanDeviceObject(
        dev_obj_id="target-1",
        name="Target",
        type=SdwanDeviceObjectType.DEVICE,
        cpe_id="cpe-1",
    )
    http_client = _HttpClientStub()
    gateway = ExecuteSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=_CatalogGatewayStub(target),  # type: ignore[arg-type]
    )
    plan = ExecutePlan.create(
        mapping_scope_id=uuid4(),
        catalog_fingerprint="catalog-fingerprint",
    )

    push_results = await gateway.push_rules(
        sdwan_target_id=target.dev_obj_id,
        plan_rules=[_plan_rule(plan, name="ACL_IN:42")],
        priority=SdwanRulePriority.LOCAL,
    )

    assert [result.rule_name for result in push_results] == ["ACL_IN:42"]
    assert [result.sdwan_rule_id for result in push_results] == [1]
    assert [result.error for result in push_results] == [None]
    assert [request.name for request in http_client.created_policies] == ["ACL_IN:42"]
    request = http_client.created_policies[0]
    assert request.parent == "target-1"
    assert request.parent_type == "device"
    assert request.priority == "local"
    assert request.action == RuleAction.ACCEPT
    assert request.ingress_zone == [1]
    assert request.egress_zone == [2]
    assert request.src_address == [10]
    assert request.dst_address == [20]
    assert request.service == [100]


@pytest.mark.asyncio
async def test_push_rules_fails_before_creating_policy_when_target_is_missing() -> None:
    http_client = _HttpClientStub()
    gateway = ExecuteSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=_CatalogGatewayStub(None),  # type: ignore[arg-type]
    )
    plan = ExecutePlan.create(
        mapping_scope_id=uuid4(),
        catalog_fingerprint="catalog-fingerprint",
    )

    with pytest.raises(ExecuteModuleNotFoundError, match="target-1"):
        await gateway.push_rules(
            sdwan_target_id="target-1",
            plan_rules=[_plan_rule(plan, name="ACL_IN:42")],
            priority=SdwanRulePriority.LOCAL,
        )

    assert http_client.created_policies == []


@pytest.mark.asyncio
async def test_push_rules_continues_after_one_policy_creation_error() -> None:
    target = SdwanDeviceObject(
        dev_obj_id="target-1",
        name="Target",
        type=SdwanDeviceObjectType.DEVICE,
        cpe_id="cpe-1",
    )
    http_client = _PartiallyFailingHttpClientStub(failed_policy_name="ACL_IN:2")
    gateway = ExecuteSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=_CatalogGatewayStub(target),  # type: ignore[arg-type]
    )
    plan = ExecutePlan.create(
        mapping_scope_id=uuid4(),
        catalog_fingerprint="catalog-fingerprint",
    )
    plan_rules = [
        _plan_rule(plan, name="ACL_IN:1"),
        _plan_rule(plan, name="ACL_IN:2"),
        _plan_rule(plan, name="ACL_IN:3"),
    ]

    push_results = await gateway.push_rules(
        sdwan_target_id=target.dev_obj_id,
        plan_rules=plan_rules,
        priority=SdwanRulePriority.LOCAL,
    )

    assert http_client.attempted_policy_names == ["ACL_IN:1", "ACL_IN:2", "ACL_IN:3"]
    assert [request.name for request in http_client.created_policies] == [
        "ACL_IN:1",
        "ACL_IN:3",
    ]
    assert [
        (
            result.execute_plan_rule_id,
            result.rule_name,
            result.sdwan_rule_id,
            result.error,
        )
        for result in push_results
    ] == [
        (plan_rules[0].id, "ACL_IN:1", 1, None),
        (plan_rules[1].id, "ACL_IN:2", None, "SD-WAN rejected policy"),
        (plan_rules[2].id, "ACL_IN:3", 2, None),
    ]
