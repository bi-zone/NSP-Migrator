"""Focused tests for service object/group materialization semantics."""

from uuid import uuid4

from app.modules.canonical.domain.enums import ObjectKind, OperandRole
from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter

CFG_SERVICE_GROUP = """
object-group service DM_INLINE_TCP_1 tcp
 port-object eq 3334
 port-object eq www
 port-object eq https
 port-object eq ssh
access-list TEST_ACL extended permit ip any any
access-group TEST_ACL global
"""

CFG_ACL_SSH = """
access-list global_access extended permit tcp any any eq ssh
access-group global_access global
"""

CFG_ICMP_GROUP = """
object-group icmp-type ICMP-ECHO
 icmp-object echo
access-list TEST_ACL extended permit icmp any any object-group ICMP-ECHO
access-group TEST_ACL global
"""

CFG_L4_ANY_OBJECTS = """
object service TCP_ANY_OBJECT
 service tcp
object service UDP_ANY_OBJECT
 service udp
access-list TEST_ACL extended permit object TCP_ANY_OBJECT any any
access-group TEST_ACL global
"""

CFG_PROTOCOL_GROUP = """
object-group protocol PROTOCOLS
 protocol-object tcp
 protocol-object udp
 protocol-object gre
access-list TEST_ACL extended permit object-group PROTOCOLS any any
access-group TEST_ACL global
"""

CFG_L4_PORT_OPERATORS = """
object service TCP_LT
 service tcp destination lt 1024
object service UDP_GT
 service udp destination gt 49151
object service TCP_NEQ
 service tcp destination neq 22
object service TCP_SOURCE
 service tcp source eq 1024
object service TCP_SOURCE_DESTINATION
 service tcp source range 1024 65535 destination eq 443
object service TCP_LT_MIN
 service tcp destination lt 0
object service UDP_GT_MAX
 service udp destination gt 65535
access-list TEST_ACL extended permit object TCP_LT any any
access-group TEST_ACL global
"""

CFG_INLINE_L4_PORT_OPERATORS = """
object-group service PORT_OPERATORS
 service-object tcp destination lt 1024
 service-object udp destination gt 49151
 service-object tcp destination neq 22
 service-object udp source range 1024 65535 destination eq 53
access-list TEST_ACL extended permit tcp any any object-group PORT_OPERATORS
access-group TEST_ACL global
"""

CFG_TCP_UDP_SERVICE_GROUP = """
object-group service TCP_UDP_PORTS tcp-udp
 port-object eq domain
 port-object range 5000 5001
access-list TEST_ACL extended permit tcp any any object-group TCP_UDP_PORTS
access-list TEST_ACL extended permit udp any any object-group TCP_UDP_PORTS
access-group TEST_ACL global
"""


def _objects_by_key(outcome):
    return {o.object_key: o for o in outcome.canonical.objects}


# ---------------------------------------------------------------------------
# Service-group and service-reference behavior
# ---------------------------------------------------------------------------
def test_service_group_members_persisted_as_object_members():
    parsed = CiscoAsaParserAdapter().parse(CFG_SERVICE_GROUP)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    parent = _objects_by_key(outcome)["service:DM_INLINE_TCP_1"]
    assert parent.object_kind == ObjectKind.SERVICE_GROUP
    edges = [
        m for m in outcome.canonical.object_members if m.parent_object_id == parent.id
    ]
    assert len(edges) == 4
    child_keys = {
        next(
            o.object_key for o in outcome.canonical.objects if o.id == e.child_object_id
        )
        for e in edges
    }
    assert any("service:tcp:22-22" in k or k.endswith(":22-22") for k in child_keys)
    assert any("service:tcp:80-80" in k for k in child_keys)


