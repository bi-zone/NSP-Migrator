from dataclasses import dataclass, field

import pytest

from app.integrations.sdwan_csp_api.schemas import (
    AddrObject,
    AmbiguousReason,
    PolicyResponse,
    RuleAction,
)
from app.modules.execute.adapters.sdwan_gateway import ExecuteSDWANGateway
from app.modules.execute.domain.enums import SdwanRuleAction


def _policy(
    *,
    policy_id: int,
    action: RuleAction = RuleAction.ACCEPT,
    ambiguous: bool = False,
) -> PolicyResponse:
    return PolicyResponse(
        type="policy",
        policy_id=policy_id,
        parents=["target-1"],
        order="1",
        priority="post",
        name=f"rule-{policy_id}",
        description="",
        tags=["migration"],
        activated=True,
        action=action,
        log=False,
        l4_inspection=False,
        ambiguous=ambiguous,
        ambiguous_reason=(
            AmbiguousReason(code=42, meta={"reason": "overlap"})
            if ambiguous
            else None
        ),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        snat=None,
        dnat=None,
        ingress_zone=[2, 1],
        egress_zone=[3],
        src_address=[AddrObject(type="host", id=100)],
        dst_address=[AddrObject(type="prefix", id=101)],
        service=[10],
        src_idents=[],
        dst_idents=[],
    )


@dataclass
class _HttpClientFake:
    policies: list[PolicyResponse]
    requested_target_id: str | None = None
    requested_policy_ids: list[int] | None = None

    async def get_policies(self, *, dev_obj_id: str) -> list[PolicyResponse]:
        self.requested_target_id = dev_obj_id
        return self.policies

    async def get_policies_by_ids(self, *, ids: list[int]) -> list[PolicyResponse]:
        self.requested_policy_ids = ids
        return self.policies


@dataclass
class _CatalogGatewayFake:
    zone_requests: list[list[int]] = field(default_factory=list)
    service_requests: list[list[int]] = field(default_factory=list)
    address_requests: list[list[int]] = field(default_factory=list)

    async def get_zones(self, *, ids: list[int]) -> list:
        self.zone_requests.append(ids)
        return []

    async def get_services(self, *, ids: list[int]) -> list:
        self.service_requests.append(ids)
        return []

    async def get_addr_objects(self, *, ids: list[int]) -> list:
        self.address_requests.append(ids)
        return []


@pytest.mark.asyncio
async def test_policy_catalog_merges_existing_and_planned_rule_references() -> None:
    http_client = _HttpClientFake([_policy(policy_id=501, action=RuleAction.DROP)])
    catalog_gateway = _CatalogGatewayFake()
    gateway = ExecuteSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=catalog_gateway,  # type: ignore[arg-type]
    )

    catalog = await gateway.get_sdwan_policy_catalog(
        "target-1",
        extra_zone_ids={4},
        extra_service_ids={20},
        extra_addr_object_ids={200},
    )

    assert http_client.requested_target_id == "target-1"
    assert catalog.target_id == "target-1"
    assert catalog.rules[0].id == 501
    assert catalog.rules[0].action == SdwanRuleAction.DROP
    assert catalog.rules[0].src_zones == [2, 1]
    assert catalog.rules[0].dst_addr_objects == [101]
    assert catalog_gateway.zone_requests == [[1, 2, 3, 4]]
    assert catalog_gateway.service_requests == [[10, 20]]
    assert catalog_gateway.address_requests == [[100, 101, 200]]


@pytest.mark.asyncio
async def test_get_rules_maps_transport_policy_to_display_dto() -> None:
    http_client = _HttpClientFake([_policy(policy_id=501, ambiguous=True)])
    gateway = ExecuteSDWANGateway(
        sdwan_http_client=http_client,  # type: ignore[arg-type]
        catalog_gateway=_CatalogGatewayFake(),  # type: ignore[arg-type]
    )

    rules = await gateway.get_rules([501])

    assert http_client.requested_policy_ids == [501]
    assert rules[0].policy_id == 501
    assert rules[0].action == SdwanRuleAction.ACCEPT
    assert rules[0].src_address[0].id == 100
    assert rules[0].ambiguous_reason is not None
    assert rules[0].ambiguous_reason.meta == {"reason": "overlap"}
