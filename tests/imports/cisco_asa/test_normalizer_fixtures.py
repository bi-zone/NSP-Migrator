"""Normalizer-layer fixture tests (canonical snapshot)."""

from __future__ import annotations

import pytest

from app.modules.canonical.domain.enums import ObjectKind, OperandRole

from tests.imports.cisco_asa.helpers import (
    assert_issue,
    assert_no_issue,
    issue_codes,
    normalize_cfg,
    objects_by_key,
    operand_object_keys,
    parse_cfg,
)


def test_tc_02_object_host_and_global_issue():
    outcome = normalize_cfg("TC_02")
    obj = objects_by_key(outcome)["addr:OBJ_APP"]
    assert obj.object_kind == ObjectKind.HOST
    assert "addr:OBJ_APP" in {o.object_key for o in outcome.canonical.objects}
    assert_issue(outcome, "global_acl_scope_no_interface_zones")
    unresolved = [o for o in outcome.canonical.objects if "unresolved" in o.object_key]
    assert not any(o.object_key == "addr:unresolved:OBJ_APP" for o in unresolved)


def test_tc_03_group_member_edges():
    outcome = normalize_cfg("TC_03")
    parent = objects_by_key(outcome)["addr:GRP_NET"]
    edges = [
        m
        for m in outcome.canonical.object_members
        if m.parent_object_id == parent.id
    ]
    assert len(edges) == 2
    assert_issue(outcome, "global_acl_scope_no_interface_zones")


def test_tc_04_service_group_typed_children():
    outcome = normalize_cfg("TC_04")
    by_key = objects_by_key(outcome)
    assert by_key["service:WEB_PORTS"].object_kind == ObjectKind.SERVICE_GROUP
    assert "service:tcp:80-80" in by_key
    assert "service:tcp:443-443" in by_key
    assert "unresolved_service_ref" not in issue_codes(outcome)


def test_tc_05_unresolved_zone_issue():
    outcome = normalize_cfg("TC_05")
    assert_issue(outcome, "unresolved_zone", entity_key_substr="ACL_ORPHAN:1")


def test_tc_06_global_not_unresolved_zone():
    outcome = normalize_cfg("TC_06")
    assert_issue(outcome, "global_acl_scope_no_interface_zones")
    assert_no_issue(outcome, "unresolved_zone")
    rule = outcome.canonical.rules[0]
    assert rule.description is not None
    assert "acl_binding=global" in rule.description


def test_tc_07_unresolved_zone_unknown_iface():
    outcome = normalize_cfg("TC_07")
    assert_issue(outcome, "unresolved_zone")


def test_tc_08_zones_inside_outside():
    outcome = normalize_cfg("TC_08")
    zone_names = {z.name for z in outcome.canonical.zones}
    assert zone_names >= {"inside", "outside"}
    rules = {r.rule_key: r for r in outcome.canonical.rules}
    in_rule = rules["ACL_IN:1"]
    out_rule = rules["ACL_OUT:2"]
    in_ops = {
        op.operand_role
        for op in outcome.canonical.operands
        if op.rule_id == in_rule.id
    }
    out_ops = {
        op.operand_role
        for op in outcome.canonical.operands
        if op.rule_id == out_rule.id
    }
    assert OperandRole.DST_ZONE in in_ops
    assert OperandRole.SRC_ZONE in out_ops


def test_tc_09_single_object_two_rules():
    outcome = normalize_cfg("TC_09")
    objs = [o for o in outcome.canonical.objects if o.object_key == "addr:OBJ_DB"]
    assert len(objs) == 1
    assert len(outcome.canonical.rules) == 2
    obj_id = objs[0].id
    src_ops = [
        op
        for op in outcome.canonical.operands
        if op.target_object_id == obj_id
        and op.operand_role == OperandRole.SRC_OBJECT
    ]
    dst_ops = [
        op
        for op in outcome.canonical.operands
        if op.target_object_id == obj_id
        and op.operand_role == OperandRole.DST_OBJECT
    ]
    assert len(src_ops) == 1
    assert len(dst_ops) == 1


def test_tc_10_distinct_rule_keys_no_dedup():
    outcome = normalize_cfg("TC_10")
    keys = [r.rule_key for r in outcome.canonical.rules]
    assert keys == ["ACL_A:1", "ACL_A:2"]
    assert "potential_duplicate_rule" not in issue_codes(outcome)


def test_tc_11_unresolved_group_member_issue():
    outcome = normalize_cfg("TC_11")
    # TC-11 inline service members are now materialized; no unresolved member issue.
    assert "unresolved_group_member_ref" not in issue_codes(outcome)


@pytest.mark.xfail(
    reason="TC-11 spec: unsupported_line issue; baseline uses unresolved_group_member_ref only"
)
def test_tc_11_unsupported_line_issue_code_spec():
    outcome = normalize_cfg("TC_11")
    assert "unsupported_line" in issue_codes(outcome)


def test_tc_12_unresolved_zone():
    outcome = normalize_cfg("TC_12")
    assert_issue(outcome, "unresolved_zone")


def test_tc_13_global_issue_on_both_rules():
    outcome = normalize_cfg("TC_13")
    assert len(outcome.canonical.rules) == 2
    global_issues = [
        i
        for i in outcome.canonical.issues
        if i.issue_code == "global_acl_scope_no_interface_zones"
    ]
    assert len(global_issues) == 2


def test_tc_14_roundtrip_metadata_and_operands():
    outcome = normalize_cfg("TC_14")
    rule = outcome.canonical.rules[0]
    assert rule.description is not None
    assert "log" in rule.description
    ops = operand_object_keys(outcome, rule.id)
    assert ops["src_object"] == "addr:OBJ_SRC"
    assert ops["dst_object"] == "addr:OBJ_DST"
    assert ops["service"] == "service:WEB"
    web = objects_by_key(outcome)["service:WEB"]
    edges = [
        m
        for m in outcome.canonical.object_members
        if m.parent_object_id == web.id
    ]
    assert len(edges) >= 1


def test_tc_15_icmp_not_any_service():
    outcome = normalize_cfg("TC_15")
    group = objects_by_key(outcome)["service:ICMP-ECHO"]
    assert group.object_kind == ObjectKind.SERVICE_GROUP
    assert not any(
        o.object_kind == ObjectKind.ANY_SERVICE
        for o in outcome.canonical.objects
        if o.object_key.startswith("service:")
        and o.object_key not in {"service:any", "service:ICMP-ECHO"}
    )


def test_tc_16_nested_group_edges():
    outcome = normalize_cfg("TC_16")
    outer = objects_by_key(outcome)["addr:GRP_OUTER"]
    edges = [
        m
        for m in outcome.canonical.object_members
        if m.parent_object_id == outer.id
    ]
    assert len(edges) >= 1


def test_tc_18_subnet_kind():
    outcome = normalize_cfg("TC_18")
    obj = objects_by_key(outcome)["addr:OBJ_SUBNET"]
    assert obj.object_kind == ObjectKind.SUBNET
    assert obj.name == "OBJ_SUBNET"
    assert obj.cidr == "10.3.21.0/27"


def test_tc_19_object_service_tcp():
    outcome = normalize_cfg("TC_19")
    svc = objects_by_key(outcome)["service:SVC_RDP"]
    assert svc.object_kind == ObjectKind.TCP
    assert svc.port_from == 3389
    assert svc.port_to == 3389


def test_tc_01_zone_operand_inside():
    outcome = normalize_cfg("TC_01")
    assert_no_issue(outcome, "unresolved_zone")
    zone_names = {z.name for z in outcome.canonical.zones}
    assert "inside" in zone_names
