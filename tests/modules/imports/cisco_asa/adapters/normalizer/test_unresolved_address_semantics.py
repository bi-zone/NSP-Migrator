from __future__ import annotations

from uuid import uuid4

from app.modules.canonical.domain.enums import ObjectKind, OperandRole
from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter


def _normalize(raw_cfg: str):
    parsed = CiscoAsaParserAdapter().parse(raw_cfg)
    return CiscoAsaNormalizerAdapter().normalize(
        parsed,
        source_snapshot_id=uuid4(),
    )


def test_missing_named_address_is_unresolved_and_not_any() -> None:
    outcome = _normalize(
        """
access-list ACL_IN extended permit ip OBJ_MISSING any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    )
    objects_by_key = {obj.object_key: obj for obj in outcome.canonical.objects}
    unresolved = objects_by_key["addr:unresolved:OBJ_MISSING"]
    any_addr = objects_by_key["addr:any"]

    assert unresolved.object_kind == ObjectKind.UNRESOLVED_ADDR
    assert any_addr.object_kind == ObjectKind.ANY_ADDR

    rule = outcome.canonical.rules[0]
    src_operand = next(
        operand
        for operand in outcome.canonical.operands
        if operand.rule_id == rule.id and operand.operand_role == OperandRole.SRC_OBJECT
    )
    assert src_operand.target_object_id == unresolved.id


def test_unresolved_address_group_member_is_preserved_as_leaf() -> None:
    outcome = _normalize(
        """
object-group network GROUP_WITH_MISSING
 network-object object OBJ_MISSING
access-list ACL_IN extended permit ip object-group GROUP_WITH_MISSING any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    )
    objects_by_key = {obj.object_key: obj for obj in outcome.canonical.objects}
    parent = objects_by_key["addr:GROUP_WITH_MISSING"]
    unresolved = objects_by_key["addr:unresolved:OBJ_MISSING"]
    edges = [
        member
        for member in outcome.canonical.object_members
        if member.parent_object_id == parent.id
    ]

    assert unresolved.object_kind == ObjectKind.UNRESOLVED_ADDR
    assert [edge.child_object_id for edge in edges] == [unresolved.id]
    assert any(
        issue.issue_code == "unresolved_group_member_ref"
        for issue in outcome.canonical.issues
    )


def test_invalid_inline_subnet_mask_is_unresolved_and_not_any() -> None:
    outcome = _normalize(
        """
access-list ACL_IN extended permit ip 10.0.0.0 255.0.255.0 any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    )
    unresolved = next(
        obj
        for obj in outcome.canonical.objects
        if obj.object_key.startswith("addr:unresolved:net:")
    )

    assert unresolved.object_kind == ObjectKind.UNRESOLVED_ADDR
    assert unresolved.object_kind != ObjectKind.ANY_ADDR


def test_unsupported_address_object_payload_is_unresolved() -> None:
    outcome = _normalize(
        """
object network OBJ_WITHOUT_VALUE
 description no supported address value
access-list ACL_IN extended permit ip object OBJ_WITHOUT_VALUE any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    )
    obj = next(
        item
        for item in outcome.canonical.objects
        if item.object_key == "addr:OBJ_WITHOUT_VALUE"
    )

    assert obj.object_kind == ObjectKind.UNRESOLVED_ADDR


def test_reopened_network_object_with_nat_keeps_canonical_host() -> None:
    outcome = _normalize(
        """
object network WEB_SERVER
 description Public web server
 host 10.0.0.2
object network WEB_SERVER
 nat (DMZ,outside) static 100.1.1.2
access-list OUTSIDE_IN extended permit tcp any object WEB_SERVER eq https
access-group OUTSIDE_IN global
"""
    )
    objects_by_key = {obj.object_key: obj for obj in outcome.canonical.objects}
    web_server = objects_by_key["addr:WEB_SERVER"]

    assert web_server.object_kind == ObjectKind.HOST
    assert web_server.cidr == "10.0.0.2/32"
    rule = outcome.canonical.rules[0]
    dst_operand = next(
        operand
        for operand in outcome.canonical.operands
        if operand.rule_id == rule.id and operand.operand_role == OperandRole.DST_OBJECT
    )
    assert dst_operand.target_object_id == web_server.id
