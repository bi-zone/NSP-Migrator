from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import pandas as pd
import streamlit as st

from app.modules.canonical.application.use_cases.get_canonical_issues import (
    GetCanonicalIssuesQuery,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceQuery,
)
from app.modules.canonical.ports.rule_repository import CanonicalRuleFilters
from app.modules.imports.application.use_cases.get_source_artifact import (
    GetSourceArtifactQuery,
)
from app.modules.imports.application.use_cases.get_source_snapshots import (
    GetSourceSnapshotsQuery,
)
from app.modules.trace.application.dto import GetTraceForCanonicalSnapshotQuery
from streamlit_app.components.trace.view_model import (
    KIND_LABELS,
    ROLE_LABELS,
    TraceDeepLink,
    build_canonical_url,
    compact_uuid,
    object_value,
    parse_trace_deep_link,
    ranges_overlap,
    source_excerpt,
)
from streamlit_app.services.use_cases import (
    get_canonical_issues,
    get_canonical_object,
    get_canonical_rule_scope,
    get_latest_canonical_snapshot_for_source,
    get_source_artifact,
    get_source_snapshots,
    get_trace_for_canonical_snapshot,
    run_async,
)
from streamlit_app.session.context import get_context

TRACE_FETCH_LIMIT = 10_000
SNAPSHOT_OPTIONS_LIMIT = 300
LEGACY_ZONE_INFO_CODES = {
    "global_acl_scope_no_interface_zones",
    "unresolved_zone",
}
GROUP_KINDS = {"addr_group", "service_group"}
OBJECT_ROLES = {"src_object", "dst_object", "service"}
ZONE_ROLES = {"src_zone", "dst_zone"}


def render() -> None:
    st.title("Trace")
    st.caption("See what each canonical rule was built from and why.")
    _ensure_page_state()

    deep_link = parse_trace_deep_link(st.query_params.to_dict())
    snapshots = _load_mapped_snapshot_options()
    if not snapshots:
        st.info("No mapped configurations yet. Upload and map a config first.")
        return

    selected_snapshot = _render_snapshot_selector(snapshots, deep_link)
    if selected_snapshot is None:
        return

    source_snapshot_id = UUID(selected_snapshot["source_snapshot_id"])
    canonical_snapshot_id = UUID(selected_snapshot["canonical_snapshot_id"])
    context = get_context()
    context.snapshot_id = source_snapshot_id
    context.canonical_snapshot_id = canonical_snapshot_id

    if deep_link and not _deep_link_matches_snapshot(
        deep_link,
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=canonical_snapshot_id,
    ):
        st.warning(
            "This link points to a different snapshot. Select the snapshot from the link "
            "or clear the entity filter."
        )

    rows = _load_trace_rows(canonical_snapshot_id)
    if not rows:
        st.warning("No trace evidence is stored for this configuration.")
        return
    if len(rows) == TRACE_FETCH_LIMIT:
        st.warning(
            f"Only the first {TRACE_FETCH_LIMIT:,} trace records are loaded. "
            "Some evidence may be missing."
        )

    scope = _load_canonical_scope(canonical_snapshot_id)
    if not scope["rules"]:
        st.warning("No canonical rules are available for this configuration.")
        return

    raw_text = _load_source_text(source_snapshot_id)
    issues = _load_canonical_issues(canonical_snapshot_id)
    member_graph = _build_member_graph(canonical_snapshot_id, scope["objects"])
    rows_by_entity = _index_rows_by_entity(rows)
    rule_indexes = _build_rule_indexes(scope)
    issues_by_rule = _index_issues_by_rule(scope["rules"], rows_by_entity, issues)

    entity_rule_ids: set[str] | None = None
    if deep_link and _deep_link_matches_snapshot(
        deep_link,
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=canonical_snapshot_id,
    ):
        entity_rule_ids = _rule_ids_for_deep_link(
            deep_link,
            scope=scope,
            rule_indexes=rule_indexes,
            member_graph=member_graph,
            issues=issues,
            rows_by_entity=rows_by_entity,
        )
        _render_entity_filter_banner(deep_link, rows_by_entity, entity_rule_ids)

    filtered_rules = _render_rule_filters(
        scope["rules"],
        scope=scope,
        rows_by_entity=rows_by_entity,
        issues_by_rule=issues_by_rule,
        entity_rule_ids=entity_rule_ids,
    )
    if not filtered_rules:
        st.info("No rules match the current filters.")
        return

    selected_rule = _render_rule_selector(
        filtered_rules,
        issues_by_rule=issues_by_rule,
        preferred_rule_id=_preferred_rule_id(deep_link, entity_rule_ids),
    )
    if selected_rule is None:
        return

    _render_rule_inspector(
        selected_rule,
        scope=scope,
        rows=rows,
        rows_by_entity=rows_by_entity,
        issues=issues_by_rule.get(selected_rule["id"], []),
        raw_text=raw_text,
        member_graph=member_graph,
        source_snapshot_id=str(source_snapshot_id),
        canonical_snapshot_id=str(canonical_snapshot_id),
    )


