from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import pandas as pd
import streamlit as st

from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceQuery,
)
from app.modules.canonical.ports.rule_repository import CanonicalRuleFilters
from app.modules.imports.application.use_cases.get_source_snapshots import (
    GetSourceSnapshotsQuery,
)
from app.modules.trace.application.dto import GetTraceForCanonicalSnapshotQuery
from app.modules.trace.domain.enums import TraceCanonicalKind
from streamlit_app.services.use_cases import (
    get_canonical_object,
    get_canonical_rule_scope,
    get_latest_canonical_snapshot_for_source,
    get_source_snapshots,
    get_trace_for_canonical_snapshot,
    run_async,
)
from streamlit_app.session.context import context_as_dict, get_context

TRACE_FETCH_LIMIT = 10000
SNAPSHOT_OPTIONS_LIMIT = 300
FRAGMENT_PREVIEW_LIMIT = 90
KIND_OPTIONS = ["Any"] + [kind.value for kind in TraceCanonicalKind]


def render() -> None:
    st.title("Trace")
    st.caption("Understand lineage from raw source lines to canonical entities.")
    context = get_context()
    _ensure_page_state()

    snapshots = _load_snapshots()
    if not snapshots:
        st.info("No mapped snapshots found yet. Upload and map a config first.")
        return

    selected_source_snapshot_id = _render_source_snapshot_selector(snapshots)
    _sync_existing_canonical_for_selected_source(selected_source_snapshot_id)

    if context.canonical_snapshot_id is None:
        st.info("No canonical snapshot for selected source yet. Map it on Upload page.")
        with st.expander("Session context"):
            st.json(context_as_dict())
        return

    all_rows = _load_trace_rows(context.canonical_snapshot_id)
    if not all_rows:
        st.warning(
            "Trace records are empty for this canonical snapshot. Try remapping or choose another source snapshot."
        )
        with st.expander("Session context"):
            st.json(context_as_dict())
        return

    canonical_scope = _load_canonical_scope(context.canonical_snapshot_id)
    canonical_context = _build_canonical_context_from_scope(canonical_scope)
    enriched_rows = _enrich_rows_with_context(all_rows, canonical_context)
    filtered_rows = _render_and_apply_filters(enriched_rows)
    if not filtered_rows:
        st.info("No trace rows match current filters.")
        return

    primary_tab, reverse_tab = st.tabs(
        ["Line -> Canonical (Primary)", "Canonical -> Lines"]
    )
    with primary_tab:
        _render_primary_flow(filtered_rows, canonical_scope)
    with reverse_tab:
        _render_reverse_flow(enriched_rows, canonical_scope, selected_source_snapshot_id)

    with st.expander("Session context"):
        st.json(context_as_dict())


def _ensure_page_state() -> None:
    st.session_state.setdefault("trace_selected_source_snapshot", None)
    st.session_state.setdefault("trace_filter_kind", "Any")
    st.session_state.setdefault("trace_filter_search", "")
    st.session_state.setdefault("trace_selected_group_key", None)
    st.session_state.setdefault("trace_primary_target_key", None)
    st.session_state.setdefault("trace_reverse_selected_rule_id", None)


def _load_snapshots() -> list:
    with st.spinner("Loading source snapshots..."):
        result = run_async(
            get_source_snapshots().execute(
                GetSourceSnapshotsQuery(limit=SNAPSHOT_OPTIONS_LIMIT)
            )
        )
    mapped_snapshots = []
    for snapshot in result.snapshots:
        latest = run_async(
            get_latest_canonical_snapshot_for_source().execute(
                GetLatestCanonicalSnapshotForSourceQuery(source_snapshot_id=snapshot.id)
            )
        )
        if latest.snapshot is not None:
            mapped_snapshots.append(snapshot)
    return mapped_snapshots


def _format_source_snapshot_label(snapshot) -> str:
    source_name = snapshot.source_name or "unknown-source"
    file_name = snapshot.file_name or "n/a"
    created_at = snapshot.created_at.strftime("%Y-%m-%d %H:%M:%S")
    short_id = str(snapshot.id).split("-")[0]
    return f"{source_name} | {file_name} | {created_at} | {short_id}"


