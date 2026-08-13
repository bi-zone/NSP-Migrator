from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.canonical.domain.enums import ObjectKind
from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "config_one_1.cfg"


def _load_sample_outcome():
    raw = SAMPLE.read_text()
    parsed = CiscoAsaParserAdapter().parse(raw)
    outcome = CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())
    return outcome.canonical


@pytest.mark.skip
def test_config_one_1_regression_key_counts():
    cmd = _load_sample_outcome()

    assert len(cmd.rules) == 25
    group = next(
        o for o in cmd.objects if o.object_key == "addr:OBJ_GRP_HOST_SD-134797_service"
    )
    member_edges = [
        m for m in cmd.object_members if m.parent_object_id == group.id
    ]
    assert len(member_edges) == 3

    svc_group = next(
        o for o in cmd.objects if o.object_key == "service:DM_INLINE_TCP_1"
    )
    assert svc_group.object_kind == ObjectKind.SERVICE_GROUP
    svc_edges = [m for m in cmd.object_members if m.parent_object_id == svc_group.id]
    assert len(svc_edges) == 4

    global_rule_keys = {r.rule_key for r in cmd.rules if r.section == "global_access"}
    global_issues = [
        i
        for i in cmd.issues
        if i.entity_key in global_rule_keys
        and i.issue_code in {
            "global_acl_scope_no_interface_zones",
            "unresolved_zone",
        }
    ]
    assert all(
        i.issue_code == "global_acl_scope_no_interface_zones" for i in global_issues
    )
    assert len(global_issues) == len(global_rule_keys)

    ssh_objects = [
        o
        for o in cmd.objects
        if o.object_kind == ObjectKind.TCP and o.port_from == 22
    ]
    assert len(ssh_objects) >= 1
