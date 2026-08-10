"""Focused tests for service object/group materialization semantics."""

from uuid import uuid4

from app.modules.canonical.domain.enums import ObjectKind
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


def _objects_by_key(outcome):
    return {o.object_key: o for o in outcome.canonical.objects}


# ---------------------------------------------------------------------------
# Service-group and service-reference behavior
# ---------------------------------------------------------------------------
def test_service_group_members_persisted_as_object_members():
    parsed = CiscoAsaParserAdapter().parse(CFG_SERVICE_GROUP)
    outcome = CiscoAsaNormalizerAdapter().normalize(
        parsed, source_snapshot_id=uuid4()
    )
    parent = _objects_by_key(outcome)["service:DM_INLINE_TCP_1"]
    assert parent.object_kind == ObjectKind.SERVICE_GROUP
    edges = [
        m
        for m in outcome.canonical.object_members
        if m.parent_object_id == parent.id
    ]
    assert len(edges) == 4
    child_keys = {
        next(o.object_key for o in outcome.canonical.objects if o.id == e.child_object_id)
        for e in edges
    }
    assert any("service:tcp:22-22" in k or k.endswith(":22-22") for k in child_keys)
    assert any("service:tcp:80-80" in k for k in child_keys)


def test_acl_named_service_ref_resolves_builtin():
    parsed = CiscoAsaParserAdapter().parse(CFG_ACL_SSH)
    outcome = CiscoAsaNormalizerAdapter().normalize(
        parsed, source_snapshot_id=uuid4()
    )
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
    outcome = CiscoAsaNormalizerAdapter().normalize(
        parsed, source_snapshot_id=uuid4()
    )
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
    outcome = CiscoAsaNormalizerAdapter().normalize(
        parsed, source_snapshot_id=uuid4()
    )
    group = _objects_by_key(outcome)["service:ICMP-ECHO"]
    assert group.object_kind == ObjectKind.SERVICE_GROUP
    edges = [
        m
        for m in outcome.canonical.object_members
        if m.parent_object_id == group.id
    ]
    assert len(edges) >= 1