def test_tcp_udp_port_objects_expand_to_tcp_and_udp_group_members():
    parsed = CiscoAsaParserAdapter().parse(CFG_TCP_UDP_SERVICE_GROUP)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    by_key = _objects_by_key(outcome)
    parent = by_key["service:TCP_UDP_PORTS"]
    child_ids = {
        member.child_object_id
        for member in outcome.canonical.object_members
        if member.parent_object_id == parent.id
    }
    children = {
        obj.object_key: obj for obj in outcome.canonical.objects if obj.id in child_ids
    }

    assert set(children) == {
        "service:tcp:53-53",
        "service:udp:53-53",
        "service:tcp:5000-5001",
        "service:udp:5000-5001",
    }
    assert children["service:tcp:53-53"].object_kind == ObjectKind.TCP
    assert children["service:tcp:53-53"].name == "tcp:53-53"
    assert children["service:udp:53-53"].object_kind == ObjectKind.UDP
    assert children["service:udp:53-53"].name == "udp:53-53"


def test_tcp_udp_group_rule_operands_are_filtered_by_acl_protocol():
    parsed = CiscoAsaParserAdapter().parse(CFG_TCP_UDP_SERVICE_GROUP)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    objects_by_id = {obj.id: obj for obj in outcome.canonical.objects}
    rules_by_name = {rule.name: rule for rule in outcome.canonical.rules}

    def service_keys(rule_name: str) -> list[str]:
        return [
            objects_by_id[operand.target_object_id].object_key
            for operand in sorted(
                outcome.canonical.operands, key=lambda item: item.position
            )
            if operand.rule_id == rules_by_name[rule_name].id
            and operand.operand_role == OperandRole.SERVICE
            and operand.target_object_id is not None
        ]

    assert service_keys("TEST_ACL:1") == [
        "service:tcp:53-53",
        "service:tcp:5000-5001",
    ]
    assert service_keys("TEST_ACL:2") == [
        "service:udp:53-53",
        "service:udp:5000-5001",
    ]


def test_acl_named_service_ref_resolves_builtin():
    parsed = CiscoAsaParserAdapter().parse(CFG_ACL_SSH)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    by_key = _objects_by_key(outcome)
    assert "service:tcp:22-22" in by_key
    svc = by_key["service:tcp:22-22"]
    assert svc.object_kind == ObjectKind.TCP
    assert svc.port_from == 22
    assert svc.port_to == 22
    unresolved = [o for o in outcome.canonical.objects if "unresolved" in o.object_key]
    assert not any(o.object_kind == ObjectKind.ANY_SERVICE for o in unresolved)


def test_unresolved_service_ref_not_any_service_permissive():
    cfg = """
access-list TEST_ACL extended permit tcp any any eq UNKNOWN_PORT_XYZ
access-group TEST_ACL global
"""
    parsed = CiscoAsaParserAdapter().parse(cfg)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    unresolved = next(
        o
        for o in outcome.canonical.objects
        if o.object_key == "service:unresolved:UNKNOWN_PORT_XYZ"
    )
    assert unresolved.object_kind == ObjectKind.UNRESOLVED_SERVICE
    assert unresolved.object_kind != ObjectKind.ANY_SERVICE
    assert any(
        i.issue_code == "unresolved_service_ref" for i in outcome.canonical.issues
    )


def test_icmp_service_group_not_any_service():
    parsed = CiscoAsaParserAdapter().parse(CFG_ICMP_GROUP)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    group = _objects_by_key(outcome)["service:ICMP-ECHO"]
    assert group.object_kind == ObjectKind.SERVICE_GROUP
    edges = [
        m for m in outcome.canonical.object_members if m.parent_object_id == group.id
    ]
    assert len(edges) >= 1