def _ensure_page_state() -> None:
    st.session_state.setdefault("trace_selected_source_snapshot", None)
    st.session_state.setdefault("trace_rule_search", "")
    st.session_state.setdefault("trace_only_issues", False)
    st.session_state.setdefault("trace_selected_rule_id", None)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_mapped_snapshot_options() -> list[dict[str, str]]:
    result = run_async(
        get_source_snapshots().execute(
            GetSourceSnapshotsQuery(limit=SNAPSHOT_OPTIONS_LIMIT)
        )
    )
    options: list[dict[str, str]] = []
    for snapshot in result.snapshots:
        latest = run_async(
            get_latest_canonical_snapshot_for_source().execute(
                GetLatestCanonicalSnapshotForSourceQuery(source_snapshot_id=snapshot.id)
            )
        )
        if latest.snapshot is None:
            continue
        options.append(
            {
                "source_snapshot_id": str(snapshot.id),
                "canonical_snapshot_id": str(latest.snapshot.id),
                "source_name": snapshot.source_name or "Unknown source",
                "file_name": snapshot.file_name or "Unknown file",
                "created_at": snapshot.created_at.strftime("%Y-%m-%d %H:%M"),
            }
        )
    return options


def _load_mapped_snapshot_options() -> list[dict[str, str]]:
    try:
        with st.spinner("Loading mapped configurations..."):
            return _cached_mapped_snapshot_options()
    except Exception as error:
        st.error(f"Failed to load mapped configurations: {error}")
        return []


def _snapshot_label(option: dict[str, str]) -> str:
    return f"{option['source_name']} · {option['file_name']} · {option['created_at']}"


def _render_snapshot_selector(
    snapshots: list[dict[str, str]],
    deep_link: TraceDeepLink | None,
) -> dict[str, str] | None:
    options_by_id = {item["source_snapshot_id"]: item for item in snapshots}
    option_ids = list(options_by_id)
    context = get_context()
    preferred = None
    if deep_link and str(deep_link.source_snapshot_id) in options_by_id:
        preferred = str(deep_link.source_snapshot_id)
    elif context.snapshot_id and str(context.snapshot_id) in options_by_id:
        preferred = str(context.snapshot_id)
    elif st.session_state["trace_selected_source_snapshot"] in options_by_id:
        preferred = st.session_state["trace_selected_source_snapshot"]
    if preferred is None:
        preferred = option_ids[0]

    current = st.session_state.get("trace_snapshot_selector")
    if current not in options_by_id or deep_link:
        st.session_state["trace_snapshot_selector"] = preferred

    selected_id = st.selectbox(
        "Configuration",
        options=option_ids,
        key="trace_snapshot_selector",
        format_func=lambda item_id: _snapshot_label(options_by_id[item_id]),
    )
    st.session_state["trace_selected_source_snapshot"] = selected_id
    return options_by_id.get(selected_id)


def _deep_link_matches_snapshot(
    deep_link: TraceDeepLink,
    *,
    source_snapshot_id: UUID,
    canonical_snapshot_id: UUID,
) -> bool:
    return (
        deep_link.source_snapshot_id == source_snapshot_id
        and deep_link.canonical_snapshot_id == canonical_snapshot_id
    )


@st.cache_data(ttl=30, show_spinner=False)
def _cached_trace_rows(canonical_snapshot_id: str) -> list[dict[str, Any]]:
    result = run_async(
        get_trace_for_canonical_snapshot().execute(
            GetTraceForCanonicalSnapshotQuery(
                canonical_snapshot_id=UUID(canonical_snapshot_id),
                limit=TRACE_FETCH_LIMIT,
                offset=0,
            )
        )
    )
    return [
        {
            "id": str(row.id),
            "source_snapshot_id": str(row.source_snapshot_id),
            "canonical_snapshot_id": str(row.canonical_snapshot_id),
            "vendor_code": row.vendor_code,
            "normalizer_code": row.normalizer_code,
            "normalizer_version": row.normalizer_version,
            "source_line_start": row.source_line_start,
            "source_line_end": row.source_line_end,
            "source_fragment": row.source_fragment,
            "canonical_kind": row.canonical_kind,
            "canonical_id": str(row.canonical_id),
            "canonical_role": row.canonical_role,
            "note": row.note,
        }
        for row in result
    ]


def _load_trace_rows(canonical_snapshot_id: UUID) -> list[dict[str, Any]]:
    try:
        with st.spinner("Loading trace evidence..."):
            return _cached_trace_rows(str(canonical_snapshot_id))
    except Exception as error:
        st.error(f"Failed to load trace evidence: {error}")
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _cached_source_text(source_snapshot_id: str) -> str:
    result = run_async(
        get_source_artifact().execute(
            GetSourceArtifactQuery(source_snapshot_id=UUID(source_snapshot_id))
        )
    )
    return result.raw_text


