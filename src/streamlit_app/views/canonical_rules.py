import math
from uuid import UUID

import pandas as pd
import streamlit as st

from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceQuery,
)
from app.modules.canonical.ports.rule_repository import CanonicalRuleFilters
from app.modules.imports.application.use_cases.get_source_snapshots import (
    GetSourceSnapshotsQuery,
)
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanCommand,
)
from streamlit_app.services.use_cases import (
    get_canonical_rule_scope,
    get_latest_canonical_snapshot_for_source,
    get_map_canonical_to_sdwan,
    get_sdwan_targets,
    get_source_snapshots,
    run_async,
)
from streamlit_app.session.context import context_as_dict, get_context

PAGE_SIZE = 30
SNAPSHOT_OPTIONS_LIMIT = 300
ACTION_OPTIONS = ["Any", "allow", "deny", "permit", "drop", "reject"]


def render() -> None:
    st.title("Canonical rules")
    context = get_context()
    _ensure_page_state()

    snapshots = _load_snapshots()
    if not snapshots:
        st.info("No mapped snapshots found yet. Upload and map a config first.")
        return

    selected_source_snapshot_id = _render_source_snapshot_selector(snapshots)
    _sync_existing_canonical_for_selected_source(selected_source_snapshot_id)
    _render_trace_link_action(selected_source_snapshot_id)

    if context.canonical_snapshot_id is None:
        st.info(
            "No canonical snapshot selected yet. Map snapshot on Upload page first."
        )
        with st.expander("Session context"):
            st.json(context_as_dict())
        return

    zone_options = _load_zone_options(context.canonical_snapshot_id)
    _render_filters_panel(zone_options)
    _render_rules_table(context)

    with st.expander("Session context"):
        st.json(context_as_dict())


def _render_trace_link_action(selected_source_snapshot_id: UUID) -> None:
    if st.button("Open Trace", key="canonical_open_trace"):
        st.session_state["trace_selected_source_snapshot"] = str(
            selected_source_snapshot_id
        )
        try:
            st.switch_page("trace-rules")
        except Exception:
            st.info("Open 'Trace' page from sidebar.")


def _ensure_page_state() -> None:
    st.session_state.setdefault("canonical_page", 1)
    st.session_state.setdefault("canonical_selected_rule_ids", set())
    st.session_state.setdefault("canonical_filter_name_contains", "")
    st.session_state.setdefault("canonical_filter_enabled", "Any")
    st.session_state.setdefault("canonical_filter_action", "Any")
    st.session_state.setdefault("canonical_filter_section", "")
    st.session_state.setdefault("canonical_filter_zone_ids", [])
    st.session_state.setdefault("canonical_selected_source_snapshot", None)
    st.session_state.setdefault("canonical_migration_name", "")
    st.session_state.setdefault("canonical_selected_sdwan_target_id", None)


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
    elif st.session_state["canonical_selected_source_snapshot"]:
        preferred_snapshot_id = st.session_state["canonical_selected_source_snapshot"]

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
    st.session_state["canonical_selected_source_snapshot"] = selected_option
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
        context.mapping_scope_id = None
        return
    if context.canonical_snapshot_id != latest.snapshot.id:
        context.canonical_snapshot_id = latest.snapshot.id
        context.mapping_scope_id = None
        st.session_state["canonical_page"] = 1
        st.session_state["canonical_selected_rule_ids"] = set()
        st.session_state["canonical_migration_name"] = ""
        st.session_state["canonical_selected_sdwan_target_id"] = None


def _load_zone_options(canonical_snapshot_id: UUID) -> list[tuple[str, str]]:
    scope = run_async(
        get_canonical_rule_scope().execute(
            GetCanonicalRuleScopeQuery(
                canonical_snapshot_id=canonical_snapshot_id,
                limit=1,
                offset=0,
                filters=CanonicalRuleFilters(),
                include_all_zones=True,
            )
        )
    )
    return [
        (str(zone.id), f"{zone.name} ({zone.zone_key})")
        for zone in sorted(scope.zones, key=lambda z: z.name.lower())
    ]


