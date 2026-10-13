from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from app.modules.trace.domain.enums import TraceCanonicalKind
from streamlit_app.components.trace.view_model import (
    CanonicalDeepLink,
    TraceDeepLink,
    build_canonical_url,
    build_trace_url,
    object_value,
    parse_trace_deep_link,
    parse_canonical_deep_link,
    ranges_overlap,
    source_excerpt,
)
from streamlit_app.views.trace_rules import (
    _dependency_source_context,
    _object_tree_lines,
    _protocol_only_explanation,
    _rule_ids_for_deep_link,
)


def test_trace_deep_link_round_trip_preserves_entity_context() -> None:
    source_snapshot_id = uuid4()
    canonical_snapshot_id = uuid4()
    canonical_id = uuid4()

    url = build_trace_url(
        source_snapshot_id=str(source_snapshot_id),
        canonical_snapshot_id=str(canonical_snapshot_id),
        canonical_kind="object",
        canonical_id=str(canonical_id),
    )

    parsed_url = urlparse(url)
    params = {key: values[-1] for key, values in parse_qs(parsed_url.query).items()}
    parsed = parse_trace_deep_link(params)

    assert parsed_url.path == "/trace-rules"
    assert parsed == TraceDeepLink(
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=canonical_snapshot_id,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=canonical_id,
    )


def test_parse_trace_deep_link_rejects_partial_or_invalid_filter() -> None:
    assert parse_trace_deep_link({"canonical_id": str(uuid4())}) is None
    assert (
        parse_trace_deep_link(
            {
                "source_snapshot_id": str(uuid4()),
                "canonical_snapshot_id": str(uuid4()),
                "canonical_kind": "unknown",
                "canonical_id": str(uuid4()),
            }
        )
        is None
    )


def test_canonical_deep_link_round_trip_keeps_rule_context() -> None:
    source_snapshot_id = uuid4()
    canonical_snapshot_id = uuid4()
    canonical_id = uuid4()
    context_rule_id = uuid4()

    url = build_canonical_url(
        source_snapshot_id=str(source_snapshot_id),
        canonical_snapshot_id=str(canonical_snapshot_id),
        canonical_kind="object",
        canonical_id=str(canonical_id),
        context_rule_id=str(context_rule_id),
    )

    parsed_url = urlparse(url)
    params = {key: values[-1] for key, values in parse_qs(parsed_url.query).items()}

    assert parsed_url.path == "/canonical-rules"
    assert parse_canonical_deep_link(params) == CanonicalDeepLink(
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=canonical_snapshot_id,
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=canonical_id,
        context_rule_id=context_rule_id,
    )


def test_source_excerpt_returns_numbered_inclusive_lines() -> None:
    assert source_excerpt("one\ntwo\nthree", line_start=2, line_end=3) == [
        {"line": 2, "text": "two"},
        {"line": 3, "text": "three"},
    ]


def test_object_value_prefers_user_facing_network_and_service_values() -> None:
    assert object_value({"object_kind": "subnet", "cidr": "10.0.0.0/24"}) == (
        "10.0.0.0/24"
    )
    assert (
        object_value(
            {
                "object_kind": "tcp",
                "protocol": "tcp",
                "port_from": 443,
                "port_to": 443,
            }
        )
        == "TCP 443"
    )
    assert object_value({"object_kind": "addr_group"}) == "Group"


def test_ranges_overlap_uses_inclusive_boundaries() -> None:
    assert ranges_overlap(10, 12, 12, 15)
    assert not ranges_overlap(10, 12, 13, 15)
    assert not ranges_overlap(10, 12, None, None)