def _render_source_snapshot_selector(snapshots: list) -> UUID:
    options_by_id = {str(s.id): s for s in snapshots}
    option_ids = list(options_by_id.keys())
    context = get_context()
    preferred_snapshot_id = None
    if context.snapshot_id:
        preferred_snapshot_id = str(context.snapshot_id)
    elif st.session_state["trace_selected_source_snapshot"]:
        preferred_snapshot_id = st.session_state["trace_selected_source_snapshot"]

    default_index = 0
    if preferred_snapshot_id in option_ids:
        default_index = option_ids.index(preferred_snapshot_id)

    selected_option = st.selectbox(
        "Source snapshot",
        options=option_ids,
        index=default_index,
        format_func=lambda option_id: _format_source_snapshot_label(
            options_by_id[option_id]
        ),
    )
    st.session_state["trace_selected_source_snapshot"] = selected_option
    return options_by_id[selected_option].id


def _sync_existing_canonical_for_selected_source(source_snapshot_id: UUID) -> None:
    context = get_context()
    latest = run_async(
        get_latest_canonical_snapshot_for_source().execute(
            GetLatestCanonicalSnapshotForSourceQuery(
                source_snapshot_id=source_snapshot_id
            )
        )
    )
    if latest.snapshot is None:
        context.canonical_snapshot_id = None
        return
    context.canonical_snapshot_id = latest.snapshot.id


def _render_and_apply_filters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with st.popover("Filters"):
        st.selectbox(
            "Canonical kind",
            options=KIND_OPTIONS,
            key="trace_filter_kind",
        )
        st.text_input(
            "Search in source fragment / canonical label / ID / role",
            key="trace_filter_search",
        )
    kind_filter = st.session_state["trace_filter_kind"]
    search_filter = st.session_state["trace_filter_search"].strip().lower()

    filtered = rows
    if kind_filter != "Any":
        filtered = [row for row in filtered if row["canonical_kind"] == kind_filter]

    if search_filter:
        filtered = [
            row
            for row in filtered
            if search_filter in (row["source_fragment"] or "").lower()
            or search_filter in row["canonical_id"]
            or search_filter in row["canonical_display"].lower()
            or search_filter in (row["canonical_role"] or "").lower()
            or search_filter in row["relation_hint"].lower()
        ]

    return filtered


def _render_primary_flow(
    rows: list[dict[str, Any]],
    canonical_scope: dict[str, Any],
) -> None:
    st.markdown("### Raw lines to canonical entity")
    st.caption(f"Trace rows: {len(rows)}")
    grouped_rows = _build_primary_groups(rows, canonical_scope)
    group_rows = _primary_group_rows_for_table(grouped_rows)
    lines_col, details_col = st.columns([1, 2])
    with lines_col:
        st.markdown("#### Source groups")
        event = st.dataframe(
            pd.DataFrame(group_rows),
            key="trace_primary_lines_table",
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "group_key": None,
                "group_order": None,
                "group_label": st.column_config.TextColumn("Group", width="large"),
                "lines_count": st.column_config.NumberColumn(
                    "Lines", width="small"
                ),
                "targets_count": st.column_config.NumberColumn(
                    "Targets", width="small"
                ),
                "line_span": st.column_config.TextColumn("Line span", width="small"),
                "sample": st.column_config.TextColumn("Sample", width="large"),
            },
            column_order=["group_label", "lines_count", "targets_count", "line_span", "sample"],
        )

    selected_group_key = _resolve_selected_group_key(event, group_rows)
    if selected_group_key is None:
        st.info("Select a source group to inspect canonical lineage.")
        return

    selected_group = grouped_rows[selected_group_key]
    with details_col:
        st.markdown("#### Group details")
        st.write(f"Group: `{selected_group['group_label']}`")
        st.write(f"Line span: `{selected_group['line_span']}`")
        st.write(
            f"Contains `{selected_group['lines_count']}` source lines and `{selected_group['targets_count']}` canonical targets"
        )

        st.markdown("#### Source lines in group")
        _render_group_source_lines_table(selected_group["rows"])

        st.markdown("#### Canonical targets in group")
        target_rows = _target_rows_for_group(selected_group["rows"])
        target_event = st.dataframe(
            pd.DataFrame(target_rows),
            key="trace_primary_targets_table",
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "target_key": None,
                "canonical_kind": st.column_config.TextColumn("Kind", width="small"),
                "canonical_display": st.column_config.TextColumn("Entity", width="large"),
                "canonical_role": st.column_config.TextColumn("Role", width="small"),
                "canonical_id": st.column_config.TextColumn("Canonical ID", width="medium"),
            },
            column_order=[
                "canonical_kind",
                "canonical_display",
                "canonical_role",
                "canonical_id",
            ],
        )
        selected_target_key = _resolve_primary_target_key(target_event, target_rows)
        selected_row = _row_for_target_key(selected_group["rows"], selected_target_key)
        if selected_row:
            st.markdown("#### Selected canonical target")
            st.write(f"Entity: `{selected_row['canonical_display']}`")
            st.write(f"Role: `{selected_row['canonical_role'] or '—'}`")
            st.write(
                f"Lineage: `raw {selected_row['source_line_start']}-{selected_row['source_line_end']}` -> "
                f"`{selected_row['normalizer_code']}@{selected_row['normalizer_version']}` -> "
                f"`{selected_row['canonical_display']}`"
            )
            if selected_row["note"]:
                st.caption(f"Note: {selected_row['note']}")
        st.markdown("#### All related entities for this group")
        _render_related_entities_table(selected_group["rows"])