def _render_filters_panel(zone_options: list[tuple[str, str]]) -> None:
    with st.popover("Filters"):
        st.text_input("Name contains", key="canonical_filter_name_contains")
        st.selectbox(
            "Enabled",
            options=["Any", "Enabled", "Disabled"],
            key="canonical_filter_enabled",
        )
        st.selectbox(
            "Action",
            options=ACTION_OPTIONS,
            key="canonical_filter_action",
        )
        st.text_input("Section", key="canonical_filter_section")
        selected_zone_ids = st.session_state["canonical_filter_zone_ids"]
        valid_zone_ids = {option_id for option_id, _ in zone_options}
        selected_zone_ids = [
            zone_id for zone_id in selected_zone_ids if zone_id in valid_zone_ids
        ]
        selected_labels = [
            label for option_id, label in zone_options if option_id in selected_zone_ids
        ]
        zone_label_to_id = {label: option_id for option_id, label in zone_options}
        selected_labels = st.multiselect(
            "Zones",
            options=[label for _, label in zone_options],
            default=selected_labels,
            key="canonical_filter_zones_multiselect",
        )
        st.session_state["canonical_filter_zone_ids"] = [
            zone_label_to_id[label] for label in selected_labels
        ]
        st.caption("Search (YAQL) is not implemented in MVP.")
        st.text_input("Search (YAQL)", disabled=True, value="Not implemented in MVP")

        if st.button("Reset filters", key="canonical_reset_filters"):
            st.session_state["canonical_filter_name_contains"] = ""
            st.session_state["canonical_filter_enabled"] = "Any"
            st.session_state["canonical_filter_action"] = "Any"
            st.session_state["canonical_filter_section"] = ""
            st.session_state["canonical_filter_zone_ids"] = []
            st.session_state["canonical_page"] = 1
            st.rerun()


def _build_rule_filters() -> CanonicalRuleFilters:
    enabled_raw = st.session_state["canonical_filter_enabled"]
    enabled = None
    if enabled_raw == "Enabled":
        enabled = True
    elif enabled_raw == "Disabled":
        enabled = False
    action = st.session_state["canonical_filter_action"]
    if action == "Any":
        action = None
    section = st.session_state["canonical_filter_section"].strip() or None
    name_contains = st.session_state["canonical_filter_name_contains"].strip() or None
    return CanonicalRuleFilters(
        name_contains=name_contains,
        action=action,
        enabled=enabled,
        section=section,
        operand_zone_ids=[
            UUID(v) for v in st.session_state["canonical_filter_zone_ids"]
        ],
    )


def _render_rules_table(context) -> None:
    page = st.session_state["canonical_page"]
    offset = (page - 1) * PAGE_SIZE
    filters = _build_rule_filters()
    scope = run_async(
        get_canonical_rule_scope().execute(
            GetCanonicalRuleScopeQuery(
                canonical_snapshot_id=context.canonical_snapshot_id,
                limit=PAGE_SIZE,
                offset=offset,
                filters=filters,
                include_all_zones=True,
            )
        )
    )

    if not scope.rules:
        st.info("No rules found for current filters.")
        return

    zone_by_id = {str(zone.id): zone for zone in scope.zones}
    object_by_id = {str(obj.id): obj for obj in scope.objects}

    selected_ids: set[str] = st.session_state["canonical_selected_rule_ids"]
    rows = []
    page_rule_ids = []
    for rule in scope.rules:
        rule_id = str(rule.id)
        labels = _resolve_rule_labels(rule, zone_by_id, object_by_id)
        page_rule_ids.append(rule_id)
        rows.append(
            {
                "full_id": rule_id,
                "rule_id": _short_rule_id(rule_id),
                "priority": rule.priority,
                "name": _compact_text(rule.name, 36),
                "src_zone": _compact_text(labels["src_zone"], 24),
                "dst_zone": _compact_text(labels["dst_zone"], 24),
                "src_object": _compact_text(labels["src_object"], 28),
                "dst_object": _compact_text(labels["dst_object"], 28),
                "service": _compact_text(labels["service"], 24),
                "action": rule.action,
                "enabled": rule.enabled,
                "section": rule.section or "",
                "rule_key": _compact_text(rule.rule_key, 24),
            }
        )
    table_df = pd.DataFrame(rows)
    table_key = f"canonical_rules_table_{context.canonical_snapshot_id}_{page}"
    event = st.dataframe(
        table_df,
        key=table_key,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "full_id": None,
            "rule_id": st.column_config.TextColumn("Rule ID", width="small"),
            "priority": st.column_config.NumberColumn("Prio", width="small"),
            "name": st.column_config.TextColumn("Name", width="medium"),
            "src_zone": st.column_config.TextColumn("Src zone", width="small"),
            "dst_zone": st.column_config.TextColumn("Dst zone", width="small"),
            "src_object": st.column_config.TextColumn("Src object", width="medium"),
            "dst_object": st.column_config.TextColumn("Dst object", width="medium"),
            "service": st.column_config.TextColumn("Service", width="small"),
            "action": st.column_config.TextColumn("Action", width="small"),
            "enabled": st.column_config.CheckboxColumn("Enabled"),
            "section": st.column_config.TextColumn("Section", width="small"),
            "rule_key": st.column_config.TextColumn("Rule key", width="small"),
        },
        column_order=[
            "rule_id",
            "priority",
            "name",
            "src_object",
            "dst_object",
            "service",
            "src_zone",
            "dst_zone",
            "action",
            "enabled",
            "section",
            "rule_key",
        ],
    )

    selected_now: set[str] = set()
    if event and event.selection and event.selection.rows:
        selected_now = {
            rows[row_index]["full_id"]
            for row_index in event.selection.rows
            if 0 <= row_index < len(rows)
        }

    selected_ids -= set(page_rule_ids)
    selected_ids |= selected_now
    st.session_state["canonical_selected_rule_ids"] = selected_ids
    context.selected_canonical_rule_ids = sorted(selected_ids)

    st.caption(f"Selected rules: {len(selected_ids)}")
    _render_migration_form(context, selected_ids)

    _render_rule_context_inspector(scope.rules, zone_by_id, object_by_id)
    _render_pagination(scope.pagination.total)