def _load_source_text(source_snapshot_id: UUID) -> str:
    try:
        return _cached_source_text(str(source_snapshot_id))
    except Exception as error:
        st.warning(f"The original configuration could not be loaded: {error}")
        return ""


@st.cache_data(ttl=30, show_spinner=False)
def _cached_canonical_issues(canonical_snapshot_id: str) -> list[dict[str, Any]]:
    result = run_async(
        get_canonical_issues().execute(
            GetCanonicalIssuesQuery(canonical_snapshot_id=UUID(canonical_snapshot_id))
        )
    )
    return [
        {
            "id": str(issue.id),
            "issue_code": issue.issue_code,
            "message": issue.message,
            "entity_type": issue.entity_type,
            "entity_key": issue.entity_key,
            "source_line_start": issue.source_line_start,
            "source_line_end": issue.source_line_end,
        }
        for issue in result.issues
        if issue.issue_code not in LEGACY_ZONE_INFO_CODES
    ]


def _load_canonical_issues(canonical_snapshot_id: UUID) -> list[dict[str, Any]]:
    try:
        return _cached_canonical_issues(str(canonical_snapshot_id))
    except Exception:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def _cached_canonical_scope(canonical_snapshot_id: str) -> dict[str, Any]:
    result = run_async(
        get_canonical_rule_scope().execute(
            GetCanonicalRuleScopeQuery(
                canonical_snapshot_id=UUID(canonical_snapshot_id),
                limit=None,
                offset=0,
                filters=CanonicalRuleFilters(),
                include_all_zones=True,
            )
        )
    )
    return {
        "rules": [
            {
                "id": str(rule.id),
                "name": rule.name,
                "rule_key": rule.rule_key,
                "action": rule.action,
                "enabled": rule.enabled,
                "priority": rule.priority,
                "section": rule.section or "",
                "operands": [
                    {
                        "id": str(operand.id),
                        "role": str(operand.operand_role),
                        "position": operand.position,
                        "target_zone_id": str(operand.target_zone_id)
                        if operand.target_zone_id
                        else None,
                        "target_object_id": str(operand.target_object_id)
                        if operand.target_object_id
                        else None,
                    }
                    for operand in (rule.operands or [])
                ],
            }
            for rule in result.rules
        ],
        "objects": {
            str(obj.id): {
                "id": str(obj.id),
                "name": obj.name or obj.object_key or str(obj.id),
                "object_key": obj.object_key,
                "object_family": str(obj.object_family),
                "object_kind": str(obj.object_kind),
                "cidr": obj.cidr,
                "range_start": str(obj.range_start) if obj.range_start else None,
                "range_end": str(obj.range_end) if obj.range_end else None,
                "fqdn": obj.fqdn,
                "protocol": obj.protocol,
                "port_from": obj.port_from,
                "port_to": obj.port_to,
                "icmp_type": obj.icmp_type,
                "icmp_code": obj.icmp_code,
                "is_group": str(obj.object_kind) in GROUP_KINDS,
            }
            for obj in result.objects
        },
        "zones": {
            str(zone.id): {
                "id": str(zone.id),
                "name": zone.name,
                "zone_key": zone.zone_key,
            }
            for zone in result.zones
        },
    }


def _load_canonical_scope(canonical_snapshot_id: UUID) -> dict[str, Any]:
    try:
        with st.spinner("Building rule context..."):
            return _cached_canonical_scope(str(canonical_snapshot_id))
    except Exception as error:
        st.error(f"Failed to load canonical rules: {error}")
        return {"rules": [], "objects": {}, "zones": {}}


@st.cache_data(ttl=30, show_spinner=False)
def _cached_object_members(
    canonical_snapshot_id: str,
    parent_object_id: str,
) -> list[dict[str, str | int]]:
    result = run_async(
        get_canonical_object().execute(
            GetCanonicalObjectQuery(
                canonical_snapshot_id=UUID(canonical_snapshot_id),
                object_id=UUID(parent_object_id),
                include_members=True,
            )
        )
    )
    return [
        {
            "member_id": str(member.id),
            "parent_object_id": str(member.parent_object_id),
            "child_object_id": str(member.child_object_id),
            "position": member.position,
        }
        for member in result.members
    ]


