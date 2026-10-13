from ipaddress import IPv4Address, IPv4Network

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanFullCatalog,
    SdwanService,
    SdwanZone,
)
from app.modules.reports.application.services.report_rule_values_resolver import (
    ReportRuleValuesResolver,
)
from app.modules.reports.application.use_cases.save_report import (
    SaveReportRuleCommand,
)
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)


def _rule(**overrides: object) -> SaveReportRuleCommand:
    data: dict[str, object] = {
        "policy_name": "allow-application",
        "action": ReportRuleAction.ACCEPT,
        "priority": 10,
        "src_zone_ids": (1,),
        "dst_zone_ids": (2,),
        "src_addr_object_ids": (50,),
        "dst_addr_object_ids": (13,),
        "service_ids": (20, 21, 22),
        "migration_result": ReportRuleMigrationResult.PUSHED,
        "reason": "Success",
    }
    data.update(overrides)
    return SaveReportRuleCommand(**data)  # type: ignore[arg-type]


def test_resolver_preserves_order_and_resolves_group_leaves_and_services() -> None:
    catalog = SdwanFullCatalog(
        zones=[
            SdwanZone(id=1, zone_id=1, name="LAN", type=SdwanZoneType.LAN),
            SdwanZone(id=2, zone_id=2, name="WAN", type=SdwanZoneType.WAN),
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
                id=11,
                parents=(50,),
                name="application-host",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("10.10.0.10"),
            ),
            SdwanAddrObject(
                id=12,
                parents=(50,),
                name="application-network",
                type=SdwanAddrObjectType.PREFIX,
                prefix=IPv4Network("10.20.0.0/16"),
            ),
            SdwanAddrObject(
                id=13,
                parents=(),
                name="application-target",
                type=SdwanAddrObjectType.FQDN,
                fqdn=" API.Example.TEST ",
            ),
        ],
        services=[
            SdwanService(
                id=20,
                name="web",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((443, 443), (1000, 1002)),
                codes=None,
            ),
            SdwanService(
                id=21,
                name="ping",
                l4_proto=SdwanServiceL4Proto.ICMP,
                ranges=None,
                codes=("8", "0"),
            ),
            SdwanService(
                id=22,
                name="all",
                l4_proto=SdwanServiceL4Proto.ANY,
                ranges=None,
                codes=None,
            ),
        ],
        networks=[],
    )

    snapshot = ReportRuleValuesResolver(catalog).resolve(_rule())

    assert snapshot.src_zone_names == ("LAN",)
    assert snapshot.dst_zone_names == ("WAN",)
    assert snapshot.src_addr_values == ("10.10.0.10", "10.20.0.0/16")
    assert snapshot.dst_addr_values == ("api.example.test",)
    assert snapshot.service_values == ("tcp/443", "tcp/1000-1002", "icmp/0,8", "any")


def test_resolver_keeps_resolved_values_when_some_operands_are_unavailable() -> None:
    catalog = SdwanFullCatalog(
        zones=[SdwanZone(id=1, zone_id=1, name="LAN", type=SdwanZoneType.LAN)],
        addr_objs=[
            SdwanAddrObject(
                id=11,
                parents=(),
                name="known-source",
                type=SdwanAddrObjectType.HOST,
                host=IPv4Address("10.10.0.10"),
            ),
            SdwanAddrObject(
                id=50,
                parents=(),
                name="empty-group",
                type=SdwanAddrObjectType.ADDR_GROUP,
                addr_group=50,
            ),
        ],
        services=[
            SdwanService(
                id=20,
                name="web",
                l4_proto=SdwanServiceL4Proto.TCP,
                ranges=((443, 443),),
                codes=None,
            )
        ],
        networks=[],
    )
    rule = _rule(
        src_zone_ids=(1, 999),
        src_addr_object_ids=(11, 999, 50),
        dst_addr_object_ids=(999,),
        service_ids=(20, 999),
        migration_result=ReportRuleMigrationResult.ERROR,
        reason="Validation failed: address object is unavailable",
    )

    snapshot = ReportRuleValuesResolver(catalog).resolve(rule)

    assert snapshot.src_zone_names == ("LAN",)
    assert snapshot.src_addr_values == ("10.10.0.10",)
    assert snapshot.dst_addr_values == ()
    assert snapshot.service_values == ("tcp/443",)
    assert snapshot.policy_name == rule.policy_name
    assert snapshot.action == rule.action
    assert snapshot.priority == rule.priority
    assert snapshot.migration_result == ReportRuleMigrationResult.ERROR
    assert snapshot.reason == "Validation failed: address object is unavailable"