@st.cache_data(ttl=60)
def _load_sdwan_targets() -> list[dict[str, str | None]]:
    result = run_async(get_sdwan_targets().execute())
    return [
        {
            "id": target.dev_obj_id,
            "name": target.name,
            "cpe_id": target.cpe_id,
        }
        for target in result.targets
    ]


def _render_migration_form(context, selected_ids: set[str]) -> None:
    st.markdown("### Migration setup")

    targets = _load_sdwan_targets()
    if not targets:
        st.warning("No SD-WAN targets available for Install On.")
        return

    target_by_id = {target["id"]: target for target in targets}
    target_ids = list(target_by_id.keys())

    if context.migration_name and not st.session_state["canonical_migration_name"]:
        st.session_state["canonical_migration_name"] = context.migration_name
    if (
        context.selected_sdwan_target_id
        and st.session_state["canonical_selected_sdwan_target_id"] is None
    ):
        st.session_state["canonical_selected_sdwan_target_id"] = (
            context.selected_sdwan_target_id
        )

    preferred_target_id = st.session_state["canonical_selected_sdwan_target_id"]
    default_index = 0
    if preferred_target_id in target_ids:
        default_index = target_ids.index(preferred_target_id)

    with st.form("canonical_migration_form"):
        st.text_input("Migration name", key="canonical_migration_name")
        st.selectbox(
            "Install On",
            options=target_ids,
            index=default_index,
            key="canonical_selected_sdwan_target_id",
            format_func=lambda target_id: _format_install_target_label(
                target_by_id[target_id]
            ),
        )
        submitted = st.form_submit_button("Generate rules", type="primary")

    if submitted:
        _run_generate_rules(context, selected_ids)

    if context.mapping_scope_id is not None:
        st.success(f"Rules generated. mapping_scope_id={context.mapping_scope_id}")


def _run_generate_rules(context, selected_ids: set[str]) -> None:
    if not selected_ids:
        st.error("Select at least one rule first.")
        return

    migration_name = st.session_state["canonical_migration_name"].strip()
    if not migration_name:
        st.error("Migration name is required.")
        return

    selected_target_id = st.session_state["canonical_selected_sdwan_target_id"]
    if not selected_target_id:
        st.error("Install On target is required.")
        return

    if context.canonical_snapshot_id is None:
        st.error("Canonical snapshot is missing.")
        return

    with st.spinner("Generating rules..."):
        result = run_async(
            get_map_canonical_to_sdwan().execute(
                MapCanonicalToSdwanCommand(
                    mapping_scope_title=migration_name,
                    sdwan_target_id=selected_target_id,
                    canonical_snapshot_id=context.canonical_snapshot_id,
                    canonical_rules_ids=[
                        UUID(rule_id) for rule_id in sorted(selected_ids)
                    ],
                )
            )
        )

    context.migration_name = migration_name
    context.selected_sdwan_target_id = selected_target_id
    context.mapping_scope_id = result.mapping_scope_id

    st.success(
        f"Mapped {result.mapped_rules_count} rules. mapping_scope_id={result.mapping_scope_id}"
    )
    try:
        st.switch_page("execute-rules")
    except Exception:
        st.info("Open 'Execute rules' page to continue with CPE selection.")


