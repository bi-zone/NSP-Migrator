"""Address-group membership and global-scope regression tests."""

from uuid import uuid4

from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter
from app.modules.imports.cisco_asa.domain.parsed_config import ParsedObjectType


CFG_ADDRESS_GROUP_OBJECT = """
object network OBJ_HOST_10.3.21.5
 host 10.3.21.5
object-group network OBJ_GRP_HOST_SD-134797_service
 network-object object OBJ_HOST_10.3.21.5
 network-object object OBJ_HOST_10.3.21.6
access-list TEST_ACL extended permit ip any any
access-group TEST_ACL global
"""

CFG_GLOBAL_ACL = """
access-list global_access extended permit tcp any any eq ssh
access-group global_access global
"""


def _normalize(raw_cfg: str):
    parsed = CiscoAsaParserAdapter().parse(raw_cfg)
    return CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())


# ---------------------------------------------------------------------------
# Address group parsing/materialization
# ---------------------------------------------------------------------------
def test_parse_network_object_object_member_refs():
    parsed = CiscoAsaParserAdapter().parse(CFG_ADDRESS_GROUP_OBJECT)
    group = next(
        o
        for o in parsed.address_objects
        if o.name == "OBJ_GRP_HOST_SD-134797_service"
    )
    assert group.kind == ParsedObjectType.ADDRESS_GROUP
    assert "OBJ_HOST_10.3.21.5" in group.payload["members"]
    assert not any("net:object/" in str(m) for m in group.payload["members"])


def test_normalize_address_group_membership_edges_created():
    outcome = _normalize(CFG_ADDRESS_GROUP_OBJECT)
    cmd = outcome.canonical
    members = [
        m
        for m in cmd.object_members
        if any(
            o.object_key == "addr:OBJ_GRP_HOST_SD-134797_service" for o in cmd.objects
        )
    ]
    parent = next(
        o for o in cmd.objects if o.object_key == "addr:OBJ_GRP_HOST_SD-134797_service"
    )
    edges = [m for m in cmd.object_members if m.parent_object_id == parent.id]
    assert len(edges) >= 1
    child_keys = {
        next(o.object_key for o in cmd.objects if o.id == e.child_object_id)
        for e in edges
    }
    assert "addr:OBJ_HOST_10.3.21.5" in child_keys


# ---------------------------------------------------------------------------
# Global ACL binding semantics
# ---------------------------------------------------------------------------
def test_global_access_group_marks_non_directional_scope():
    parsed = CiscoAsaParserAdapter().parse(CFG_GLOBAL_ACL)
    rule = parsed.rules[0]
    assert rule.unresolved_zone is False
    assert rule.zone_inference_status.value == "global_scope"

    outcome = _normalize(CFG_GLOBAL_ACL)
    issue_codes = {i.issue_code for i in outcome.canonical.issues}
    assert "global_acl_scope_no_interface_zones" in issue_codes
    assert "unresolved_zone" not in issue_codes
    rule_entity = outcome.canonical.rules[0]
    assert rule_entity.description is not None
    assert "acl_binding=global" in rule_entity.description
