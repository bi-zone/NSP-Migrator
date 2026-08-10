from datetime import datetime

from app.integrations.sdwan_csp_api.gateways.ports import SDWANCatalogGatewayPort
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient
from app.integrations.sdwan_csp_api.schemas import (
    CreatePolicyRequest,
    PolicyResponse,
    RuleAction,
)
from app.modules.execute.application.dto import (
    AmbiguousReasonDTO,
    SdwanAddrObjectDTO,
    SdwanRuleDTO,
)
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import SdwanRuleAction
from app.modules.execute.domain.value_objects import (
    PlannedRuleDraft,
    SdwanPolicyCatalog,
    SdwanRule,
)
from app.modules.execute.ports.gateways import ExecuteSDWANGatewayPort


class ExecuteSDWANGateway(ExecuteSDWANGatewayPort):
    """Execute-specific SD-WAN gateway.

    Low-level HTTP calls stay in ISDWANCspHttpClient. Shared catalog loading and
    address-group expansion stay in SDWANCatalogGateway. This adapter only builds
    execute runtime models and creates policies from prepared plan drafts.
    """

    def __init__(
        self,
        sdwan_http_client: ISDWANCspHttpClient,
        catalog_gateway: SDWANCatalogGatewayPort,
    ) -> None:
        self.sdwan_http_client = sdwan_http_client
        self.catalog_gateway = catalog_gateway

    async def health_check(self) -> None:
        await self.sdwan_http_client.health_check()

    async def get_sdwan_policy_catalog(
        self,
        sdwan_target_id: str,
        *,
        extra_zone_ids: set[int] | None = None,
        extra_service_ids: set[int] | None = None,
        extra_addr_object_ids: set[int] | None = None,
    ) -> SdwanPolicyCatalog:
        """Load runtime catalog needed to compare plan drafts with SD-WAN.

        The method fetches existing policies for target device object, collects
        all referenced zone/service/address-object ids from both SD-WAN policies
        and planned drafts, then delegates object loading to the shared catalog
        gateway.
        """
        policies: list[PolicyResponse] = await self.sdwan_http_client.get_policies(
            dev_obj_id=sdwan_target_id,
        )

        zone_ids: set[int] = set(extra_zone_ids or set())
        service_ids: set[int] = set(extra_service_ids or set())
        addr_object_ids: set[int] = set(extra_addr_object_ids or set())

        for policy in policies:
            zone_ids.update(policy.ingress_zone)
            zone_ids.update(policy.egress_zone)
            service_ids.update(policy.service)
            addr_object_ids.update(addr_object.id for addr_object in policy.src_address)
            addr_object_ids.update(addr_object.id for addr_object in policy.dst_address)

        rules: list[SdwanRule] = [
            SdwanRule(
                id=policy.policy_id,
                action=SdwanRuleAction(policy.action),
                src_zones=policy.ingress_zone,
                dst_zones=policy.egress_zone,
                src_addr_objects=[addr_object.id for addr_object in policy.src_address],
                dst_addr_objects=[addr_object.id for addr_object in policy.dst_address],
                services=policy.service,
            )
            for policy in policies
        ]

        return SdwanPolicyCatalog(
            target_id=sdwan_target_id,
            rules=rules,
            zones=await self.catalog_gateway.get_zones(ids=sorted(zone_ids)),
            services=await self.catalog_gateway.get_services(ids=sorted(service_ids)),
            address_objects=await self.catalog_gateway.get_addr_objects(
                ids=sorted(addr_object_ids)
            ),
        )

    async def push_rules(
        self,
        sdwan_target_id: str,
        plan_rules: list[ExecutePlanRule],
    ) -> list[int]:
        """Create SD-WAN policies from prepared execute plan rules."""
        pushed_rules_ids: list[int] = []
        for rule_num, plan_rule in enumerate(plan_rules, start=1):
            draft: PlannedRuleDraft = plan_rule.draft

            pushed_rule_id: int = await self.sdwan_http_client.create_policy(
                CreatePolicyRequest(
                    name=f"imported-migrator-rule-{datetime.now()}-{rule_num}",
                    description="",
                    tags=[],
                    activated=True,
                    action=RuleAction(draft.action),
                    log=False,
                    l4_inspection=False,
                    ingress_zone=draft.src_zones,
                    egress_zone=draft.dst_zones,
                    src_address=draft.src_addr_objects,
                    dst_address=draft.dst_addr_objects,
                    service=draft.services,
                    parent=sdwan_target_id,
                    parent_type="device",
                )
            )
            pushed_rules_ids.append(pushed_rule_id)

        return pushed_rules_ids

    async def get_rules(self, rules_ids: list[int]) -> list[SdwanRuleDTO]:
        """Return SD-WAN policy DTOs by external policy ids."""
        rules: list[PolicyResponse] = await self.sdwan_http_client.get_policies_by_ids(
            ids=rules_ids
        )
        return [self._policy_response_to_dto(rule) for rule in rules]

    def _policy_response_to_dto(self, rule: PolicyResponse) -> SdwanRuleDTO:
        """Convert integration policy response into execute application DTO."""
        return SdwanRuleDTO(
            policy_id=rule.policy_id,
            type=rule.type,
            name=rule.name,
            parents=rule.parents,
            description=rule.description,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            order=rule.order,
            priority=rule.priority,
            tags=rule.tags,
            activated=rule.activated,
            action=SdwanRuleAction(rule.action),
            log=rule.log,
            l4_inspection=rule.l4_inspection,
            ambiguous=rule.ambiguous,
            ambiguous_reason=(
                AmbiguousReasonDTO(
                    code=rule.ambiguous_reason.code,
                    meta=rule.ambiguous_reason.meta,
                )
                if rule.ambiguous_reason
                else None
            ),
            snat=rule.snat,
            dnat=rule.dnat,
            ingress_zone=rule.ingress_zone,
            egress_zone=rule.egress_zone,
            src_address=[
                SdwanAddrObjectDTO(
                    type=addr_object.type,
                    id=addr_object.id,
                )
                for addr_object in rule.src_address
            ],
            dst_address=[
                SdwanAddrObjectDTO(
                    type=addr_object.type,
                    id=addr_object.id,
                )
                for addr_object in rule.dst_address
            ],
            service=rule.service,
            src_idents=rule.src_idents,
            dst_idents=rule.dst_idents,
        )
