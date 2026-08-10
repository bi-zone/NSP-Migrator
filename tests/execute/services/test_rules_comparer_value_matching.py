from ipaddress import IPv4Address, IPv4Network

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
    SdwanZoneType,
)
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanService,
    SdwanZone,
)
from app.modules.execute.domain.enums import RuleMatchStatus, SdwanRuleAction
from app.modules.execute.domain.value_objects import (
    PlannedRuleDraft,
    SdwanPolicyCatalog,
    SdwanRule,
)
from app.modules.execute.services.rules_comparer import RulesComparer


def _zones() -> list[SdwanZone]:
    return [
        SdwanZone(id=1, zone_id=101, name="LAN", type=SdwanZoneType.LAN),
        SdwanZone(id=2, zone_id=102, name="WAN", type=SdwanZoneType.WAN),
    ]


def _catalog(
    *,
    rules: list[SdwanRule] | None = None,
    services: list[SdwanService] | None = None,
    address_objects: list[SdwanAddrObject] | None = None,
    zones: list[SdwanZone] | None = None,
) -> SdwanPolicyCatalog:
    return SdwanPolicyCatalog(
        target_id="target-1",
        rules=rules or [],
        zones=zones or _zones(),
        services=services or [],
        address_objects=address_objects or [],
    )


def _any_service(service_id: int = 100) -> SdwanService:
    return SdwanService(
        id=service_id,
        name="any",
        l4_proto=SdwanServiceL4Proto.ANY,
        ranges=None,
        codes=None,
    )


def _tcp_service(
    service_id: int,
    ranges: tuple[tuple[int, int], ...],
    name: str = "tcp-service",
) -> SdwanService:
    return SdwanService(
        id=service_id,
        name=name,
        l4_proto=SdwanServiceL4Proto.TCP,
        ranges=ranges,
        codes=None,
    )


def _icmp_service(
    service_id: int,
    codes: tuple[str, ...] = ("any",),
    name: str = "icmp-service",
) -> SdwanService:
    return SdwanService(
        id=service_id,
        name=name,
        l4_proto=SdwanServiceL4Proto.ICMP,
        ranges=None,
        codes=codes,
    )


def _existing_rule(
    *,
    rule_id: int = 500,
    action: SdwanRuleAction = SdwanRuleAction.ACCEPT,
    src_addr_objects: list[int] | None = None,
    dst_addr_objects: list[int] | None = None,
    services: list[int] | None = None,
    src_zones: list[int] | None = None,
    dst_zones: list[int] | None = None,
) -> SdwanRule:
    return SdwanRule(
        id=rule_id,
        action=action,
        src_zones=src_zones or [1],
        dst_zones=dst_zones or [2],
        src_addr_objects=src_addr_objects or [],
        dst_addr_objects=dst_addr_objects or [],
        services=services or [100],
    )


def _planned_rule(
    *,
    action: SdwanRuleAction = SdwanRuleAction.ACCEPT,
    src_addr_objects: list[int] | None = None,
    dst_addr_objects: list[int] | None = None,
    services: list[int] | None = None,
    src_zones: list[int] | None = None,
    dst_zones: list[int] | None = None,
) -> PlannedRuleDraft:
    return PlannedRuleDraft(
        action=action,
        src_zones=src_zones or [1],
        dst_zones=dst_zones or [2],
        src_addr_objects=src_addr_objects or [],
        dst_addr_objects=dst_addr_objects or [],
        services=services or [100],
    )


def _host(
    addr_id: int, value: str, *, name: str = "host", parents: tuple[int, ...] = ()
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=addr_id,
        parents=parents,
        name=name,
        type=SdwanAddrObjectType.HOST,
        host=IPv4Address(value),
    )


def _prefix(
    addr_id: int, value: str, *, name: str = "prefix", parents: tuple[int, ...] = ()
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=addr_id,
        parents=parents,
        name=name,
        type=SdwanAddrObjectType.PREFIX,
        prefix=IPv4Network(value),
    )


