from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from ipaddress import IPv4Address, IPv4Network
from uuid import UUID, uuid4

import pytest

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanDeviceObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanDeviceObject,
    SdwanFullCatalog,
    SdwanService,
    SdwanZone,
)
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.execute.adapters.reports_writer import ExecuteReportsWriter
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import (
    RuleMatchStatus,
    SdwanRuleAction,
)
from app.modules.execute.domain.value_objects import PlannedRuleDraft
from app.modules.reports.adapters.db.uow import ReportsUnitOfWork
from app.modules.reports.application.use_cases.save_report import SaveReportUseCase
from app.modules.reports.domain.enums import ReportRuleMigrationResult


class _Gateway:
    def __init__(self, catalog: SdwanFullCatalog) -> None:
        self._catalog = catalog
        self.target_ids: list[str] = []
        self.catalog_calls = 0

    async def get_target(self, target_id: str) -> SdwanDeviceObject:
        self.target_ids.append(target_id)
        return SdwanDeviceObject(
            dev_obj_id=target_id,
            name="Branch gateway",
            type=SdwanDeviceObjectType.DEVICE,
            cpe_id="cpe-1",
        )

    async def get_sdwan_full_catalog(self) -> SdwanFullCatalog:
        self.catalog_calls += 1
        return self._catalog


class _GatewayProvider:
    def __init__(self, gateway: _Gateway) -> None:
        self._gateway = gateway
        self.discovered_profile_ids: list[UUID] = []
        self.acquired: list[tuple[UUID, str]] = []
        self.closed_contexts = 0

    async def discover_vpcs(self, profile_id: UUID) -> list[AllowedVPCResponse]:
        self.discovered_profile_ids.append(profile_id)
        return [
            AllowedVPCResponse(
                vpc_id="vpc-1",
                customer_name="Customer",
                project_name="Firewall migration",
                cuid="cuid-1",
                pid="pid-1",
            )
        ]

    @asynccontextmanager
    async def acquire(
        self,
        profile_id: UUID,
        vpc_id: str,
    ) -> AsyncIterator[_Gateway]:
        self.acquired.append((profile_id, vpc_id))
        try:
            yield self._gateway
        finally:
            self.closed_contexts += 1


def _catalog() -> SdwanFullCatalog:
    return SdwanFullCatalog(
        zones=[
            SdwanZone(id=1, zone_id=1, name="Inside", type=SdwanZoneType.LAN),
            SdwanZone(id=2, zone_id=2, name="Outside", type=SdwanZoneType.WAN),
        ],
        addr_objs=[
            SdwanAddrObject(
                id=50,
                parents=(),
                name="application-sources",
                type=SdwanAddrObjectType.ADDR_GROUP,
                addr_group=50,
            ),
            SdwanAddrObject(
                id=10,
                parents=(50,),
                name="application-host",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("10.10.0.10"),
            ),
            SdwanAddrObject(
                id=11,
                parents=(50,),
                name="application-network",
                type=SdwanAddrObjectType.PREFIX,
                prefix=IPv4Network("10.20.0.0/16"),
            ),
            SdwanAddrObject(
                id=20,
                parents=(),
                name="application-destination",
                type=SdwanAddrObjectType.FQDN,
                fqdn="API.Example.TEST",
            ),
        ],
        services=[
            SdwanService(
                id=30,
                name="https",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((443, 443),),
                codes=None,
            ),
            SdwanService(
                id=31,
                name="all",
                l4_proto=SdwanServiceL4Proto.ANY,
                ranges=None,
                codes=None,
            ),
        ],
        networks=[],
    )


def _plan_rule(
    *,
    execute_plan_id: UUID,
    name: str,
    priority: int,
    match_status: RuleMatchStatus,
    match_info: str,
    src_addr_objects: list[int] | None = None,
    services: list[int] | None = None,
) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=execute_plan_id,
        mapping_scope_rule_id=uuid4(),
        priority=priority,
        draft=PlannedRuleDraft(
            name=name,
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=src_addr_objects or [50],
            dst_addr_objects=[20],
            services=services or [30],
        ),
        matched_sdwan_rule_id=None,
        match_status=match_status,
        match_info=match_info,
    )