def _render_reverse_flow(
    rows: list[dict[str, Any]],
    canonical_scope: dict[str, Any],
    selected_source_snapshot_id: UUID,
) -> None:
    st.markdown("### Rule composition <- Source lines")
    reverse_nodes = _build_reverse_rule_nodes(
        rows=rows,
        canonical_scope=canonical_scope,
        selected_source_snapshot_id=selected_source_snapshot_id,
    )
    if not reverse_nodes:
        st.info("No canonical rules available for reverse trace view.")
        return
    st.caption(f"Rules: {len(reverse_nodes)}")

    rules_col, tree_col = st.columns([1, 2])
    with rules_col:
        st.markdown("#### Canonical rules")
        rule_rows = _rule_list_rows(reverse_nodes)
        event = st.dataframe(
            pd.DataFrame(rule_rows),
            key="trace_reverse_rules_table",
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "rule_id": None,
                "rule_short": st.column_config.TextColumn("Rule", width="small"),
                "name": st.column_config.TextColumn("Name", width="large"),
                "action": st.column_config.TextColumn("Action", width="small"),
                "zones": st.column_config.TextColumn("Zones", width="medium"),
                "objects": st.column_config.TextColumn("Objects", width="medium"),
                "linked_lines": st.column_config.NumberColumn("Lines", width="small"),
            },
            column_order=["rule_short", "name", "action", "zones", "objects", "linked_lines"],
        )
        selected_rule_id = _resolve_selected_rule_id(event, rule_rows)

    selected_node = next(
        (node for node in reverse_nodes if node["rule_id"] == selected_rule_id), None
    )
    with tree_col:
        if selected_node is None:
            st.info("Select rule on the left to inspect composition tree.")
            return
        _render_rule_tree(selected_node)


def _line_key(line_start: int, line_end: int, source_fragment: str | None) -> str:
    fragment_key = (source_fragment or "").strip().replace("\n", "\\n")
    return f"{line_start}:{line_end}:{fragment_key}"


