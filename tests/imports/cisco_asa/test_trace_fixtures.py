"""Trace-layer fixture tests (raw → canonical lineage)."""

from __future__ import annotations

import pytest

from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole

from tests.imports.cisco_asa.helpers import (
    assert_rule_has_trace,
    assert_trace_line,
    issue_codes,
    line_number_for_substring,
    load_cfg,
    normalize_cfg,
    objects_by_key,
    trace_for_entity,
    traces_on_line,
)


def test_tc_01_rule_and_dst_zone_trace():
    cfg = load_cfg("TC_01")
    outcome = normalize_cfg("TC_01")
    rule = outcome.canonical.rules[0]
    assert_rule_has_trace(outcome, rule.id)
    acl_line = line_number_for_substring(cfg, "access-list ACL_IN")
    records = outcome.trace.records
    assert_trace_line(records, acl_line, TraceCanonicalKind.RULE)
    dst_zone_ops = [
        op
        for op in outcome.canonical.operands
        if op.rule_id == rule.id and op.operand_role.value == "dst_zone"
    ]
    assert dst_zone_ops
    assert_trace_line(
        records,
        acl_line,
        TraceCanonicalKind.RULE_OPERAND,
        role=TraceCanonicalRole.DST_ZONE.value,
    )


def test_tc_02_object_header_trace():
    cfg = load_cfg("TC_02")
    outcome = normalize_cfg("TC_02")
    obj = objects_by_key(outcome)["addr:OBJ_APP"]
    obj_line = line_number_for_substring(cfg, "object network OBJ_APP")
    hits = trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=obj.id,
    )
    assert hits
    assert hits[0].source_line_start == obj_line
    assert hits[0].canonical_role == TraceCanonicalRole.HEADER.value


def test_tc_03_group_header_and_member_traces():
    outcome = normalize_cfg("TC_03")
    parent = objects_by_key(outcome)["addr:GRP_NET"]
    header_traces = trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=parent.id,
    )
    assert header_traces
    member_traces = [
        r
        for r in outcome.trace.records
        if r.canonical_kind == TraceCanonicalKind.OBJECT_MEMBER
        and r.canonical_role == TraceCanonicalRole.MEMBER_REF.value
    ]
    assert len(member_traces) >= 2


def test_tc_04_service_operand_trace():
    cfg = load_cfg("TC_04")
    outcome = normalize_cfg("TC_04")
    rule = outcome.canonical.rules[0]
    acl_line = line_number_for_substring(cfg, "access-list ACL_A")
    assert_trace_line(
        outcome.trace.records,
        acl_line,
        TraceCanonicalKind.RULE_OPERAND,
        role=TraceCanonicalRole.SERVICE.value,
    )
    web = objects_by_key(outcome)["service:WEB_PORTS"]
    assert trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=web.id,
    )


def test_tc_05_issue_trace_on_acl_line():
    cfg = load_cfg("TC_05")
    outcome = normalize_cfg("TC_05")
    acl_line = line_number_for_substring(cfg, "access-list ACL_ORPHAN")
    issue = next(
        i for i in outcome.canonical.issues if i.issue_code == "unresolved_zone"
    )
    issue_traces = trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.ISSUE,
        canonical_id=issue.id,
    )
    assert issue_traces
    assert issue_traces[0].source_line_start == acl_line
    assert_rule_has_trace(outcome, outcome.canonical.rules[0].id)


def test_tc_06_global_issue_trace():
    cfg = load_cfg("TC_06")
    outcome = normalize_cfg("TC_06")
    acl_line = line_number_for_substring(cfg, "access-list ACL_A")
    issue = next(
        i
        for i in outcome.canonical.issues
        if i.issue_code == "global_acl_scope_no_interface_zones"
    )
    hits = trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.ISSUE,
        canonical_id=issue.id,
    )
    assert hits
    assert hits[0].source_line_start == acl_line


def test_tc_11_issue_trace_baseline():
    outcome = normalize_cfg("TC_11")
    assert not any(
        i.issue_code == "unresolved_group_member_ref"
        for i in outcome.canonical.issues
    )


@pytest.mark.xfail(
    reason="TC-11 spec: trace on unsupported child line; baseline traces group header only"
)
def test_tc_11_trace_on_unsupported_line_spec():
    cfg = load_cfg("TC_11")
    outcome = normalize_cfg("TC_11")
    line_no = line_number_for_substring(cfg, "strange-unsupported-token")
    hits = traces_on_line(outcome.trace.records, line_no)
    assert any(r.canonical_kind == TraceCanonicalKind.ISSUE for r in hits)


def test_tc_12_issue_and_rule_same_line():
    cfg = load_cfg("TC_12")
    outcome = normalize_cfg("TC_12")
    acl_line = line_number_for_substring(cfg, "access-list RANDOM_ACL")
    assert_trace_line(outcome.trace.records, acl_line, TraceCanonicalKind.RULE)
    issue = next(
        i for i in outcome.canonical.issues if i.issue_code == "unresolved_zone"
    )
    assert trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.ISSUE,
        canonical_id=issue.id,
    )


def test_tc_13_every_rule_has_rule_trace():
    outcome = normalize_cfg("TC_13")
    for rule in outcome.canonical.rules:
        assert_rule_has_trace(outcome, rule.id)


def test_tc_14_object_rule_operand_traces():
    cfg = load_cfg("TC_14")
    outcome = normalize_cfg("TC_14")
    for key in ("addr:OBJ_SRC", "addr:OBJ_DST", "service:WEB"):
        obj = objects_by_key(outcome)[key]
        assert trace_for_entity(
            outcome.trace.records,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=obj.id,
        )
    rule = outcome.canonical.rules[0]
    assert_rule_has_trace(outcome, rule.id)
    acl_line = line_number_for_substring(cfg, "access-list ACL_A extended permit tcp")
    assert_trace_line(
        outcome.trace.records,
        acl_line,
        TraceCanonicalKind.RULE_OPERAND,
        role=TraceCanonicalRole.SRC_OBJECT.value,
    )


def test_tc_08_distinct_rule_traces():
    outcome = normalize_cfg("TC_08")
    rule_traces = [
        r
        for r in outcome.trace.records
        if r.canonical_kind == TraceCanonicalKind.RULE
    ]
    assert len(rule_traces) == 2
    lines = {r.source_line_start for r in rule_traces}
    assert len(lines) == 2


def test_tc_09_single_object_trace_two_operand_traces():
    outcome = normalize_cfg("TC_09")
    obj = objects_by_key(outcome)["addr:OBJ_DB"]
    obj_traces = trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=obj.id,
    )
    assert len(obj_traces) == 1
    operand_traces = [
        r
        for r in outcome.trace.records
        if r.canonical_kind == TraceCanonicalKind.RULE_OPERAND
        and r.canonical_role
        in {
            TraceCanonicalRole.SRC_OBJECT.value,
            TraceCanonicalRole.DST_OBJECT.value,
        }
        and r.source_fragment == "OBJ_DB"
    ]
    assert len(operand_traces) == 2


def test_tc_10_two_rule_traces():
    outcome = normalize_cfg("TC_10")
    rule_traces = [
        r
        for r in outcome.trace.records
        if r.canonical_kind == TraceCanonicalKind.RULE
    ]
    assert len(rule_traces) == 2
