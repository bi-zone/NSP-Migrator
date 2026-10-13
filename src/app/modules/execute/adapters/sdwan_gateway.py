import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.integrations.sdwan_csp_api.client_provider import SDWANClientProvider
from app.integrations.sdwan_csp_api.gateways.catalog import SDWANCatalogGateway
from app.integrations.sdwan_csp_api.gateways.enums import SdwanRulePriority
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanDeviceObject,
    SdwanFullCatalog,
)
from app.integrations.sdwan_csp_api.gateways.ports import SDWANCatalogGatewayPort
from app.integrations.sdwan_csp_api.interfaces import ISDWANCspHttpClient
from app.integrations.sdwan_csp_api.schemas import (
    CommitDataResponse,
    CreatePolicyRequest,
    DeviceObjectType,
    PolicyPlacementPriority,
    PolicyResponse,
    RuleAction,
)
from app.modules.common.domain.utils import get_utc_now
from app.modules.execute.application.dto import (
    AmbiguousReasonDTO,
    CommitInfoDTO,
    PushRuleResultDTO,
    SdwanAddrObjectDTO,
    SdwanRuleDTO,
)
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import SdwanRuleAction
from app.modules.execute.domain.exceptions import ExecuteModuleNotFoundError
from app.modules.execute.domain.value_objects import (
    PlannedRuleDraft,
    SdwanPolicyCatalog,
    SdwanRule,
)
from app.modules.execute.ports.gateways import (
    ExecuteSDWANGatewayPort,
    ExecuteSDWANGatewayProviderPort,
)

logger = logging.getLogger(__name__)


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

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        """Load the full catalog used for execution consistency checks."""
        return await self.catalog_gateway.get_sdwan_full_catalog()

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
        priority: SdwanRulePriority,
    ) -> list[PushRuleResultDTO]:
        """Create SD-WAN policies and return an outcome for every plan rule."""
        # -- get target device object info
        target: SdwanDeviceObject | None = (  # fmt: no
            await self.catalog_gateway.get_sdwan_device_object(
                dev_obj_id=sdwan_target_id
            )
        )
        if not target:
            raise ExecuteModuleNotFoundError(
                f"Not found device object {sdwan_target_id}"
            )

        # -- push rules for device object
        push_results: list[PushRuleResultDTO] = []
        for plan_rule in plan_rules:
            draft: PlannedRuleDraft = plan_rule.draft

            try:
                pushed_rule_id: int = await self.sdwan_http_client.create_policy(
                    CreatePolicyRequest(
                        name=draft.name,
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
                        parent_type=DeviceObjectType(target.type),
                        priority=PolicyPlacementPriority(priority),
                    )
                )
            except Exception as error:
                push_results.append(
                    PushRuleResultDTO(
                        execute_plan_rule_id=plan_rule.id,
                        rule_name=draft.name,
                        sdwan_rule_id=None,
                        error=str(error) or type(error).__name__,
                    )
                )
                continue

            push_results.append(
                PushRuleResultDTO(
                    execute_plan_rule_id=plan_rule.id,
                    rule_name=draft.name,
                    sdwan_rule_id=pushed_rule_id,
                    error=None,
                )
            )

        return push_results

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

    async def commit_csp_changes(self) -> CommitInfoDTO:
        """Commit changes on CSP and return commit info"""
        commit_id: int = await self.sdwan_http_client.commit_full_state(
            commit_name=(
                f"policy-migrator-commit-{get_utc_now().strftime('%Y%m%d-%H%M%S')}"
            ),
            commit_description="",
        )
        commit_info_resp: CommitDataResponse = (
            await self.sdwan_http_client.get_commit_info(commit_id=commit_id)
        )
        return CommitInfoDTO(
            commit_id=commit_info_resp.commit_id,
            name=commit_info_resp.name,
            description=commit_info_resp.description,
        )


class ExecuteSDWANGatewayProvider(ExecuteSDWANGatewayProviderPort):
    def __init__(self, client_provider: SDWANClientProvider) -> None:
        self._client_provider = client_provider

    @asynccontextmanager
    async def acquire(
        self,
        profile_id: UUID,
        vpc_id: str,
    ) -> AsyncIterator[ExecuteSDWANGateway]:
        async with self._client_provider.acquire(
            profile_id,
            vpc_id,
        ) as client:
            yield ExecuteSDWANGateway(
                sdwan_http_client=client,
                catalog_gateway=SDWANCatalogGateway(client),
            )