def _build_primary_groups(
    rows: list[dict[str, Any]],
    canonical_scope: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    indexes = _build_primary_rule_indexes(canonical_scope)
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        rule_ids = _rule_ids_for_row(row, indexes)
        if rule_ids:
            if len(rule_ids) == 1:
                rule_id = rule_ids[0]
                rule_name = indexes["rule_name_by_id"].get(rule_id, _short_uuid(rule_id))
                group_key = f"rule:{rule_id}"
                group_label = f"rule:{rule_name}"
            else:
                group_key = f"rules:{','.join(rule_ids)}"
                group_label = f"multiple rules ({len(rule_ids)})"
        else:
            line_key = f"{row['source_line_start']}-{row['source_line_end']}"
            group_key = f"line:{line_key}"
            group_label = f"line:{line_key}"

        if group_key not in grouped:
            grouped[group_key] = {
                "group_key": group_key,
                "group_label": group_label,
                "rule_ids": rule_ids,
                "rows": [],
            }
        grouped[group_key]["rows"].append(row)

    for group in grouped.values():
        starts = [row["source_line_start"] for row in group["rows"]]
        ends = [row["source_line_end"] for row in group["rows"]]
        unique_line_keys = {
            _line_key(row["source_line_start"], row["source_line_end"], row["source_fragment"])
            for row in group["rows"]
        }
        group["lines_count"] = len(unique_line_keys)
        group["targets_count"] = len(
            {
                f"{row['canonical_kind']}:{row['canonical_id']}:{row['canonical_role'] or '-'}"
                for row in group["rows"]
            }
        )
        group["line_span"] = f"{min(starts)}-{max(ends)}"
        group["sample"] = _compact_text(
            ", ".join(
                sorted(
                    {
                        (row["source_fragment"] or "—").strip() or "—"
                        for row in group["rows"]
                    }
                )
            ),
            FRAGMENT_PREVIEW_LIMIT,
        )
        group["group_order"] = min(starts)
    return grouped


def _build_primary_rule_indexes(canonical_scope: dict[str, Any]) -> dict[str, Any]:
    rule_name_by_id: dict[str, str] = {}
    operand_to_rule: dict[str, str] = {}
    zone_to_rules: dict[str, set[str]] = defaultdict(set)
    object_to_rules: dict[str, set[str]] = defaultdict(set)
    for rule in canonical_scope["rules"]:
        rule_id = rule["id"]
        rule_name_by_id[rule_id] = rule["name"]
        for operand in rule["operands"]:
            operand_to_rule[operand["id"]] = rule_id
            if operand["target_zone_id"]:
                zone_to_rules[operand["target_zone_id"]].add(rule_id)
            if operand["target_object_id"]:
                object_to_rules[operand["target_object_id"]].add(rule_id)
    return {
        "rule_name_by_id": rule_name_by_id,
        "operand_to_rule": operand_to_rule,
        "zone_to_rules": zone_to_rules,
        "object_to_rules": object_to_rules,
    }


def _rule_ids_for_row(row: dict[str, Any], indexes: dict[str, Any]) -> list[str]:
    kind = row["canonical_kind"]
    canonical_id = row["canonical_id"]
    if kind == "rule":
        return [canonical_id]
    if kind == "rule_operand":
        rule_id = indexes["operand_to_rule"].get(canonical_id)
        return [rule_id] if rule_id else []
    if kind == "zone":
        return sorted(indexes["zone_to_rules"].get(canonical_id, set()))
    if kind in {"object", "object_member"}:
        return sorted(indexes["object_to_rules"].get(canonical_id, set()))
    return []


def _primary_group_rows_for_table(
    grouped_rows: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = [
        {
            "group_key": group["group_key"],
            "group_order": group["group_order"],
            "group_label": group["group_label"],
            "lines_count": group["lines_count"],
            "targets_count": group["targets_count"],
            "line_span": group["line_span"],
            "sample": group["sample"],
        }
        for group in grouped_rows.values()
    ]
    return sorted(rows, key=lambda row: row["group_order"])


def _target_rows_for_group(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = []
    unique_keys = sorted(
        {
            f"{row['canonical_kind']}:{row['canonical_id']}:{row['canonical_role'] or '-'}"
            for row in rows
        }
    )
    for key in unique_keys:
        row = _row_for_target_key(rows, key)
        if row is None:
            continue
        targets.append(
            {
                "target_key": key,
                "canonical_kind": row["canonical_kind"],
                "canonical_display": row["canonical_display"],
                "canonical_role": row["canonical_role"] or "—",
                "canonical_id": row["canonical_id"],
            }
        )
    return targets


def _render_group_source_lines_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.caption("No source lines in this group.")
        return
    unique_lines: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _line_key(
            row["source_line_start"], row["source_line_end"], row["source_fragment"]
        )
        if key not in unique_lines:
            unique_lines[key] = {
                "line_range": f"{row['source_line_start']}-{row['source_line_end']}",
                "source_fragment": _compact_text(
                    row["source_fragment"] or "—", FRAGMENT_PREVIEW_LIMIT
                ),
                "normalizer": f"{row['normalizer_code']}@{row['normalizer_version']}",
            }
    table_rows = sorted(
        unique_lines.values(),
        key=lambda item: int(item["line_range"].split("-")[0]),
    )
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)


def _build_reverse_rule_nodes(
    *,
    rows: list[dict[str, Any]],
    canonical_scope: dict[str, Any],
    selected_source_snapshot_id: UUID,
) -> list[dict[str, Any]]:
    rows_for_snapshot = [
        row for row in rows if row["source_snapshot_id"] == str(selected_source_snapshot_id)
    ]
    rows_by_canonical_id: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows_for_snapshot:
        rows_by_canonical_id[(row["canonical_kind"], row["canonical_id"])].append(row)

    zones_by_id = canonical_scope["zones"]
    objects_by_id = canonical_scope["objects"]
    scope_snapshot_id = canonical_scope["snapshot_id"]
    nodes: list[dict[str, Any]] = []
    for rule in canonical_scope["rules"]:
        labels = _resolve_scope_rule_labels(rule, zones_by_id, objects_by_id)
        all_rows = _collect_rule_related_rows(rule, rows_by_canonical_id)
        unique_line_keys = {
            _line_key(row["source_line_start"], row["source_line_end"], row["source_fragment"])
            for row in all_rows
        }
        operand_nodes: list[dict[str, Any]] = []
        for operand in sorted(rule["operands"], key=lambda item: item["position"]):
            operand_rows = _collect_operand_related_rows(operand, rows_by_canonical_id)
            target_kind, target_id, target_label = _resolve_operand_target(
                operand, zones_by_id, objects_by_id
            )
            member_nodes: list[dict[str, Any]] = []
            if target_kind == "object":
                object_meta = objects_by_id.get(target_id)
                if object_meta and object_meta.get("is_group"):
                    members = _load_object_members(
                        canonical_snapshot_id=scope_snapshot_id,
                        parent_object_id=target_id,
                    )
                    member_nodes = _build_member_nodes(
                        members=members,
                        objects_by_id=objects_by_id,
                        rows_by_canonical_id=rows_by_canonical_id,
                    )
            operand_nodes.append(
                {
                    "operand_id": operand["id"],
                    "role": operand["role"],
                    "position": operand["position"],
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "target_label": target_label,
                    "rows": operand_rows,
                    "meaning": _relation_hint(operand["role"]),
                    "member_nodes": member_nodes,
                }
            )

        nodes.append(
            {
                "rule_id": rule["id"],
                "rule_short": _short_uuid(rule["id"]),
                "name": rule["name"],
                "action": rule["action"],
                "enabled": rule["enabled"],
                "priority": rule["priority"],
                "zones_summary": f"{labels['src_zone']} -> {labels['dst_zone']}",
                "objects_summary": f"{labels['src_object']} -> {labels['dst_object']}",
                "service_summary": labels["service"],
                "all_rows": all_rows,
                "operand_nodes": operand_nodes,
                "linked_lines": len(unique_line_keys),
            }
        )
    return sorted(nodes, key=lambda node: (node["priority"], node["name"]))


def _collect_rule_related_rows(
    rule: dict[str, Any],
    rows_by_canonical_id: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    rule_id = rule["id"]
    for row in rows_by_canonical_id.get(("rule", rule_id), []):
        collected[row["id"]] = row

    for operand in rule["operands"]:
        for row in rows_by_canonical_id.get(("rule_operand", operand["id"]), []):
            collected[row["id"]] = row
        if operand["target_zone_id"]:
            for row in rows_by_canonical_id.get(("zone", operand["target_zone_id"]), []):
                collected[row["id"]] = row
        if operand["target_object_id"]:
            for kind in ("object", "object_member"):
                for row in rows_by_canonical_id.get((kind, operand["target_object_id"]), []):
                    collected[row["id"]] = row

    return sorted(
        collected.values(),
        key=lambda row: (
            row["source_line_start"],
            row["source_line_end"],
            row["canonical_kind"],
        ),
    )


def _collect_operand_related_rows(
    operand: dict[str, Any],
    rows_by_canonical_id: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for row in rows_by_canonical_id.get(("rule_operand", operand["id"]), []):
        collected[row["id"]] = row
    if operand["target_zone_id"]:
        for row in rows_by_canonical_id.get(("zone", operand["target_zone_id"]), []):
            collected[row["id"]] = row
    if operand["target_object_id"]:
        for kind in ("object", "object_member"):
            for row in rows_by_canonical_id.get((kind, operand["target_object_id"]), []):
                collected[row["id"]] = row
    return sorted(
        collected.values(),
        key=lambda row: (
            row["source_line_start"],
            row["source_line_end"],
            row["canonical_kind"],
        ),
    )


def _resolve_operand_target(
    operand: dict[str, Any],
    zones_by_id: dict[str, dict[str, str]],
    objects_by_id: dict[str, dict[str, str]],
) -> tuple[str, str, str]:
    if operand["target_zone_id"]:
        zone = zones_by_id.get(operand["target_zone_id"])
        zone_label = zone["name"] if zone else _short_uuid(operand["target_zone_id"])
        return "zone", operand["target_zone_id"], zone_label
    if operand["target_object_id"]:
        obj = objects_by_id.get(operand["target_object_id"])
        obj_label = obj["display"] if obj else _short_uuid(operand["target_object_id"])
        return "object", operand["target_object_id"], obj_label
    return "none", "—", "No direct target entity"


def _build_member_nodes(
    *,
    members: list[dict[str, Any]],
    objects_by_id: dict[str, dict[str, Any]],
    rows_by_canonical_id: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for member in sorted(members, key=lambda item: item["position"]):
        child_object_id = member["child_object_id"]
        child_meta = objects_by_id.get(child_object_id)
        child_label = (
            child_meta["display"] if child_meta else f"object:{_short_uuid(child_object_id)}"
        )
        collected: dict[str, dict[str, Any]] = {}
        for row in rows_by_canonical_id.get(("object_member", member["member_id"]), []):
            collected[row["id"]] = row
        for row in rows_by_canonical_id.get(("object", child_object_id), []):
            collected[row["id"]] = row
        rows = sorted(
            collected.values(),
            key=lambda row: (
                row["source_line_start"],
                row["source_line_end"],
                row["canonical_kind"],
            ),
        )
        nodes.append(
            {
                "member_id": member["member_id"],
                "child_object_id": child_object_id,
                "child_label": child_label,
                "rows": rows,
            }
        )
    return nodes


def _rule_list_rows(reverse_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": node["rule_id"],
            "rule_short": node["rule_short"],
            "name": _compact_text(node["name"], 48),
            "action": node["action"],
            "zones": _compact_text(node["zones_summary"], 36),
            "objects": _compact_text(node["objects_summary"], 36),
            "linked_lines": node["linked_lines"],
        }
        for node in reverse_nodes
    ]


def _resolve_selected_rule_id(event, rule_rows: list[dict[str, Any]]) -> str | None:
    selected_rule_id = st.session_state.get("trace_reverse_selected_rule_id")
    if event and event.selection and event.selection.rows:
        idx = event.selection.rows[0]
        if 0 <= idx < len(rule_rows):
            selected_rule_id = rule_rows[idx]["rule_id"]
    valid_rule_ids = {row["rule_id"] for row in rule_rows}
    if selected_rule_id not in valid_rule_ids:
        selected_rule_id = rule_rows[0]["rule_id"] if rule_rows else None
    st.session_state["trace_reverse_selected_rule_id"] = selected_rule_id
    return selected_rule_id


def _render_rule_tree(rule_node: dict[str, Any]) -> None:
    st.markdown("#### Rule composition tree")
    st.write(f"Rule: `{rule_node['name']}`")
    st.write(f"Action: `{rule_node['action']}` | Priority: `{rule_node['priority']}`")
    st.write(f"Zones: `{rule_node['zones_summary']}`")
    st.write(f"Objects: `{rule_node['objects_summary']}` | Service: `{rule_node['service_summary']}`")

    if not rule_node["operand_nodes"]:
        st.info("Rule has no operands in canonical scope.")
    for operand_node in rule_node["operand_nodes"]:
        label = (
            f"{operand_node['role']} -> {operand_node['target_kind']}:{operand_node['target_label']} "
            f"({len(operand_node['rows'])} rows)"
        )
        with st.expander(label):
            st.write(f"Target ID: `{operand_node['target_id']}`")
            if operand_node["member_nodes"]:
                st.markdown("**Group members**")
                for member_node in operand_node["member_nodes"]:
                    with st.expander(
                        f"member -> {member_node['child_label']} ({len(member_node['rows'])} rows)"
                    ):
                        st.write(f"Member ID: `{member_node['member_id']}`")
                        st.write(f"Child object ID: `{member_node['child_object_id']}`")
                        _render_source_lines_table(member_node["rows"])
            _render_source_lines_table(operand_node["rows"])

    st.markdown("#### All related entities for this rule")
    _render_related_entities_table(rule_node["all_rows"])

    st.markdown("#### All source lines linked to this rule")
    _render_source_lines_table(rule_node["all_rows"])


def _render_source_lines_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.caption("No trace rows for this node.")
        return
    table_rows = [
        {
            "line_range": f"{row['source_line_start']}-{row['source_line_end']}",
            "source_fragment": _compact_text(row["source_fragment"] or "—", FRAGMENT_PREVIEW_LIMIT),
            "canonical_target": row["canonical_display"],
            "role": row["canonical_role"] or "—",
            "normalizer": f"{row['normalizer_code']}@{row['normalizer_version']}",
            "note": row["note"] or "—",
        }
        for row in rows
    ]
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)


def _render_related_entities_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.caption("No related entities for this rule.")
        return
    entities: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["canonical_kind"],
            row["canonical_id"],
            row["canonical_role"] or "—",
        )
        if key not in entities:
            entities[key] = {
                "kind": row["canonical_kind"],
                "entity": row["canonical_display"],
                "canonical_id": row["canonical_id"],
                "role": row["canonical_role"] or "—",
                "meaning": row["relation_hint"],
                "line_keys": set(),
            }
        entities[key]["line_keys"].add(
            _line_key(row["source_line_start"], row["source_line_end"], row["source_fragment"])
        )

    table_rows = [
        {
            "kind": value["kind"],
            "entity": value["entity"],
            "canonical_id": value["canonical_id"],
            "role": value["role"],
            "lines_count": len(value["line_keys"]),
        }
        for value in entities.values()
    ]
    table_rows.sort(key=lambda item: (item["kind"], item["entity"], item["role"]))
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)


def _resolve_scope_rule_labels(
    rule: dict[str, Any],
    zones_by_id: dict[str, dict[str, str]],
    objects_by_id: dict[str, dict[str, str]],
) -> dict[str, str]:
    labels = {
        "src_zone": "—",
        "dst_zone": "—",
        "src_object": "—",
        "dst_object": "—",
        "service": "ANY",
    }
    for operand in rule["operands"]:
        role = operand["role"]
        if operand["target_zone_id"]:
            zone = zones_by_id.get(operand["target_zone_id"])
            zone_name = zone["name"] if zone else _short_uuid(operand["target_zone_id"])
            if role == "src_zone":
                labels["src_zone"] = zone_name
            elif role == "dst_zone":
                labels["dst_zone"] = zone_name
        if operand["target_object_id"]:
            obj = objects_by_id.get(operand["target_object_id"])
            obj_name = obj["display"] if obj else _short_uuid(operand["target_object_id"])
            if role == "src_object":
                labels["src_object"] = obj_name
            elif role == "dst_object":
                labels["dst_object"] = obj_name
            elif role == "service":
                labels["service"] = obj_name
    return labels


def _short_uuid(value: str) -> str:
    return value.split("-")[0]


def _resolve_selected_group_key(
    event, group_rows: list[dict[str, Any]]
) -> str | None:
    selected_group_key = st.session_state.get("trace_selected_group_key")
    if event and event.selection and event.selection.rows:
        selected_idx = event.selection.rows[0]
        if 0 <= selected_idx < len(group_rows):
            selected_group_key = group_rows[selected_idx]["group_key"]
    if selected_group_key not in {row["group_key"] for row in group_rows}:
        selected_group_key = group_rows[0]["group_key"] if group_rows else None
    st.session_state["trace_selected_group_key"] = selected_group_key
    return selected_group_key


def _resolve_primary_target_key(
    event, target_rows: list[dict[str, Any]]
) -> str | None:
    selected_target_key = st.session_state.get("trace_primary_target_key")
    if event and event.selection and event.selection.rows:
        idx = event.selection.rows[0]
        if 0 <= idx < len(target_rows):
            selected_target_key = target_rows[idx]["target_key"]
    valid_keys = {row["target_key"] for row in target_rows}
    if selected_target_key not in valid_keys:
        selected_target_key = target_rows[0]["target_key"] if target_rows else None
    st.session_state["trace_primary_target_key"] = selected_target_key
    return selected_target_key


def _row_for_target_key(
    rows: list[dict[str, Any]],
    target_key: str | None,
) -> dict[str, Any] | None:
    if target_key is None:
        return None
    kind, canonical_id, canonical_role = target_key.split(":", maxsplit=2)
    role = None if canonical_role == "-" else canonical_role
    for row in rows:
        if (
            row["canonical_kind"] == kind
            and row["canonical_id"] == canonical_id
            and row["canonical_role"] == role
        ):
            return row
    return None


@st.cache_data(ttl=30, show_spinner=False)
def _cached_trace_rows(canonical_snapshot_id: str) -> list[dict[str, Any]]:
    rows = run_async(
        get_trace_for_canonical_snapshot().execute(
            GetTraceForCanonicalSnapshotQuery(
                canonical_snapshot_id=UUID(canonical_snapshot_id),
                limit=TRACE_FETCH_LIMIT,
                offset=0,
            )
        )
    )
    return [_trace_row_to_dict(row) for row in rows]


def _load_trace_rows(canonical_snapshot_id: UUID) -> list[dict[str, Any]]:
    try:
        with st.spinner("Loading trace rows..."):
            return _cached_trace_rows(str(canonical_snapshot_id))
    except Exception as error:
        st.error(f"Failed to load trace rows: {error}")
        with st.expander("Error details"):
            st.exception(error)
        return []


def _trace_row_to_dict(row) -> dict[str, Any]:
    return {
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


def _enrich_rows_with_context(
    rows: list[dict[str, Any]],
    canonical_context: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        canonical_display = _build_canonical_display(row, canonical_context)
        relation_hint = _relation_hint(row["canonical_role"])
        row_copy = dict(row)
        row_copy["canonical_display"] = canonical_display
        row_copy["relation_hint"] = relation_hint
        enriched_rows.append(row_copy)
    return enriched_rows


def _build_canonical_display(
    row: dict[str, Any],
    canonical_context: dict[str, dict[str, str]],
) -> str:
    kind = row["canonical_kind"]
    canonical_id = row["canonical_id"]
    short_id = canonical_id.split("-")[0]
    if kind == "rule":
        rule_name = canonical_context["rules"].get(canonical_id)
        if rule_name:
            return f"rule:{rule_name}"
    if kind in {"object", "object_member", "rule_operand"}:
        object_name = canonical_context["objects"].get(canonical_id)
        if object_name:
            return f"{kind}:{object_name}"
    if kind == "zone":
        zone_name = canonical_context["zones"].get(canonical_id)
        if zone_name:
            return f"zone:{zone_name}"
    return f"{kind}:{short_id}"


def _relation_hint(canonical_role: str | None) -> str:
    role_map = {
        "src_zone": "Maps line to source zone of rule",
        "dst_zone": "Maps line to destination zone of rule",
        "src_object": "Maps line to source object/address",
        "dst_object": "Maps line to destination object/address",
        "service": "Maps line to service/protocol part of rule",
        "header": "Maps line to object definition header",
        "member_ref": "Maps line to object member reference",
        "from_acl_name": "Derived from ACL name",
        "from_access_group_binding": "Derived from access-group binding",
    }
    if canonical_role is None:
        return "Maps line to canonical entity (role is not specified)"
    return role_map.get(canonical_role, f"Maps line with role `{canonical_role}`")


@st.cache_data(ttl=30, show_spinner=False)
def _cached_canonical_scope(canonical_snapshot_id: str) -> dict[str, Any]:
    scope = run_async(
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
        "snapshot_id": canonical_snapshot_id,
        "rules": [
            {
                "id": str(rule.id),
                "name": rule.name,
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
            for rule in scope.rules
        ],
        "objects": {
            str(obj.id): {
                "name": obj.name,
                "display": obj.name or obj.object_key or obj.cidr or obj.fqdn or str(obj.id),
                "object_kind": str(obj.object_kind),
                "is_group": str(obj.object_kind) in {"addr_group", "service_group"},
            }
            for obj in scope.objects
        },
        "zones": {
            str(zone.id): {
                "name": zone.name,
                "zone_key": zone.zone_key,
            }
            for zone in scope.zones
        },
    }


def _load_canonical_scope(canonical_snapshot_id: UUID) -> dict[str, Any]:
    try:
        with st.spinner("Loading canonical scope for reverse tree..."):
            return _cached_canonical_scope(str(canonical_snapshot_id))
    except Exception:
        return {
            "snapshot_id": str(canonical_snapshot_id),
            "rules": [],
            "objects": {},
            "zones": {},
        }


def _build_canonical_context_from_scope(
    canonical_scope: dict[str, Any]
) -> dict[str, dict[str, str]]:
    return {
        "rules": {rule["id"]: rule["name"] for rule in canonical_scope["rules"]},
        "objects": {
            object_id: obj_meta["display"]
            for object_id, obj_meta in canonical_scope["objects"].items()
        },
        "zones": {
            zone_id: zone_meta["name"]
            for zone_id, zone_meta in canonical_scope["zones"].items()
        },
    }


@st.cache_data(ttl=30, show_spinner=False)
def _cached_object_members(
    canonical_snapshot_id: str,
    parent_object_id: str,
) -> list[dict[str, Any]]:
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


def _load_object_members(
    *,
    canonical_snapshot_id: str,
    parent_object_id: str,
) -> list[dict[str, Any]]:
    try:
        return _cached_object_members(canonical_snapshot_id, parent_object_id)
    except Exception:
        return []


def _compact_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit - 1]}…"