def test_named_tcp_udp_services_without_ports_keep_l4_kinds():
    parsed = CiscoAsaParserAdapter().parse(CFG_L4_ANY_OBJECTS)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    by_key = _objects_by_key(outcome)

    tcp_service = by_key["service:TCP_ANY_OBJECT"]
    assert tcp_service.object_kind == ObjectKind.TCP
    assert tcp_service.protocol == "tcp"
    assert tcp_service.port_from == 0
    assert tcp_service.port_to == 65535

    udp_service = by_key["service:UDP_ANY_OBJECT"]
    assert udp_service.object_kind == ObjectKind.UDP
    assert udp_service.protocol == "udp"
    assert udp_service.port_from == 0
    assert udp_service.port_to == 65535

    rule = outcome.canonical.rules[0]
    operands = [
        operand for operand in outcome.canonical.operands if operand.rule_id == rule.id
    ]
    service_operand = next(
        operand for operand in operands if operand.operand_role == OperandRole.SERVICE
    )
    assert service_operand.target_object_id == tcp_service.id
    assert not any(
        obj.object_kind == ObjectKind.UNRESOLVED_ADDR and obj.name == "TCP_ANY_OBJECT"
        for obj in outcome.canonical.objects
    )


def test_protocol_group_tcp_udp_members_keep_l4_kinds():
    parsed = CiscoAsaParserAdapter().parse(CFG_PROTOCOL_GROUP)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    by_key = _objects_by_key(outcome)

    assert by_key["service:ip-proto:tcp"].object_kind == ObjectKind.TCP
    assert by_key["service:ip-proto:udp"].object_kind == ObjectKind.UDP
    assert by_key["service:ip-proto:gre"].object_kind == ObjectKind.IP_PROTO


def test_acl_tcp_without_port_operand_uses_tcp_service_instead_of_any():
    cfg = """
access-list TEST_ACL extended permit tcp any any
access-group TEST_ACL global
"""
    parsed = CiscoAsaParserAdapter().parse(cfg)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    rule = outcome.canonical.rules[0]
    service_operand = next(
        operand
        for operand in outcome.canonical.operands
        if operand.rule_id == rule.id and operand.operand_role == OperandRole.SERVICE
    )
    service = next(
        obj
        for obj in outcome.canonical.objects
        if obj.id == service_operand.target_object_id
    )

    assert service.object_kind == ObjectKind.TCP
    assert service.protocol == "tcp"
    assert service.port_from == 0
    assert service.port_to == 65535


def test_named_l4_port_operators_preserve_only_exactly_representable_ranges():
    parsed = CiscoAsaParserAdapter().parse(CFG_L4_PORT_OPERATORS)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    by_key = _objects_by_key(outcome)

    tcp_lt = by_key["service:TCP_LT"]
    assert tcp_lt.object_kind == ObjectKind.TCP
    assert (tcp_lt.port_from, tcp_lt.port_to) == (0, 1023)

    udp_gt = by_key["service:UDP_GT"]
    assert udp_gt.object_kind == ObjectKind.UDP
    assert (udp_gt.port_from, udp_gt.port_to) == (49152, 65535)

    for key in (
        "service:TCP_NEQ",
        "service:TCP_SOURCE",
        "service:TCP_SOURCE_DESTINATION",
        "service:TCP_LT_MIN",
        "service:UDP_GT_MAX",
    ):
        unresolved = by_key[key]
        assert unresolved.object_kind == ObjectKind.UNRESOLVED_SERVICE
        assert unresolved.port_from is None
        assert unresolved.port_to is None


def test_inline_l4_port_operators_do_not_widen_unrepresentable_members():
    parsed = CiscoAsaParserAdapter().parse(CFG_INLINE_L4_PORT_OPERATORS)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    by_key = _objects_by_key(outcome)
    group = by_key["service:PORT_OPERATORS"]
    child_ids = {
        member.child_object_id
        for member in outcome.canonical.object_members
        if member.parent_object_id == group.id
    }
    child_keys = {
        obj.object_key for obj in outcome.canonical.objects if obj.id in child_ids
    }

    assert child_keys == {
        "service:tcp:0-1023",
        "service:udp:49152-65535",
    }
    assert (
        sum(
            issue.issue_code == "unresolved_group_member_ref"
            for issue in outcome.canonical.issues
        )
        == 2
    )