def _build_member_graph(
    canonical_snapshot_id: UUID,
    objects: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    child_to_parents: dict[str, set[str]] = defaultdict(set)
    for object_id, obj in objects.items():
        if not obj["is_group"]:
            continue
        try:
            members = _cached_object_members(str(canonical_snapshot_id), object_id)
        except Exception:
            members = []
        by_parent[object_id] = sorted(members, key=lambda item: item["position"])
        for member in members:
            child_to_parents[str(member["child_object_id"])].add(object_id)
    return {"by_parent": by_parent, "child_to_parents": child_to_parents}


def _index_rows_by_entity(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        indexed[(row["canonical_kind"], row["canonical_id"])].append(row)
    return indexed


def _build_rule_indexes(scope: dict[str, Any]) -> dict[str, Any]:
    operand_to_rule: dict[str, str] = {}
    target_to_rules: dict[tuple[str, str], set[str]] = defaultdict(set)
    for rule in scope["rules"]:
        for operand in rule["operands"]:
            operand_to_rule[operand["id"]] = rule["id"]
            if operand["target_zone_id"]:
                target_to_rules[("zone", operand["target_zone_id"])].add(rule["id"])
            if operand["target_object_id"]:
                target_to_rules[("object", operand["target_object_id"])].add(rule["id"])
    return {
        "operand_to_rule": operand_to_rule,
        "target_to_rules": target_to_rules,
    }


def _rule_direct_ranges(
    rule_id: str,
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[tuple[int, int]]:
    return sorted(
        {
            (row["source_line_start"], row["source_line_end"])
            for row in rows_by_entity.get(("rule", rule_id), [])
        }
    )


def _index_issues_by_rule(
    rules: list[dict[str, Any]],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    issues: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        ranges = _rule_direct_ranges(rule["id"], rows_by_entity)
        result[rule["id"]] = [
            issue
            for issue in issues
            if any(
                ranges_overlap(
                    start, end, issue["source_line_start"], issue["source_line_end"]
                )
                for start, end in ranges
            )
        ]
    return result


def _ancestor_object_ids(
    object_id: str,
    child_to_parents: dict[str, set[str]],
) -> set[str]:
    collected = {object_id}
    pending = [object_id]
    while pending:
        child_id = pending.pop()
        for parent_id in child_to_parents.get(child_id, set()):
            if parent_id in collected:
                continue
            collected.add(parent_id)
            pending.append(parent_id)
    return collected


def _rule_ids_for_deep_link(
    deep_link: TraceDeepLink,
    *,
    scope: dict[str, Any],
    rule_indexes: dict[str, Any],
    member_graph: dict[str, Any],
    issues: list[dict[str, Any]],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
) -> set[str]:
    kind = deep_link.canonical_kind.value
    canonical_id = str(deep_link.canonical_id)
    if kind == "rule":
        return {canonical_id}
    if kind == "rule_operand":
        rule_id = rule_indexes["operand_to_rule"].get(canonical_id)
        return {rule_id} if rule_id else set()
    if kind == "zone":
        return set(rule_indexes["target_to_rules"].get(("zone", canonical_id), set()))
    if kind == "object":
        object_ids = _ancestor_object_ids(
            canonical_id, member_graph["child_to_parents"]
        )
        return set().union(
            *(
                rule_indexes["target_to_rules"].get(("object", object_id), set())
                for object_id in object_ids
            )
        )
    if kind == "object_member":
        parent_ids = {
            parent_id
            for parent_id, members in member_graph["by_parent"].items()
            if any(str(member["member_id"]) == canonical_id for member in members)
        }
        expanded: set[str] = set()
        for parent_id in parent_ids:
            expanded.update(
                _ancestor_object_ids(parent_id, member_graph["child_to_parents"])
            )
        return set().union(
            *(
                rule_indexes["target_to_rules"].get(("object", object_id), set())
                for object_id in expanded
            )
        )
    if kind == "issue":
        issue = next((item for item in issues if item["id"] == canonical_id), None)
        if issue is None:
            return set()
        return {
            rule["id"]
            for rule in scope["rules"]
            if any(
                ranges_overlap(
                    start, end, issue["source_line_start"], issue["source_line_end"]
                )
                for start, end in _rule_direct_ranges(rule["id"], rows_by_entity)
            )
        }
    return set()


def _render_entity_filter_banner(
    deep_link: TraceDeepLink,
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    entity_rule_ids: set[str],
) -> None:
    kind = deep_link.canonical_kind.value
    canonical_id = str(deep_link.canonical_id)
    evidence_count = len(rows_by_entity.get((kind, canonical_id), []))
    with st.container(border=True):
        label = KIND_LABELS.get(kind, kind.replace("_", " ").title())
        st.markdown(f"**Entity filter:** {label} · `{canonical_id}`")
        st.caption(
            f"{evidence_count} direct trace record(s) · "
            f"{len(entity_rule_ids)} affected rule(s)"
        )
        if st.button("Clear entity filter", key="trace_clear_entity_filter"):
            st.query_params.clear()
            st.rerun()


def _rule_display_text(rule: dict[str, Any], issue_count: int) -> str:
    status = " · ⚠ problems" if issue_count else ""
    state = "" if rule["enabled"] else " · disabled"
    return (
        f"{rule['priority']}. {rule['name']} · {rule['action'].upper()}{state}{status}"
    )


def _rule_matches_search(
    rule: dict[str, Any],
    search: str,
    *,
    scope: dict[str, Any],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
) -> bool:
    if not search:
        return True
    if search.isdigit():
        line_number = int(search)
        return any(
            start <= line_number <= end
            for start, end in _rule_direct_ranges(rule["id"], rows_by_entity)
        )
    labels = _resolve_rule_labels(rule, scope)
    haystack = " ".join(
        [
            rule["name"],
            rule["rule_key"],
            rule["action"],
            rule["section"],
            *labels.values(),
        ]
    ).lower()
    return search.lower() in haystack


def _render_rule_filters(
    rules: list[dict[str, Any]],
    *,
    scope: dict[str, Any],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    issues_by_rule: dict[str, list[dict[str, Any]]],
    entity_rule_ids: set[str] | None,
) -> list[dict[str, Any]]:
    search_col, issue_col = st.columns([3, 1])
    with search_col:
        st.text_input(
            "Find a rule or source line",
            key="trace_rule_search",
            placeholder="Rule name, object, zone, or line number",
        )
    with issue_col:
        st.checkbox("Only with problems", key="trace_only_issues")

    search = st.session_state["trace_rule_search"].strip()
    only_issues = st.session_state["trace_only_issues"]
    filtered = []
    for rule in rules:
        if entity_rule_ids is not None and rule["id"] not in entity_rule_ids:
            continue
        if only_issues and not issues_by_rule.get(rule["id"]):
            continue
        if not _rule_matches_search(
            rule,
            search,
            scope=scope,
            rows_by_entity=rows_by_entity,
        ):
            continue
        filtered.append(rule)
    return filtered


def _preferred_rule_id(
    deep_link: TraceDeepLink | None,
    entity_rule_ids: set[str] | None,
) -> str | None:
    if deep_link and deep_link.canonical_kind.value == "rule":
        return str(deep_link.canonical_id)
    if entity_rule_ids and len(entity_rule_ids) == 1:
        return next(iter(entity_rule_ids))
    return None


def _render_rule_selector(
    rules: list[dict[str, Any]],
    *,
    issues_by_rule: dict[str, list[dict[str, Any]]],
    preferred_rule_id: str | None,
) -> dict[str, Any] | None:
    options = {rule["id"]: rule for rule in rules}
    option_ids = list(options)
    current = st.session_state.get("trace_selected_rule_id")
    if preferred_rule_id in options:
        current = preferred_rule_id
    if current not in options:
        current = option_ids[0]
    st.session_state["trace_selected_rule_id"] = current
    selected_id = st.selectbox(
        "Canonical rule",
        options=option_ids,
        key="trace_selected_rule_id",
        format_func=lambda rule_id: _rule_display_text(
            options[rule_id], len(issues_by_rule.get(rule_id, []))
        ),
    )
    st.caption(f"Showing {len(rules)} rule(s)")
    return options.get(selected_id)


def _resolve_rule_labels(
    rule: dict[str, Any],
    scope: dict[str, Any],
) -> dict[str, str]:
    labels = {
        "src_zone": "Not resolved",
        "dst_zone": "Not resolved",
        "src_object": "Any",
        "dst_object": "Any",
        "service": "Any",
        "protocol": "Any",
    }
    for operand in rule["operands"]:
        role = operand["role"]
        if operand["target_zone_id"]:
            zone = scope["zones"].get(operand["target_zone_id"])
            labels[role] = zone["name"] if zone else "Unknown zone"
        if operand["target_object_id"]:
            obj = scope["objects"].get(operand["target_object_id"])
            labels[role] = _object_heading(obj) if obj else "Unknown object"
            if role == "service" and obj:
                protocol = str(obj["protocol"]).lower() if obj.get("protocol") else None
                labels["protocol"] = protocol.upper() if protocol else "Any"
                if protocol and obj["object_key"].startswith("service:ip-proto:"):
                    labels["service"] = _protocol_only_service_label(protocol)
    return labels


def _object_heading(obj: dict[str, Any]) -> str:
    kind = obj["object_kind"]
    if kind == "any_addr":
        return "Any address"
    if kind == "any_service":
        return "Any service"
    return obj["name"]


def _any_object_explanation(obj: dict[str, Any], role: str) -> str | None:
    if obj["object_kind"] == "any_addr":
        side = "source" if role == "src_object" else "destination"
        return (
            f"Matches every {side} IP address. It comes directly from the `any` "
            "keyword in the source rule above, so no separate object definition exists."
        )
    if obj["object_kind"] == "any_service":
        return (
            "Matches any protocol or service. It comes directly from the source rule, "
            "so no separate service definition exists."
        )
    return None


def _protocol_only_explanation(obj: dict[str, Any]) -> tuple[str, str] | None:
    """Explain implicit protocol-only services (`service:ip-proto:*`)."""
    if not obj["object_key"].startswith("service:ip-proto:"):
        return None
    protocol = str(obj["protocol"]).lower() if obj.get("protocol") else None
    if not protocol:
        return None
    display = protocol.upper()
    if protocol in {"icmp", "icmp6"}:
        meaning = f"Matches all {display} message types."
    elif protocol in {"tcp", "udp"}:
        meaning = f"Matches all {display} ports."
    elif protocol == "ip":
        meaning = "Matches any IP protocol."
    else:
        meaning = f"Matches IP protocol {display}."
    return display, meaning + " It is taken directly from the source rule above."


def _protocol_only_service_label(protocol: str) -> str:
    normalized = protocol.lower()
    if normalized in {"icmp", "icmp6"}:
        return f"All {normalized.upper()} types"
    if normalized in {"tcp", "udp"}:
        return f"All {normalized.upper()} ports"
    if normalized == "ip":
        return "Any IP protocol"
    return normalized.upper()


def _render_rule_inspector(
    rule: dict[str, Any],
    *,
    scope: dict[str, Any],
    rows: list[dict[str, Any]],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    issues: list[dict[str, Any]],
    raw_text: str,
    member_graph: dict[str, Any],
    source_snapshot_id: str,
    canonical_snapshot_id: str,
) -> None:
    labels = _resolve_rule_labels(rule, scope)
    with st.container(border=True):
        title_col, state_col = st.columns([4, 1])
        with title_col:
            st.subheader(rule["name"])
            st.caption(
                f"Priority {rule['priority']}"
                + (f" · ACL {rule['section']}" if rule["section"] else "")
            )
        with state_col:
            st.markdown(f"**{rule['action'].upper()}**")
            st.caption("Enabled" if rule["enabled"] else "Disabled")

        src_col, arrow_col, dst_col, service_col = st.columns([3, 1, 3, 3])
        with src_col:
            st.caption("SOURCE")
            st.markdown(f"**{labels['src_object']}**")
            st.caption(labels["src_zone"])
        with arrow_col:
            st.markdown("### →")
        with dst_col:
            st.caption("DESTINATION")
            st.markdown(f"**{labels['dst_object']}**")
            st.caption(labels["dst_zone"])
        with service_col:
            st.caption("PROTOCOL")
            st.markdown(f"**{labels['protocol']}**")
            st.caption("SERVICE")
            st.markdown(f"**{labels['service']}**")

    st.markdown("### What this rule was built from")
    _render_direct_rule_source(rule, rows_by_entity, raw_text)
    _render_operand_dependencies(
        rule,
        scope=scope,
        rows_by_entity=rows_by_entity,
        raw_text=raw_text,
        member_graph=member_graph,
    )
    _render_zone_derivation(rule, scope, rows_by_entity, raw_text)
    _render_rule_issues(issues, raw_text)
    _render_technical_details(
        rule,
        scope=scope,
        rows=rows,
        issues=issues,
        member_graph=member_graph,
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=canonical_snapshot_id,
    )


def _render_direct_rule_source(
    rule: dict[str, Any],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    raw_text: str,
) -> None:
    st.markdown("#### 1. Source rule")
    direct_rows = rows_by_entity.get(("rule", rule["id"]), [])
    ranges = sorted(
        {(row["source_line_start"], row["source_line_end"]) for row in direct_rows}
    )
    if not ranges:
        st.warning("No direct source line is linked to this rule.")
        return
    for line_start, line_end in ranges:
        _render_source_block(raw_text, line_start, line_end)


def _render_source_block(raw_text: str, line_start: int, line_end: int) -> None:
    excerpt = source_excerpt(
        raw_text,
        line_start=line_start,
        line_end=line_end,
    )
    if not excerpt:
        st.caption(f"Source lines {line_start}–{line_end} are unavailable.")
        return
    rendered = "\n".join(f"{item['line']:>5}  {item['text']}" for item in excerpt)
    st.code(rendered, language="text")


def _render_operand_dependencies(
    rule: dict[str, Any],
    *,
    scope: dict[str, Any],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    raw_text: str,
    member_graph: dict[str, Any],
) -> None:
    st.markdown("#### 2. Source, destination, and service")
    rule_ranges = _rule_direct_ranges(rule["id"], rows_by_entity)
    role_order = {"src_object": 0, "dst_object": 1, "service": 2}
    operands = sorted(
        (
            operand
            for operand in rule["operands"]
            if operand["role"] in OBJECT_ROLES and operand["target_object_id"]
        ),
        key=lambda operand: (
            role_order.get(operand["role"], 99),
            operand["position"],
        ),
    )
    if not operands:
        st.caption("This rule has no object or service dependencies.")
        return

    for operand in operands:
        object_id = operand["target_object_id"]
        obj = scope["objects"].get(object_id)
        role_label = ROLE_LABELS.get(operand["role"], operand["role"])
        if obj is None:
            st.warning(f"{role_label}: linked object is unavailable.")
            continue
        protocol_only = _protocol_only_explanation(obj)
        if protocol_only:
            protocol, explanation = protocol_only
            with st.container(border=True):
                st.markdown(f"**{role_label}: {protocol} protocol**")
                st.caption(explanation)
            continue
        explanation = _any_object_explanation(obj, operand["role"])  # type: ignore
        if explanation:
            with st.container(border=True):
                st.markdown(f"**{role_label}: {_object_heading(obj)}**")
                st.caption(explanation)
            continue
        label = f"{role_label}: {obj['name']} — {object_value(obj)}"
        if obj["is_group"]:
            with st.expander(label, expanded=True):
                tree_lines, related_entities = _object_tree_lines(
                    object_id,
                    objects=scope["objects"],
                    member_graph=member_graph,
                )
                st.markdown("\n".join(tree_lines))
                _render_dependency_source_context(
                    related_entities,
                    rows_by_entity=rows_by_entity,
                    raw_text=raw_text,
                    rule_ranges=rule_ranges,
                )
        else:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                _render_dependency_source_context(
                    {("object", object_id)},
                    rows_by_entity=rows_by_entity,
                    raw_text=raw_text,
                    rule_ranges=rule_ranges,
                )


def _object_tree_lines(
    root_id: str,
    *,
    objects: dict[str, dict[str, Any]],
    member_graph: dict[str, Any],
) -> tuple[list[str], set[tuple[str, str]]]:
    lines: list[str] = []
    entities: set[tuple[str, str]] = {("object", root_id)}
    expanded: set[str] = set()

    def walk(object_id: str, depth: int, path: frozenset[str]) -> None:
        obj = objects.get(object_id)
        if obj is None:
            lines.append(f"{'  ' * depth}- Unknown object `{compact_uuid(object_id)}`")
            return
        suffix = f" — {object_value(obj)}"
        if object_id in path:
            lines.append(f"{'  ' * depth}- **{obj['name']}**{suffix} · cycle")
            return
        reused = object_id in expanded
        lines.append(
            f"{'  ' * depth}- **{obj['name']}**{suffix}"
            + (" · reused" if reused else "")
        )
        if reused or not obj["is_group"]:
            return
        expanded.add(object_id)
        for member in member_graph["by_parent"].get(object_id, []):
            member_id = str(member["member_id"])
            child_id = str(member["child_object_id"])
            entities.add(("object_member", member_id))
            entities.add(("object", child_id))
            walk(child_id, depth + 1, path | {object_id})

    walk(root_id, 0, frozenset())
    return lines, entities


def _render_dependency_source_context(
    entities: set[tuple[str, str]],
    *,
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    raw_text: str,
    rule_ranges: list[tuple[int, int]],
) -> None:
    ranges, used_inline = _dependency_source_context(
        entities,
        rows_by_entity=rows_by_entity,
        rule_ranges=rule_ranges,
    )
    if not ranges:
        if used_inline:
            st.caption("Taken directly from the source rule above.")
            return
        st.caption("No source definition context is stored for this dependency.")
        return
    with st.popover(f"Source context · {len(ranges)} line(s)"):
        st.caption(
            "These are the source definitions used by the inspected rule. "
            "For some group members, the stored location points to the group header."
        )
        for line_start, line_end in ranges:
            _render_source_block(raw_text, line_start, line_end)


def _dependency_source_context(
    entities: set[tuple[str, str]],
    *,
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    rule_ranges: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], bool]:
    """Return definition ranges and whether the dependency is inline in this rule."""
    definition_roles = {"header", "member_ref"}
    entity_rows = [row for entity in entities for row in rows_by_entity.get(entity, [])]
    ranges = sorted(
        {
            (row["source_line_start"], row["source_line_end"])
            for row in entity_rows
            if row["canonical_role"] in definition_roles
        }
    )
    if not ranges:
        used_inline = any(
            ranges_overlap(
                rule_start,
                rule_end,
                row["source_line_start"],
                row["source_line_end"],
            )
            for row in entity_rows
            for rule_start, rule_end in rule_ranges
        )
        return [], used_inline
    return ranges, False


def _render_zone_derivation(
    rule: dict[str, Any],
    scope: dict[str, Any],
    rows_by_entity: dict[tuple[str, str], list[dict[str, Any]]],
    raw_text: str,
) -> None:
    st.markdown("#### 3. Zones")
    zone_operands = [
        operand
        for operand in rule["operands"]
        if operand["role"] in ZONE_ROLES and operand["target_zone_id"]
    ]
    if not zone_operands:
        st.caption("Source and destination zones could not be resolved for this rule.")
        return
    for operand in zone_operands:
        zone_id = operand["target_zone_id"]
        zone = scope["zones"].get(zone_id)
        label = ROLE_LABELS.get(operand["role"], operand["role"])
        st.markdown(f"- **{label}:** {zone['name'] if zone else 'Unknown zone'}")
        entity_rows = rows_by_entity.get(("rule_operand", operand["id"]), [])
        entity_rows += rows_by_entity.get(("zone", zone_id), [])
        ranges = sorted(
            {(row["source_line_start"], row["source_line_end"]) for row in entity_rows}
        )
        if ranges:
            st.caption(
                "Source context: "
                + ", ".join(
                    str(start) if start == end else f"{start}–{end}"
                    for start, end in ranges
                )
            )
    if raw_text and zone_operands:
        st.caption("Zone evidence is included in Technical details below.")


def _render_rule_issues(issues: list[dict[str, Any]], raw_text: str) -> None:
    st.markdown("#### 4. Problems")
    if not issues:
        st.success("No normalization problems are linked to this source rule.")
        return
    for issue in issues:
        message = issue["message"]
        if message.startswith("[") and "] " in message:
            message = message.split("] ", maxsplit=1)[1]
        st.warning(message)
        if issue["source_line_start"]:
            _render_source_block(
                raw_text,
                issue["source_line_start"],
                issue["source_line_end"] or issue["source_line_start"],
            )


def _collect_rule_entity_keys(
    rule: dict[str, Any],
    *,
    member_graph: dict[str, Any],
    issues: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = {("rule", rule["id"])}
    pending_objects: list[str] = []
    seen_objects: set[str] = set()
    for operand in rule["operands"]:
        keys.add(("rule_operand", operand["id"]))
        if operand["target_zone_id"]:
            keys.add(("zone", operand["target_zone_id"]))
        if operand["target_object_id"]:
            pending_objects.append(operand["target_object_id"])
    while pending_objects:
        object_id = pending_objects.pop()
        if object_id in seen_objects:
            continue
        seen_objects.add(object_id)
        keys.add(("object", object_id))
        for member in member_graph["by_parent"].get(object_id, []):
            keys.add(("object_member", str(member["member_id"])))
            pending_objects.append(str(member["child_object_id"]))
    for issue in issues:
        keys.add(("issue", issue["id"]))
    return keys


def _entity_display(
    row: dict[str, Any],
    *,
    rule: dict[str, Any],
    scope: dict[str, Any],
    issues: list[dict[str, Any]],
) -> str:
    kind = row["canonical_kind"]
    canonical_id = row["canonical_id"]
    if kind == "rule":
        return rule["name"]
    if kind == "object":
        obj = scope["objects"].get(canonical_id)
        return obj["name"] if obj else f"Object {compact_uuid(canonical_id)}"
    if kind == "zone":
        zone = scope["zones"].get(canonical_id)
        return zone["name"] if zone else f"Zone {compact_uuid(canonical_id)}"
    if kind == "rule_operand":
        operand = next(
            (item for item in rule["operands"] if item["id"] == canonical_id),
            None,
        )
        return (
            ROLE_LABELS.get(operand["role"], operand["role"])
            if operand
            else "Rule field"
        )
    if kind == "issue":
        issue = next((item for item in issues if item["id"] == canonical_id), None)
        return issue["issue_code"].replace("_", " ").title() if issue else "Problem"
    if kind == "object_member":
        return "Group membership"
    return f"{KIND_LABELS.get(kind, kind)} {compact_uuid(canonical_id)}"


def _render_technical_details(
    rule: dict[str, Any],
    *,
    scope: dict[str, Any],
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    member_graph: dict[str, Any],
    source_snapshot_id: str,
    canonical_snapshot_id: str,
) -> None:
    entity_keys = _collect_rule_entity_keys(
        rule,
        member_graph=member_graph,
        issues=issues,
    )
    related_rows = [
        row
        for row in rows
        if (row["canonical_kind"], row["canonical_id"]) in entity_keys
    ]
    with st.expander("Technical details"):
        st.caption(
            "Internal IDs and producer metadata are kept here for diagnostics. "
            "Click a Canonical ID to open the entity in Canonical rules."
        )
        if not related_rows:
            st.caption("No technical trace rows are available.")
            return
        table_rows = []
        for row in related_rows:
            table_rows.append(
                {
                    "kind": KIND_LABELS.get(
                        row["canonical_kind"], row["canonical_kind"]
                    ),
                    "entity": _entity_display(
                        row,
                        rule=rule,
                        scope=scope,
                        issues=issues,
                    ),
                    "role": ROLE_LABELS.get(
                        row["canonical_role"], row["canonical_role"] or "—"
                    ),
                    "canonical_link": build_canonical_url(
                        source_snapshot_id=source_snapshot_id,
                        canonical_snapshot_id=canonical_snapshot_id,
                        canonical_kind=row["canonical_kind"],
                        canonical_id=row["canonical_id"],
                        context_rule_id=rule["id"],
                    ),
                    "source_lines": (
                        str(row["source_line_start"])
                        if row["source_line_start"] == row["source_line_end"]
                        else f"{row['source_line_start']}–{row['source_line_end']}"
                    ),
                    "normalizer": (
                        f"{row['normalizer_code']}@{row['normalizer_version']}"
                    ),
                    "note": row["note"] or "—",
                }
            )
        st.dataframe(
            pd.DataFrame(table_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "kind": st.column_config.TextColumn("Type", width="small"),
                "entity": st.column_config.TextColumn("Entity", width="medium"),
                "role": st.column_config.TextColumn("Meaning", width="medium"),
                "canonical_link": st.column_config.LinkColumn(
                    "Canonical ID",
                    width="large",
                    display_text=r".*canonical_id=([^&]+).*",
                ),
                "source_lines": st.column_config.TextColumn(
                    "Source lines", width="small"
                ),
                "normalizer": st.column_config.TextColumn("Normalizer", width="small"),
                "note": st.column_config.TextColumn("Note", width="large"),
            },
            column_order=[
                "kind",
                "entity",
                "role",
                "canonical_link",
                "source_lines",
                "normalizer",
                "note",
            ],
        )
