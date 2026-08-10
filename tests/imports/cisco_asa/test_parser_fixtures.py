"""Parser-layer fixture tests (ParsedConfig)."""

from __future__ import annotations

import pytest

from app.core.errors import DomainValidationError
from app.modules.imports.cisco_asa.domain.parsed_config import (
    AclBindingType,
    ParsedObjectType,
    ZoneInferenceStatus,
)

from tests.imports.cisco_asa.helpers import parse_cfg


def _first_rule(tc_id: str):
    parsed = parse_cfg(tc_id)
    assert parsed.rules
    return parsed, parsed.rules[0]


# ---------------------------------------------------------------------------
# Binding and zone inference
# ---------------------------------------------------------------------------
def test_tc_01_acl_iface_in_zones():
    parsed, rule = _first_rule("TC_01")
    assert len(parsed.rules) == 1
    assert rule.rule_name == "ACL_IN:1"
    assert rule.src_zone is None
    assert rule.dst_zone == "inside"
    assert rule.unresolved_zone is False
    assert rule.zone_inference_status == ZoneInferenceStatus.DIRECTIONAL
    assert rule.acl_binding_type == AclBindingType.INTERFACE


def test_tc_05_acl_no_binding_unresolved():
    _, rule = _first_rule("TC_05")
    assert rule.src_zone is None
    assert rule.dst_zone is None
    assert rule.unresolved_zone is True
    assert rule.zone_inference_status == ZoneInferenceStatus.UNKNOWN


def test_tc_06_global_scope():
    _, rule = _first_rule("TC_06")
    assert rule.unresolved_zone is False
    assert rule.zone_inference_status == ZoneInferenceStatus.GLOBAL_SCOPE
    assert rule.acl_binding_type == AclBindingType.GLOBAL


def test_tc_07_unknown_interface_unresolved():
    _, rule = _first_rule("TC_07")
    assert rule.unresolved_zone is True
    assert rule.src_zone is None
    assert rule.dst_zone is None


def test_tc_08_multi_iface_different_zones():
    parsed = parse_cfg("TC_08")
    assert len(parsed.rules) == 2
    by_acl = {rule.acl_name: rule for rule in parsed.rules}
    assert by_acl["ACL_IN"].dst_zone == "inside"
    assert by_acl["ACL_IN"].src_zone is None
    assert by_acl["ACL_OUT"].src_zone == "outside"
    assert by_acl["ACL_OUT"].dst_zone is None


def test_tc_12_ambiguous_no_zones():
    _, rule = _first_rule("TC_12")
    assert rule.unresolved_zone is True
    assert rule.src_zone is None
    assert rule.dst_zone is None


def test_tc_21_acl_name_zone_inference():
    _, rule = _first_rule("TC_21")
    assert rule.src_zone == "inside"
    assert rule.dst_zone == "outside"
    assert rule.unresolved_zone is False
    assert rule.zone_inference_status == ZoneInferenceStatus.DIRECTIONAL


# ---------------------------------------------------------------------------
# Object and service references
# ---------------------------------------------------------------------------
def test_tc_02_acl_object_network_refs():
    parsed = parse_cfg("TC_02")
    obj = next(item for item in parsed.address_objects if item.name == "OBJ_APP")
    assert obj.payload["type"] == "host"
    assert obj.payload["ip"] == "10.10.10.10"
    assert parsed.rules[0].src_ref == "OBJ_APP"


def test_tc_03_object_group_network_members():
    parsed = parse_cfg("TC_03")
    group = next(item for item in parsed.address_objects if item.name == "GRP_NET")
    assert group.kind == ParsedObjectType.ADDRESS_GROUP
    assert len(group.payload["members"]) == 2


def test_tc_04_service_group_in_acl():
    _, rule = _first_rule("TC_04")
    assert rule.service_ref == "WEB_PORTS"
    assert rule.protocol == "tcp"


def test_tc_11_service_group_raw_lines():
    parsed = parse_cfg("TC_11")
    group = next(item for item in parsed.service_objects if item.name == "SVC_MIX")
    assert group.kind == ParsedObjectType.SERVICE_GROUP
    assert group.payload.get("raw_lines")


def test_tc_15_icmp_group_ref():
    _, rule = _first_rule("TC_15")
    assert rule.protocol == "icmp"
    assert rule.service_ref == "ICMP-ECHO"


def test_tc_16_nested_group_members_payload():
    parsed = parse_cfg("TC_16")
    outer = next(item for item in parsed.address_objects if item.name == "GRP_OUTER")
    assert "GRP_INNER" in outer.payload["members"]
    assert "OBJ_LEAF" in outer.payload["members"]


def test_tc_18_subnet_payload():
    parsed = parse_cfg("TC_18")
    obj = next(item for item in parsed.address_objects if item.name == "OBJ_SUBNET")
    assert obj.payload["type"] == "subnet"
    assert obj.payload["ip"] == "10.3.21.0"


def test_tc_19_object_service_payload():
    parsed = parse_cfg("TC_19")
    svc = next(item for item in parsed.service_objects if item.name == "SVC_RDP")
    assert svc.kind == ParsedObjectType.SERVICE


# ---------------------------------------------------------------------------
# Rule semantics and modifiers
# ---------------------------------------------------------------------------
def test_tc_09_two_rules_one_object():
    parsed = parse_cfg("TC_09")
    assert len(parsed.rules) == 2
    assert len(parsed.address_objects) == 1


def test_tc_10_duplicate_rules_preserved():
    parsed = parse_cfg("TC_10")
    assert len(parsed.rules) == 2
    assert parsed.rules[0].rule_name == "ACL_A:1"
    assert parsed.rules[1].rule_name == "ACL_A:2"


def test_tc_13_two_rules_mixed():
    parsed = parse_cfg("TC_13")
    assert len(parsed.rules) == 2
    assert parsed.rules[0].protocol == "tcp"
    assert parsed.rules[1].action == "DENY"


def test_tc_14_log_modifier():
    _, rule = _first_rule("TC_14")
    assert rule.log is True


def test_tc_17_objects_only_raises():
    with pytest.raises(DomainValidationError, match="No ACL rules found"):
        parse_cfg("TC_17")


def test_tc_20_inline_host_dst_ref():
    _, rule = _first_rule("TC_20")
    assert rule.src_ref == "any"
    assert rule.dst_ref == "host:88.218.65.126"


def test_tc_22_inactive_disabled():
    _, rule = _first_rule("TC_22")
    assert rule.enabled is False


def test_tc_23_any4_src_ref():
    _, rule = _first_rule("TC_23")
    assert rule.src_ref == "any"