def _ip_range(
    addr_id: int,
    start: str,
    end: str,
    *,
    name: str = "range",
    parents: tuple[int, ...] = (),
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=addr_id,
        parents=parents,
        name=name,
        type=SdwanAddrObjectType.IP_RANGE,
        ip_range_from=IPv4Address(start),
        ip_range_to=IPv4Address(end),
    )


def _fqdn(
    addr_id: int, value: str, *, name: str = "fqdn", parents: tuple[int, ...] = ()
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=addr_id,
        parents=parents,
        name=name,
        type=SdwanAddrObjectType.FQDN,
        fqdn=value,
    )


def _addr_group(
    addr_id: int,
    group_id: int,
    *,
    name: str = "addr-group",
    parents: tuple[int, ...] = (),
) -> SdwanAddrObject:
    return SdwanAddrObject(
        id=addr_id,
        parents=parents,
        name=name,
        type=SdwanAddrObjectType.ADDR_GROUP,
        addr_group=group_id,
    )


def test_exact_match_with_different_address_object_ids_but_same_host_value() -> None:
    """Разные SD-WAN object ids, но одинаковый host value => EXACT_MATCH."""
    address_objects = [
        _host(10, "10.0.0.10", name="existing-host"),
        _host(20, "10.0.0.10", name="planned-host"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.EXACT_MATCH
    assert result.matched_sdwan_rule_id == 500
    assert "exact match" in result.match_info


def test_host_is_covered_by_existing_subnet() -> None:
    """Host planned object входит в existing subnet => COVERED_MATCH."""
    address_objects = [
        _prefix(10, "10.0.0.0/24", name="existing-subnet"),
        _host(20, "10.0.0.10", name="planned-host"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.COVERED_MATCH
    assert result.matched_sdwan_rule_id == 500
    assert "cover" in result.match_info


def test_subnet_is_covered_by_existing_wider_subnet() -> None:
    """Planned /24 входит в existing /16 => COVERED_MATCH."""
    address_objects = [
        _prefix(10, "10.0.0.0/16", name="existing-wide-subnet"),
        _prefix(20, "10.0.10.0/24", name="planned-subnet"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.COVERED_MATCH


def test_range_is_covered_by_existing_subnet() -> None:
    """Planned IP range полностью лежит внутри existing subnet => COVERED_MATCH."""
    address_objects = [
        _prefix(10, "10.0.0.0/24", name="existing-subnet"),
        _ip_range(20, "10.0.0.10", "10.0.0.20", name="planned-range"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.COVERED_MATCH


def test_fqdn_is_exact_match_by_normalized_string() -> None:
    """FQDN сравнивается строка-в-строку после нормализации."""
    address_objects = [
        _fqdn(10, "Example.COM", name="existing-fqdn"),
        _fqdn(20, "example.com", name="planned-fqdn"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.EXACT_MATCH


def test_fqdn_does_not_match_ip_address_even_if_semantically_related() -> None:
    """FQDN не сравнивается с IP/range/subnet."""
    address_objects = [
        _prefix(10, "10.0.0.0/24", name="existing-subnet"),
        _fqdn(20, "example.com", name="planned-fqdn"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.NEW


def test_address_group_is_flattened_and_matched_by_leaf_values() -> None:
    """Address group раскрывается в плоский список leaf objects."""
    address_objects = [
        _addr_group(10, group_id=777, name="existing-group-object"),
        _host(11, "10.0.0.10", name="existing-group-child", parents=(777,)),
        _host(20, "10.0.0.10", name="planned-host"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_addr_objects=[10], services=[100])],
            services=[_any_service(100)],
            address_objects=address_objects,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_addr_objects=[20], services=[100]),
    )

    assert result.match_status == RuleMatchStatus.EXACT_MATCH


def test_tcp_single_port_is_covered_by_existing_tcp_range() -> None:
    """Planned tcp/443 покрывается existing tcp/1-65535."""
    services = [
        _tcp_service(10, ((1, 65535),), name="existing-all-tcp"),
        _tcp_service(20, ((443, 443),), name="planned-https"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(services=[10])],
            services=services,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[20]),
    )

    assert result.match_status == RuleMatchStatus.COVERED_MATCH


def test_tcp_range_is_not_covered_by_two_separate_existing_ranges_without_merge() -> (
    None
):
    """MVP-ограничение: покрытие объединением ranges не поддерживается.

    existing tcp 80-80 + 81-81 математически покрывает planned tcp 80-81,
    но текущий алгоритм требует, чтобы planned range был покрыт одним existing range.
    """
    services = [
        _tcp_service(10, ((80, 80), (81, 81)), name="existing-split"),
        _tcp_service(20, ((80, 81),), name="planned-merged"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(services=[10])],
            services=services,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[20]),
    )

    assert result.match_status == RuleMatchStatus.NEW


def test_two_planned_tcp_ranges_are_covered_by_one_existing_wider_range() -> None:
    """Один широкий existing range может покрыть несколько planned ranges."""
    services = [
        _tcp_service(10, ((80, 100),), name="existing-wide"),
        _tcp_service(20, ((80, 80), (90, 90)), name="planned-split"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(services=[10])],
            services=services,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[20]),
    )

    assert result.match_status == RuleMatchStatus.COVERED_MATCH


def test_udp_does_not_cover_tcp_same_ports() -> None:
    """Protocol является частью service value."""
    services = [
        SdwanService(
            id=10,
            name="existing-udp-53",
            l4_proto=SdwanServiceL4Proto.UDP,
            ranges=((53, 53),),
            codes=None,
        ),
        _tcp_service(20, ((53, 53),), name="planned-tcp-53"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(services=[10])],
            services=services,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[20]),
    )

    assert result.match_status == RuleMatchStatus.NEW


def test_any_service_covers_tcp_service() -> None:
    """ANY service покрывает конкретный TCP service."""
    services = [
        _any_service(10),
        _tcp_service(20, ((443, 443),), name="planned-https"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(services=[10])],
            services=services,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[20]),
    )

    assert result.match_status == RuleMatchStatus.COVERED_MATCH


def test_ip_ip_does_not_cover_tcp() -> None:
    """IP_IP не является ANY и не покрывает TCP/UDP."""
    services = [
        SdwanService(
            id=10,
            name="existing-ip-ip",
            l4_proto=SdwanServiceL4Proto.IP_IP,
            ranges=None,
            codes=None,
        ),
        _tcp_service(20, ((443, 443),), name="planned-https"),
    ]
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(services=[10])],
            services=services,
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[20]),
    )

    assert result.match_status == RuleMatchStatus.NEW


def test_different_direction_is_not_match() -> None:
    """src/dst zones не взаимозаменяемы."""
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(src_zones=[1], dst_zones=[2])],
            services=[_any_service(100)],
        )
    )

    result = comparer.compare_rule(
        _planned_rule(src_zones=[2], dst_zones=[1]),
    )

    assert result.match_status == RuleMatchStatus.NEW


def test_unknown_planned_service_returns_match_error() -> None:
    """Если planned object/service не загружен в catalog, правило нельзя сравнить."""
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[],
            services=[],
            address_objects=[],
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[999]),
    )

    assert result.match_status == RuleMatchStatus.MATCH_ERROR
    assert result.matched_sdwan_rule_id is None
    assert "Unknown service id" in result.match_info


def test_broken_existing_rule_is_skipped_and_does_not_break_planned_compare() -> None:
    """Некорректное existing rule пропускается, а planned rule сравнивается дальше."""
    comparer = RulesComparer(
        catalog=_catalog(
            rules=[_existing_rule(rule_id=500, services=[999])],
            services=[_any_service(100)],
        )
    )

    result = comparer.compare_rule(
        _planned_rule(services=[100]),
    )

    assert result.match_status == RuleMatchStatus.NEW
    assert result.matched_sdwan_rule_id is None