def _format_install_target_label(target: dict[str, str | None]) -> str:
    cpe = target["cpe_id"] or "n/a"
    return f"{target['name']} | cpe_id={cpe} | id={target['id']}"


def _render_pagination(total: int) -> None:
    page = st.session_state["canonical_page"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    st.session_state["canonical_page"] = page

    start = (page - 1) * PAGE_SIZE + 1
    end = min(page * PAGE_SIZE, total)
    st.caption(f"Showing {start}-{end} of {total}")

    prev_col, page_col, next_col = st.columns([1, 2, 1])
    with prev_col:
        if st.button("Prev", disabled=page <= 1):
            st.session_state["canonical_page"] = page - 1
            st.rerun()
    with page_col:
        st.markdown(
            f"<div style='text-align:center'>Page {page} / {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with next_col:
        if st.button("Next", disabled=page >= total_pages):
            st.session_state["canonical_page"] = page + 1
            st.rerun()


def _short_rule_id(rule_id: str) -> str:
    return rule_id.split("-")[0]


def _compact_text(value: str | None, limit: int) -> str:
    if not value:
        return "—"
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}…"


def _resolve_rule_labels(
    rule, zone_by_id: dict[str, object], object_by_id: dict[str, object]
) -> dict[str, str]:
    labels = {
        "src_zone": "—",
        "dst_zone": "—",
        "src_object": "—",
        "dst_object": "—",
        "service": "ANY",
    }
    for operand in rule.operands:
        role = operand.operand_role
        if operand.target_zone_id:
            zone = zone_by_id.get(str(operand.target_zone_id))
            zone_label = zone.name if zone else str(operand.target_zone_id)
            if role == "src_zone":
                labels["src_zone"] = zone_label
            elif role == "dst_zone":
                labels["dst_zone"] = zone_label
        if operand.target_object_id:
            obj = object_by_id.get(str(operand.target_object_id))
            object_label = _object_label(obj, operand.target_object_id)
            if role == "src_object":
                labels["src_object"] = object_label
            elif role == "dst_object":
                labels["dst_object"] = object_label
            elif role == "service":
                labels["service"] = object_label
    return labels


def _object_label(obj, object_id: UUID) -> str:
    if obj is None:
        return str(object_id)
    if obj.name:
        return obj.name
    if obj.cidr:
        return obj.cidr
    if obj.fqdn:
        return obj.fqdn
    if obj.object_key:
        return obj.object_key
    return str(object_id)


def _render_rule_context_inspector(
    rules: list,
    zone_by_id: dict[str, object],
    object_by_id: dict[str, object],
) -> None:
    st.markdown("### Rule context inspector")
    options = {str(rule.id): rule for rule in rules}
    selected_rule_id = st.selectbox(
        "Inspect rule",
        options=list(options.keys()),
        format_func=lambda rule_id: f"{_short_rule_id(rule_id)} | {options[rule_id].name}",
        key="canonical_context_rule_select",
    )
    selected_rule = options[selected_rule_id]
    labels = _resolve_rule_labels(selected_rule, zone_by_id, object_by_id)

    tabs = st.tabs(["Zones", "Objects", "Service", "Operands"])
    with tabs[0]:
        st.write(f"SRC: `{labels['src_zone']}`")
        st.write(f"DST: `{labels['dst_zone']}`")
    with tabs[1]:
        st.write(f"SRC object: `{labels['src_object']}`")
        st.write(f"DST object: `{labels['dst_object']}`")
    with tabs[2]:
        st.write(f"Service: `{labels['service']}`")
    with tabs[3]:
        st.json(
            [
                {
                    "role": operand.operand_role,
                    "target_zone_id": (
                        str(operand.target_zone_id) if operand.target_zone_id else None
                    ),
                    "target_object_id": (
                        str(operand.target_object_id)
                        if operand.target_object_id
                        else None
                    ),
                    "position": operand.position,
                }
                for operand in selected_rule.operands
            ]
        )
