from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanRulePriority,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanFullCatalog,
    SdwanService,
    SdwanZone,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanCommand,
    PrepareExecutePlanUseCase,
)
from app.modules.execute.domain.entities import ExecutePlan, ExecutePlanRule
from app.modules.execute.domain.enums import RulePushStatus, SdwanRuleAction
from app.modules.execute.domain.value_objects import SdwanPolicyCatalog, SdwanRule
from app.modules.execute.errors import ConflictError
from app.modules.execute.ports.mapping_reader.schemas import (
    MappedRuleData,
    MappedRuleDataAction,
    MappingScopeData,
)


def test_build_draft_keeps_mapping_rule_name() -> None:
    use_case = PrepareExecutePlanUseCase(
        execute_repo=None,  # type: ignore[arg-type]
        sdwan_gateway_provider=None,  # type: ignore[arg-type]
        mapping_reader=None,  # type: ignore[arg-type]
    )

    draft = use_case._build_draft(
        MappedRuleData(
            id=uuid4(),
            name="global_access:3",
            action=MappedRuleDataAction.ACCEPT,
            priority=3,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=[10],
            dst_addr_objects=[20],
            services=[100],
        )
    )

    assert draft.name == "global_access:3"
    assert draft.action == SdwanRuleAction.ACCEPT


class _ExecuteRepositoryStub:
    saved_plan: ExecutePlan | None = None
    saved_rules: list[ExecutePlanRule] | None = None

    async def add_plan_with_rules(
        self,
        *,
        plan: ExecutePlan,
        rules: list[ExecutePlanRule],
    ) -> ExecutePlan:
        self.saved_plan = plan
        self.saved_rules = rules
        return plan


class _MappingReaderStub:
    def __init__(self, scope: MappingScopeData, rules: list[MappedRuleData]) -> None:
        self._scope = scope
        self._rules = rules

    async def get_mapping_scope_data(self, mapping_scope_id) -> MappingScopeData:  # type: ignore[no-untyped-def]
        assert mapping_scope_id == self._scope.id
        return self._scope

    async def get_mapping_scope_rules(self, mapping_scope_id) -> list[MappedRuleData]:  # type: ignore[no-untyped-def]
        assert mapping_scope_id == self._scope.id
        return self._rules


class _GatewayStub:
    def __init__(
        self,
        catalog: SdwanPolicyCatalog,
        full_catalog: SdwanFullCatalog,
    ) -> None:
        self._catalog = catalog
        self._full_catalog = full_catalog

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        return self._full_catalog

    async def get_sdwan_policy_catalog(
        self, sdwan_target_id, **kwargs
    ) -> SdwanPolicyCatalog:  # type: ignore[no-untyped-def]
        assert sdwan_target_id == self._catalog.target_id
        return self._catalog


class _GatewayProviderStub:
    def __init__(self, gateway: _GatewayStub) -> None:
        self._gateway = gateway

    @asynccontextmanager
    async def acquire(self, profile_id, vpc_id):  # type: ignore[no-untyped-def]
        yield self._gateway