@pytest.mark.asyncio
async def test_execute_writer_persists_complete_report_snapshot(
    csp_profile_id: UUID,
    session_factory: SQLAlchemySessionFactory,
) -> None:
    execute_plan_id = uuid4()
    pushed = _plan_rule(
        execute_plan_id=execute_plan_id,
        name="pushed-policy",
        priority=30,
        match_status=RuleMatchStatus.NEW,
        match_info="New policy",
    ).mark_push_succeeded(901)
    failed = _plan_rule(
        execute_plan_id=execute_plan_id,
        name="failed-policy",
        priority=20,
        match_status=RuleMatchStatus.NEW,
        match_info="New policy",
        services=[31],
    ).mark_push_failed("SD-WAN rejected policy: destination is invalid")
    matched = _plan_rule(
        execute_plan_id=execute_plan_id,
        name="matched-policy",
        priority=40,
        match_status=RuleMatchStatus.EXACT_MATCH,
        match_info="Exact match with SD-WAN policy 501",
    )
    covered = _plan_rule(
        execute_plan_id=execute_plan_id,
        name="covered-policy",
        priority=50,
        match_status=RuleMatchStatus.COVERED_MATCH,
        match_info="Covered by SD-WAN policy 502",
    )
    error = _plan_rule(
        execute_plan_id=execute_plan_id,
        name="validation-error-policy",
        priority=10,
        match_status=RuleMatchStatus.MATCH_ERROR,
        match_info="Validation failed: service is unavailable",
        src_addr_objects=[999],
        services=[999],
    )
    gateway = _Gateway(_catalog())
    gateway_provider = _GatewayProvider(gateway)
    save_report_use_case = SaveReportUseCase(
        ReportsUnitOfWork(session_factory),
        gateway_provider,  # type: ignore[arg-type]
    )
    writer = ExecuteReportsWriter(save_report_use_case)

    await writer.save_report(
        scope_title="Branch migration",
        csp_profile_id=csp_profile_id,
        vpc_id="vpc-1",
        target_id="target-1",
        commit_id=42,
        plan_rules=[pushed, failed, matched, covered, error],
    )

    async with ReportsUnitOfWork(session_factory) as uow:
        reports = await uow.reports.get_list()
        assert len(reports) == 1
        restored = await uow.reports.get_report_by_id(reports[0].id)

    assert restored is not None
    assert restored.title.startswith("Branch migration — ")
    assert restored.csp_profile_id == csp_profile_id
    assert restored.commit_id == 42
    assert restored.environment.project_name == "Firewall migration"
    assert restored.environment.vpc_id == "vpc-1"
    assert restored.environment.target_name == "Branch gateway"
    assert restored.environment.target_id == "target-1"
    assert restored.rules is not None
    assert [rule.priority for rule in restored.rules] == [10, 20, 30, 40, 50]

    rules_by_name = {rule.policy_name: rule for rule in restored.rules}
    assert (
        rules_by_name["pushed-policy"].migration_result,
        rules_by_name["pushed-policy"].reason,
        rules_by_name["pushed-policy"].src_zone_names,
        rules_by_name["pushed-policy"].dst_zone_names,
        rules_by_name["pushed-policy"].src_addr_values,
        rules_by_name["pushed-policy"].dst_addr_values,
        rules_by_name["pushed-policy"].service_values,
    ) == (
        ReportRuleMigrationResult.PUSHED,
        "Success",
        ("Inside",),
        ("Outside",),
        ("10.10.0.10", "10.20.0.0/16"),
        ("api.example.test",),
        ("tcp/443",),
    )
    assert (
        rules_by_name["failed-policy"].migration_result,
        rules_by_name["failed-policy"].reason,
        rules_by_name["failed-policy"].service_values,
    ) == (
        ReportRuleMigrationResult.FAILED,
        "SD-WAN rejected policy: destination is invalid",
        ("any",),
    )
    assert (
        rules_by_name["matched-policy"].migration_result,
        rules_by_name["matched-policy"].reason,
    ) == (
        ReportRuleMigrationResult.MATCHED,
        "Exact match with SD-WAN policy 501",
    )
    assert (
        rules_by_name["covered-policy"].migration_result,
        rules_by_name["covered-policy"].reason,
    ) == (
        ReportRuleMigrationResult.COVERED,
        "Covered by SD-WAN policy 502",
    )
    assert (
        rules_by_name["validation-error-policy"].migration_result,
        rules_by_name["validation-error-policy"].reason,
        rules_by_name["validation-error-policy"].src_addr_values,
        rules_by_name["validation-error-policy"].service_values,
    ) == (
        ReportRuleMigrationResult.ERROR,
        "Validation failed: service is unavailable",
        (),
        (),
    )
    assert gateway_provider.discovered_profile_ids == [csp_profile_id]
    assert gateway_provider.acquired == [(csp_profile_id, "vpc-1")]
    assert gateway_provider.closed_contexts == 1
    assert gateway.target_ids == ["target-1"]
    assert gateway.catalog_calls == 1