def test_object_tree_renders_nested_groups_and_stops_cycles() -> None:
    root_id = str(uuid4())
    nested_id = str(uuid4())
    leaf_id = str(uuid4())
    root_member_id = str(uuid4())
    leaf_member_id = str(uuid4())
    cycle_member_id = str(uuid4())
    objects = {
        root_id: {
            "name": "ROOT",
            "object_kind": "addr_group",
            "is_group": True,
        },
        nested_id: {
            "name": "NESTED",
            "object_kind": "addr_group",
            "is_group": True,
        },
        leaf_id: {
            "name": "HOST_1",
            "object_kind": "host",
            "cidr": "10.0.0.1/32",
            "is_group": False,
        },
    }
    graph = {
        "by_parent": {
            root_id: [
                {
                    "member_id": root_member_id,
                    "child_object_id": nested_id,
                }
            ],
            nested_id: [
                {
                    "member_id": leaf_member_id,
                    "child_object_id": leaf_id,
                },
                {
                    "member_id": cycle_member_id,
                    "child_object_id": root_id,
                },
            ],
        }
    }

    lines, entities = _object_tree_lines(
        root_id,
        objects=objects,
        member_graph=graph,
    )

    rendered = "\n".join(lines)
    assert "ROOT" in rendered
    assert "NESTED" in rendered
    assert "HOST_1" in rendered
    assert "cycle" in rendered
    assert ("object_member", leaf_member_id) in entities
    assert ("object", leaf_id) in entities


def test_nested_object_deep_link_resolves_rules_using_ancestor_groups() -> None:
    rule_id = str(uuid4())
    operand_id = str(uuid4())
    root_group_id = str(uuid4())
    nested_group_id = str(uuid4())
    leaf_id = str(uuid4())
    source_snapshot_id = uuid4()
    canonical_snapshot_id = uuid4()
    scope = {
        "rules": [
            {
                "id": rule_id,
                "operands": [
                    {
                        "id": operand_id,
                        "target_object_id": root_group_id,
                        "target_zone_id": None,
                    }
                ],
            }
        ]
    }
    rule_indexes = {
        "operand_to_rule": {operand_id: rule_id},
        "target_to_rules": {("object", root_group_id): {rule_id}},
    }
    member_graph = {
        "by_parent": {},
        "child_to_parents": {
            leaf_id: {nested_group_id},
            nested_group_id: {root_group_id},
        },
    }

    result = _rule_ids_for_deep_link(
        TraceDeepLink(
            source_snapshot_id=source_snapshot_id,
            canonical_snapshot_id=canonical_snapshot_id,
            canonical_kind=TraceCanonicalKind.OBJECT,
            canonical_id=UUID(leaf_id),
        ),
        scope=scope,
        rule_indexes=rule_indexes,
        member_graph=member_graph,
        issues=[],
        rows_by_entity={},
    )

    assert result == {rule_id}


def test_dependency_context_hides_other_rules_using_shared_implicit_service() -> None:
    service_id = str(uuid4())
    rows_by_entity = {
        ("object", service_id): [
            {
                "source_line_start": line,
                "source_line_end": line,
                "canonical_role": "service",
            }
            for line in (233, 235, 246, 247, 248, 249, 253, 254, 256, 257, 258, 259, 260)
        ]
    }

    ranges, used_inline = _dependency_source_context(
        {("object", service_id)},
        rows_by_entity=rows_by_entity,
        rule_ranges=[(254, 254)],
    )

    assert ranges == []
    assert used_inline is True


def test_dependency_context_keeps_named_object_definition() -> None:
    object_id = str(uuid4())
    rows_by_entity = {
        ("object", object_id): [
            {
                "source_line_start": 111,
                "source_line_end": 111,
                "canonical_role": "header",
            },
            {
                "source_line_start": 254,
                "source_line_end": 254,
                "canonical_role": "src_object",
            },
        ]
    }

    ranges, used_inline = _dependency_source_context(
        {("object", object_id)},
        rows_by_entity=rows_by_entity,
        rule_ranges=[(254, 254)],
    )

    assert ranges == [(111, 111)]
    assert used_inline is False


def test_protocol_only_explanation_uses_canonical_ip_proto_object() -> None:
    result = _protocol_only_explanation(
        {
            "object_key": "service:ip-proto:icmp",
            "object_kind": "icmp",
            "protocol": "icmp",
        }
    )

    assert result == (
        "ICMP",
        "Matches all ICMP message types. It is taken directly from the source rule above.",
    )


def test_protocol_only_explanation_ignores_true_any_service() -> None:
    assert (
        _protocol_only_explanation(
            {
                "object_key": "service:any",
                "object_kind": "any_service",
                "protocol": None,
            }
        )
        is None
    )