@pytest.mark.asyncio
async def test_prepare_plan_reports_existing_rules_excluded_from_comparison() -> None:
    scope_id = uuid4()
    scope = MappingScopeData(
        id=scope_id,
        title="mapping-scope",
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=SdwanRulePriority.POST,
        catalog_fingerprint="",
    )
    mapped_rule = MappedRuleData(
        id=uuid4(),
        name="planned-rule",
        action=MappedRuleDataAction.ACCEPT,
        priority=10,
        src_zones=[1],
        dst_zones=[2],
        src_addr_objects=[],
        dst_addr_objects=[],
        services=[100],
    )
    later_mapped_rule = replace(
        mapped_rule,
        id=uuid4(),
        name="later-planned-rule",
        priority=20,
    )
    catalog = SdwanPolicyCatalog(
        target_id="target-1",
        rules=[
            SdwanRule(
                id=500,
                action=SdwanRuleAction.ACCEPT,
                src_zones=[1],
                dst_zones=[2],
                src_addr_objects=[],
                dst_addr_objects=[],
                services=[999],
            )
        ],
        zones=[
            SdwanZone(id=1, zone_id=1, name="LAN", type=SdwanZoneType.LAN),
            SdwanZone(id=2, zone_id=2, name="WAN", type=SdwanZoneType.WAN),
        ],
        services=[
            SdwanService(
                id=100,
                name="any",
                l4_proto=SdwanServiceL4Proto.ANY,
                ranges=None,
                codes=None,
            )
        ],
        address_objects=[],
    )
    full_catalog = SdwanFullCatalog(
        zones=catalog.zones,
        services=catalog.services,
        addr_objs=catalog.address_objects,
        networks=[],
    )
    scope = MappingScopeData(
        id=scope.id,
        title=scope.title,
        csp_profile_id=scope.csp_profile_id,
        vpc_id=scope.vpc_id,
        sdwan_target_id=scope.sdwan_target_id,
        rules_priority=scope.rules_priority,
        catalog_fingerprint=full_catalog.get_fingerprint(),
    )
    execute_repo = _ExecuteRepositoryStub()
    use_case = PrepareExecutePlanUseCase(
        execute_repo=execute_repo,  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(  # type: ignore[arg-type]
            _GatewayStub(catalog, full_catalog)
        ),
        mapping_reader=_MappingReaderStub(  # type: ignore[arg-type]
            scope,
            [later_mapped_rule, mapped_rule],
        ),
    )

    result = await use_case.execute(
        PrepareExecutePlanCommand(mapping_scope_id=scope_id)
    )

    assert result.new_rules == 2
    assert result.excluded_existing_rules[0].sdwan_rule_id == 500
    assert result.excluded_existing_rules[0].reason == "Unknown service id: 999"
    assert execute_repo.saved_plan is not None
    assert execute_repo.saved_plan.catalog_fingerprint == scope.catalog_fingerprint
    assert execute_repo.saved_rules is not None
    assert [rule.priority for rule in execute_repo.saved_rules] == [10, 20]
    assert [rule.draft.name for rule in execute_repo.saved_rules] == [
        "planned-rule",
        "later-planned-rule",
    ]
    assert all(
        rule.push_status == RulePushStatus.PENDING for rule in execute_repo.saved_rules
    )


@pytest.mark.asyncio
async def test_prepare_plan_rejects_changed_sdwan_catalog() -> None:
    scope_id = uuid4()
    original_catalog = SdwanFullCatalog(
        zones=[],
        services=[],
        addr_objs=[],
        networks=[],
    )
    current_catalog = SdwanFullCatalog(
        zones=[],
        services=[
            SdwanService(
                id=100,
                name="any",
                l4_proto=SdwanServiceL4Proto.ANY,
                ranges=None,
                codes=None,
            )
        ],
        addr_objs=[],
        networks=[],
    )
    scope = MappingScopeData(
        id=scope_id,
        title="mapping-scope",
        csp_profile_id=uuid4(),
        vpc_id="vpc-1",
        sdwan_target_id="target-1",
        rules_priority=SdwanRulePriority.POST,
        catalog_fingerprint=original_catalog.get_fingerprint(),
    )
    policy_catalog = SdwanPolicyCatalog(
        target_id=scope.sdwan_target_id,
        rules=[],
        zones=[],
        services=current_catalog.services,
        address_objects=[],
    )
    execute_repo = _ExecuteRepositoryStub()
    use_case = PrepareExecutePlanUseCase(
        execute_repo=execute_repo,  # type: ignore[arg-type]
        sdwan_gateway_provider=_GatewayProviderStub(  # type: ignore[arg-type]
            _GatewayStub(policy_catalog, current_catalog)
        ),
        mapping_reader=_MappingReaderStub(scope, []),  # type: ignore[arg-type]
    )

    with pytest.raises(ConflictError, match="SD-WAN catalog changed"):
        await use_case.execute(PrepareExecutePlanCommand(mapping_scope_id=scope_id))

    assert execute_repo.saved_plan is None
