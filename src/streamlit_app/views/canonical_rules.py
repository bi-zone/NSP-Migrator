import math
from uuid import UUID

import pandas as pd
import streamlit as st

from app.core.querying import SortDirection, Sorting
from app.integrations.sdwan_csp_api.gateways.enums import SdwanDeviceObjectType
from app.integrations.sdwan_csp_api.gateways.models import SdwanDeviceObject
from app.integrations.sdwan_csp_api.schemas import AllowedVPCResponse
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeQuery,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceQuery,
)
from app.modules.canonical.domain.enums import ObjectKind
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleFilters,
    CanonicalRuleSearchScope,
    CanonicalRuleSortField,
)
from app.modules.imports.application.use_cases.get_source_snapshots import (
    GetSourceSnapshotsQuery,
)
from app.modules.mapping.application.discover_allowed_vpcs import (
    DiscoverAllowedVpcsQuery,
)
from app.modules.mapping.application.get_sdwan_targets import GetSdwanTargetsQuery
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanCommand,
)
from app.modules.mapping.domain.enums import MappingScopeRulesPriority
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
)
from streamlit_app.components.canonical.rule_selection import (
    dataframe_selection_state,
    merge_visible_page_selection,
    normalized_row_indices,
    row_indices_for_selected_ids,
    selected_ids_from_row_indices,
    selection_rows_match,
    visible_rows_token,
)
from streamlit_app.components.trace.view_model import (
    CanonicalDeepLink,
    build_trace_url,
    parse_canonical_deep_link,
)
from streamlit_app.services.use_cases import (
    get_canonical_object,
    get_canonical_rule_scope,
    get_csp_profiles,
    get_discover_allowed_vpcs,
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
SORT_FIELD_OPTIONS = {
    "Default (priority)": None,
    "Priority": CanonicalRuleSortField.PRIORITY,
    "Name": CanonicalRuleSortField.NAME,
    "Action": CanonicalRuleSortField.ACTION,
    "Enabled": CanonicalRuleSortField.ENABLED,
    "Section": CanonicalRuleSortField.SECTION,
    "Rule key": CanonicalRuleSortField.RULE_KEY,
    "Description": CanonicalRuleSortField.DESCRIPTION,
}
SEARCH_SCOPE_OPTIONS = {
    "Everything (rules + objects + zones)": CanonicalRuleSearchScope.ALL,
    "Rules only (name / key / ACL / action / description)": CanonicalRuleSearchScope.RULES,
    "Objects only (name / key / cidr / fqdn, incl. nested)": CanonicalRuleSearchScope.OBJECTS,
    "Zones only (name / zone_key)": CanonicalRuleSearchScope.ZONES,
}
_GROUP_KINDS = {ObjectKind.ADDR_GROUP, ObjectKind.SERVICE_GROUP}


def render() -> None:
    st.title("Canonical rules")
    context = get_context()
    _ensure_page_state()
    deep_link = parse_canonical_deep_link(st.query_params.to_dict())

    snapshots = _load_snapshots()
    if not snapshots:
        st.info("No mapped snapshots found yet. Upload and map a config first.")
        return

    selected_source_snapshot_id = _render_source_snapshot_selector(
        snapshots, deep_link=deep_link
    )
    _sync_existing_canonical_for_selected_source(selected_source_snapshot_id)
    _render_trace_link_action(selected_source_snapshot_id)

    if context.canonical_snapshot_id is None:
        st.info(
            "No canonical snapshot selected yet. Map snapshot on Upload page first."
        )
        with st.expander("Session context"):
            st.json(context_as_dict())
        return

    active_deep_link = _matching_canonical_deep_link(
        deep_link,
        source_snapshot_id=selected_source_snapshot_id,
        canonical_snapshot_id=context.canonical_snapshot_id,
    )
    if deep_link and active_deep_link is None:
        st.warning(
            "This Canonical ID belongs to a different canonical snapshot. "
            "The latest snapshot for the selected source is shown instead."
        )
    if active_deep_link:
        _apply_canonical_deep_link(active_deep_link)
        _render_canonical_deep_link_banner(active_deep_link)

    zone_options, object_options = _load_filter_options(context.canonical_snapshot_id)
    _render_filters_panel(zone_options, object_options)
    _render_rules_table(context)

    with st.expander("Session context"):
        st.json(context_as_dict())


def _render_trace_link_action(selected_source_snapshot_id: UUID) -> None:
    context = get_context()
    selected_rule_ids = st.session_state.get("canonical_selected_rule_ids", set())
    if len(selected_rule_ids) == 1 and context.canonical_snapshot_id is not None:
        selected_rule_id = next(iter(selected_rule_ids))
        st.link_button(
            "Open selected rule in Trace",
            build_trace_url(
                source_snapshot_id=str(selected_source_snapshot_id),
                canonical_snapshot_id=str(context.canonical_snapshot_id),
                canonical_kind="rule",
                canonical_id=selected_rule_id,
            ),
            icon=":material/open_in_new:",
        )
        return
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
    st.session_state.setdefault("canonical_filter_search", "")
    st.session_state.setdefault(
        "canonical_filter_search_scope",
        "Everything (rules + objects + zones)",
    )
    st.session_state.setdefault("canonical_filter_enabled", "Any")
    st.session_state.setdefault("canonical_filter_action", "Any")
    st.session_state.setdefault("canonical_filter_section", "")
    st.session_state.setdefault("canonical_filter_zone_ids", [])
    st.session_state.setdefault("canonical_filter_object_ids", [])
    st.session_state.setdefault("canonical_sort_by_label", "Default (priority)")
    st.session_state.setdefault("canonical_sort_dir", "asc")
    st.session_state.setdefault("canonical_selected_source_snapshot", None)
    st.session_state.setdefault("canonical_migration_name", "")
    st.session_state.setdefault("canonical_selected_sdwan_target_id", None)
    st.session_state.setdefault("canonical_deep_rule_ids", [])
    st.session_state.setdefault("canonical_deep_link_signature", None)
    st.session_state.setdefault("canonical_rules_visible_ids", None)
    st.session_state.setdefault("canonical_rules_table_key", None)
    st.session_state.setdefault("canonical_rules_pending_sync", False)


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


def _render_source_snapshot_selector(
    snapshots: list,
    *,
    deep_link: CanonicalDeepLink | None = None,
) -> UUID:
    options_by_id = {str(s.id): s for s in snapshots}
    option_ids = list(options_by_id.keys())
    context = get_context()
    preferred_snapshot_id = None
    if deep_link and str(deep_link.source_snapshot_id) in option_ids:
        preferred_snapshot_id = str(deep_link.source_snapshot_id)
    elif context.snapshot_id:
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


def _matching_canonical_deep_link(
    deep_link: CanonicalDeepLink | None,
    *,
    source_snapshot_id: UUID,
    canonical_snapshot_id: UUID,
) -> CanonicalDeepLink | None:
    if deep_link is None:
        return None
    if (
        deep_link.source_snapshot_id != source_snapshot_id
        or deep_link.canonical_snapshot_id != canonical_snapshot_id
    ):
        return None
    return deep_link


def _apply_canonical_deep_link(deep_link: CanonicalDeepLink) -> None:
    signature = (
        str(deep_link.canonical_snapshot_id),
        deep_link.canonical_kind.value,
        str(deep_link.canonical_id),
        str(deep_link.context_rule_id) if deep_link.context_rule_id else None,
    )
    if st.session_state["canonical_deep_link_signature"] == signature:
        return

    _reset_filters_state()
    kind = deep_link.canonical_kind.value
    canonical_id = str(deep_link.canonical_id)
    if kind == "object":
        st.session_state["canonical_filter_object_ids"] = [canonical_id]
    elif kind == "zone":
        st.session_state["canonical_filter_zone_ids"] = [canonical_id]
    elif kind == "rule":
        st.session_state["canonical_deep_rule_ids"] = [canonical_id]
    elif deep_link.context_rule_id:
        st.session_state["canonical_deep_rule_ids"] = [
            str(deep_link.context_rule_id)
        ]
    st.session_state["canonical_deep_link_signature"] = signature


def _clear_canonical_deep_link() -> None:
    st.session_state["canonical_deep_rule_ids"] = []
    st.session_state["canonical_deep_link_signature"] = None
    st.query_params.clear()


def _render_canonical_deep_link_banner(deep_link: CanonicalDeepLink) -> None:
    kind = deep_link.canonical_kind.value.replace("_", " ").title()
    with st.container(border=True):
        st.markdown(f"**Canonical entity:** {kind} · `{deep_link.canonical_id}`")
        st.caption("The rules table is filtered to this entity or its rule context.")
        if st.button("Clear Canonical ID filter", key="canonical_clear_deep_link"):
            _reset_filters_state()
            _clear_canonical_deep_link()
            st.rerun()


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
        st.session_state["canonical_rules_visible_ids"] = None
        st.session_state["canonical_rules_table_key"] = None
        st.session_state["canonical_rules_pending_sync"] = False
        st.session_state["canonical_migration_name"] = ""
        st.session_state["canonical_selected_sdwan_target_id"] = None


def _load_filter_options(
    canonical_snapshot_id: UUID,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Load zone/object catalogs for filter dropdowns via rule_scope.

    Empty filters => narrow_scope=False => full zone/object catalogs.
    """
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
    zone_options = [
        (str(zone.id), f"{zone.name} ({zone.zone_key})")
        for zone in sorted(scope.zones, key=lambda z: z.name.lower())
    ]
    object_options = [
        _object_filter_option(obj)
        for obj in sorted(scope.objects, key=lambda o: (o.name or "").lower())
    ]
    return zone_options, object_options


def _object_filter_option(obj) -> tuple[str, str]:
    """Build a (id, label) pair for the objects filter dropdown.

    Keep this as an explicit two-value return. A trailing comma after a
    concatenated f-string makes a 1-tuple and crashes the multiselect unpack.
    """
    label = (
        f"{obj.name} "
        f"[{obj.object_kind}] ({obj.object_key})"
    )
    return str(obj.id), label


def _active_filters_summary() -> str:
    parts: list[str] = []
    search = (st.session_state.get("canonical_filter_search") or "").strip()
    if search:
        scope_label = st.session_state.get(
            "canonical_filter_search_scope",
            "Everything (rules + objects + zones)",
        )
        scope = SEARCH_SCOPE_OPTIONS.get(
            scope_label, CanonicalRuleSearchScope.ALL
        ).value
        parts.append(f"search=`{search}` [{scope}]")
    enabled = st.session_state.get("canonical_filter_enabled", "Any")
    if enabled != "Any":
        parts.append(f"enabled={enabled}")
    action = st.session_state.get("canonical_filter_action", "Any")
    if action != "Any":
        parts.append(f"action={action}")
    section = (st.session_state.get("canonical_filter_section") or "").strip()
    if section:
        parts.append(f"acl=`{section}`")
    zones = st.session_state.get("canonical_filter_zone_ids") or []
    if zones:
        parts.append(f"zones={len(zones)}")
    objects = st.session_state.get("canonical_filter_object_ids") or []
    if objects:
        parts.append(f"objects={len(objects)}")
    sort_label = st.session_state.get("canonical_sort_by_label", "Default (priority)")
    if sort_label != "Default (priority)":
        direction = st.session_state.get("canonical_sort_dir", "asc")
        parts.append(f"sort={sort_label} {direction}")
    return ", ".join(parts) if parts else "none"


def _reset_filters_state() -> None:
    st.session_state["canonical_filter_search"] = ""
    st.session_state["canonical_filter_search_scope"] = (
        "Everything (rules + objects + zones)"
    )
    st.session_state["canonical_filter_enabled"] = "Any"
    st.session_state["canonical_filter_action"] = "Any"
    st.session_state["canonical_filter_section"] = ""
    st.session_state["canonical_filter_zone_ids"] = []
    st.session_state["canonical_filter_object_ids"] = []
    st.session_state["canonical_sort_by_label"] = "Default (priority)"
    st.session_state["canonical_sort_dir"] = "asc"
    st.session_state["canonical_page"] = 1
    st.session_state["canonical_deep_rule_ids"] = []
    st.session_state["canonical_rules_visible_ids"] = None
    st.session_state["canonical_rules_table_key"] = None
    st.session_state["canonical_rules_pending_sync"] = False


def _render_filters_panel(
    zone_options: list[tuple[str, str]],
    object_options: list[tuple[str, str]],
) -> None:
    summary = _active_filters_summary()
    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.caption(f"Active filters: {summary}")
    with header_right:
        if st.button("Reset", key="canonical_reset_filters_top", use_container_width=True):
            _reset_filters_state()
            _clear_canonical_deep_link()
            st.rerun()

    search_col, match_col, sort_col = st.columns(3)

    with search_col:
        with st.expander("Search", expanded=True):
            st.selectbox(
                "Search in",
                options=list(SEARCH_SCOPE_OPTIONS.keys()),
                key="canonical_filter_search_scope",
                help=(
                    "Everything — rules + object names + zone names. "
                    "Objects — finds rules that use matching objects "
                    "(including nested group members)."
                ),
            )
            st.text_input(
                "Query (case-insensitive LIKE)",
                key="canonical_filter_search",
                placeholder="e.g. OBJ_GRP_NET-VpnPool",
            )
            st.caption("Tip: object names are found when Search in = Everything or Objects.")

    with match_col:
        with st.expander("Filters", expanded=False):
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
            st.text_input(
                "ACL / policy name (exact)",
                key="canonical_filter_section",
                help=(
                    "Exact match on the source ACL / policy block name "
                    "(Cisco ASA: access-list name). Example: global_access. "
                    "Not a free-text search — use Search for LIKE."
                ),
                placeholder="e.g. global_access",
            )
            _render_id_multiselect(
                label="Zones",
                options=zone_options,
                state_key="canonical_filter_zone_ids",
                widget_key="canonical_filter_zones_multiselect",
            )
            _render_id_multiselect(
                label="Objects (incl. nested group members)",
                options=object_options,
                state_key="canonical_filter_object_ids",
                widget_key="canonical_filter_objects_multiselect",
            )

    with sort_col:
        with st.expander("Sort", expanded=False):
            st.selectbox(
                "Sort by",
                options=list(SORT_FIELD_OPTIONS.keys()),
                key="canonical_sort_by_label",
            )
            st.selectbox(
                "Direction",
                options=["asc", "desc"],
                key="canonical_sort_dir",
            )


def _render_id_multiselect(
    *,
    label: str,
    options: list[tuple[str, str]],
    state_key: str,
    widget_key: str,
) -> None:
    selected_ids = st.session_state[state_key]
    valid_ids = {option_id for option_id, _ in options}
    selected_ids = [item_id for item_id in selected_ids if item_id in valid_ids]
    selected_labels = [
        label_text for option_id, label_text in options if option_id in selected_ids
    ]
    label_to_id = {label_text: option_id for option_id, label_text in options}
    selected_labels = st.multiselect(
        label,
        options=[label_text for _, label_text in options],
        default=selected_labels,
        key=widget_key,
    )
    st.session_state[state_key] = [label_to_id[text] for text in selected_labels]


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
    search = st.session_state["canonical_filter_search"].strip() or None
    scope_label = st.session_state.get(
        "canonical_filter_search_scope",
        "Everything (rules + objects + zones)",
    )
    search_scope = SEARCH_SCOPE_OPTIONS.get(
        scope_label, CanonicalRuleSearchScope.ALL
    )
    return CanonicalRuleFilters(
        rule_ids=[
            UUID(value) for value in st.session_state["canonical_deep_rule_ids"]
        ]
        or None,
        search=search,
        search_scope=search_scope,
        action=action,
        enabled=enabled,
        section=section,
        operand_zone_ids=[
            UUID(v) for v in st.session_state["canonical_filter_zone_ids"]
        ],
        operand_object_ids=[
            UUID(v) for v in st.session_state["canonical_filter_object_ids"]
        ],
    )


def _build_rule_sort() -> Sorting[CanonicalRuleSortField] | None:
    field = SORT_FIELD_OPTIONS.get(st.session_state["canonical_sort_by_label"])
    if field is None:
        return None
    direction = SortDirection(st.session_state["canonical_sort_dir"])
    return Sorting(field=field, direction=direction)


def _render_rules_table(context) -> None:
    page = st.session_state["canonical_page"]
    offset = (page - 1) * PAGE_SIZE
    filters = _build_rule_filters()
    sort = _build_rule_sort()
    scope = run_async(
        get_canonical_rule_scope().execute(
            GetCanonicalRuleScopeQuery(
                canonical_snapshot_id=context.canonical_snapshot_id,
                limit=PAGE_SIZE,
                offset=offset,
                filters=filters,
                sort=sort,
                include_all_zones=True,
            )
        )
    )

    if not scope.rules:
        st.session_state["canonical_rules_visible_ids"] = None
        st.session_state["canonical_rules_pending_sync"] = False
        _discard_rules_table_widget_state()
        st.info("No rules found for current filters.")
        _render_pagination(scope.pagination.total)
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
    visible_signature = tuple(page_rule_ids)
    data_changed = (
        st.session_state.get("canonical_rules_visible_ids") != visible_signature
    )
    pending_sync = bool(st.session_state.get("canonical_rules_pending_sync"))
    visible_indices = row_indices_for_selected_ids(page_rule_ids, selected_ids)
    table_key = (
        f"canonical_rules_table_{context.canonical_snapshot_id}_"
        f"{page}_{visible_rows_token(page_rule_ids)}"
    )
    _replace_rules_table_widget_key(table_key)
    if data_changed or pending_sync:
        st.session_state[table_key] = dataframe_selection_state(visible_indices)

    event = st.dataframe(
        table_df,
        key=table_key,
        width="stretch",
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

    actual_indices = normalized_row_indices(
        event.selection.rows if event and event.selection else []
    )
    in_sync = selection_rows_match(visible_indices, actual_indices)
    if data_changed:
        st.session_state["canonical_rules_visible_ids"] = visible_signature
        st.session_state["canonical_rules_pending_sync"] = not in_sync
    elif pending_sync:
        st.session_state["canonical_rules_pending_sync"] = not in_sync
    else:
        selected_now = selected_ids_from_row_indices(page_rule_ids, actual_indices)
        selected_ids = merge_visible_page_selection(
            selected_ids, page_rule_ids, selected_now
        )
        st.session_state["canonical_selected_rule_ids"] = selected_ids
    context.selected_canonical_rule_ids = sorted(selected_ids)

    _render_pagination(scope.pagination.total)
    st.caption(f"Selected for migration: {len(selected_ids)}")

    _render_rule_context_inspector(
        context.canonical_snapshot_id,
        scope.rules,
        zone_by_id,
        object_by_id,
    )

    st.divider()
    _render_migration_form(context, selected_ids)


@st.cache_data(ttl=60)
def _load_sdwan_targets(profile_id: UUID, vpc_id: str) -> list[dict[str, str]]:
    targets: list[SdwanDeviceObject] = run_async(
        get_sdwan_targets().execute(GetSdwanTargetsQuery(profile_id, vpc_id))
    ).targets

    return [
        {
            "id": target.dev_obj_id,
            "name": target.name,
            "type": target.type,
            "cpe_id": target.cpe_id if target.cpe_id else "not CPE",
        }
        for target in targets
    ]


def _render_migration_form(context, selected_ids: set[str]) -> None:
    st.markdown("### Migration setup")
    st.caption(
        "Select rules in the table above, then configure CSP target and generate mapping."
    )
    if not selected_ids:
        st.info("No rules selected yet. Multi-select rows in the table to enable migration.")

    # -- select profile
    profiles = run_async(
        get_csp_profiles().execute(query=ListProfilesQuery(active_only=True))
    ).profiles
    if not profiles:
        st.warning("Create a CSP profile in Settings first.")
        return

    profile_by_id = {profile.id: profile for profile in profiles}
    profile_ids = list(profile_by_id)

    selected_profile_id = st.selectbox(
        "CSP profile",
        options=profile_ids,
        format_func=lambda item: profile_by_id[item].name,
    )

    # -- select vpc from list, awailable for profile
    vpcs: list[AllowedVPCResponse] = run_async(
        get_discover_allowed_vpcs().execute(
            DiscoverAllowedVpcsQuery(selected_profile_id)
        )
    ).vpcs
    if not vpcs:
        st.warning("Selected profile has no allowed VPCs.")
        return

    vpc_by_id: dict[str, AllowedVPCResponse] = {vpc.vpc_id: vpc for vpc in vpcs}
    selected_vpc_id = st.selectbox(
        "VPC",
        options=list(vpc_by_id),
        format_func=lambda vpc_id: (
            f"{vpc_by_id[vpc_id].project_name} ({vpc_by_id[vpc_id].customer_name})"
            if vpc_by_id[vpc_id].project_name and vpc_by_id[vpc_id].customer_name
            else vpc_id
        ),
    )

    # -- select target (device object - cpe/group) of selected vpc
    targets = _load_sdwan_targets(selected_profile_id, selected_vpc_id)
    if not targets:
        st.warning("No SD-WAN targets available for Install On.")
        return

    target_by_id = {target["id"]: target for target in targets}
    target_ids = list(target_by_id.keys())

    # -- check values in state
    if context.migration_name and not st.session_state["canonical_migration_name"]:
        st.session_state["canonical_migration_name"] = context.migration_name
    if (
        context.selected_sdwan_target_id
        and st.session_state["canonical_selected_sdwan_target_id"] is None
    ):
        st.session_state["canonical_selected_sdwan_target_id"] = (
            context.selected_sdwan_target_id
        )

    st.text_input("Migration name", key="canonical_migration_name")

    selected_target_id: str | None = st.selectbox(
        "Install On",
        options=target_ids,
        # index=default_index,
        key="canonical_selected_sdwan_target_id",
        format_func=lambda target_id: _format_install_target_label(
            target_by_id[target_id]
        ),
    )
    if not selected_target_id:
        return

    selected_target = target_by_id[selected_target_id]
    is_device: bool = selected_target["type"] == SdwanDeviceObjectType.DEVICE

    if is_device:
        # For device always LOCAL, selector not needed
        st.session_state["canonical_policies_priority"] = (
            MappingScopeRulesPriority.LOCAL
        )
    else:
        st.selectbox(
            "Policies priority placement (for GROUP only)",
            options=[
                MappingScopeRulesPriority.PRE,
                MappingScopeRulesPriority.POST,
            ],
            index=1,
            key="canonical_policies_priority",
            format_func=lambda priority: priority.value.upper(),
        )

    if st.button("Generate rules", type="primary"):
        context.selected_csp_profile_id = selected_profile_id
        context.selected_vpc_id = selected_vpc_id
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

    selected_policies_priority = st.session_state["canonical_policies_priority"]
    if not selected_policies_priority:
        st.error("Priority should be selected.")
        return

    if context.canonical_snapshot_id is None:
        st.error("Canonical snapshot is missing.")
        return
    if context.selected_csp_profile_id is None or not context.selected_vpc_id:
        st.error("CSP profile and VPC are required.")
        return

    with st.spinner("Generating rules..."):
        result = run_async(
            get_map_canonical_to_sdwan().execute(
                MapCanonicalToSdwanCommand(
                    mapping_scope_title=migration_name,
                    csp_profile_id=context.selected_csp_profile_id,
                    vpc_id=context.selected_vpc_id,
                    sdwan_target_id=selected_target_id,
                    rules_priority=selected_policies_priority,
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


def _format_install_target_label(target: dict[str, str]) -> str:
    return f"{target['name']} | {target['type'].upper()} | {target['id']}"


def _discard_rules_table_widget_state() -> None:
    previous_key = st.session_state.get("canonical_rules_table_key")
    if previous_key and previous_key in st.session_state:
        del st.session_state[previous_key]
    st.session_state["canonical_rules_table_key"] = None


def _replace_rules_table_widget_key(table_key: str) -> None:
    previous_key = st.session_state.get("canonical_rules_table_key")
    if previous_key and previous_key != table_key and previous_key in st.session_state:
        del st.session_state[previous_key]
    st.session_state["canonical_rules_table_key"] = table_key


def _go_prev_page() -> None:
    st.session_state["canonical_page"] = max(
        1, int(st.session_state.get("canonical_page", 1)) - 1
    )
    st.session_state["canonical_rules_visible_ids"] = None
    st.session_state["canonical_rules_pending_sync"] = True


def _go_next_page() -> None:
    st.session_state["canonical_page"] = int(st.session_state.get("canonical_page", 1)) + 1
    st.session_state["canonical_rules_visible_ids"] = None
    st.session_state["canonical_rules_pending_sync"] = True


def _render_pagination(total: int) -> None:
    page = st.session_state["canonical_page"]
    total_pages = max(1, math.ceil(total / PAGE_SIZE) if total else 1)
    page = min(page, total_pages)
    st.session_state["canonical_page"] = page

    if total == 0:
        st.caption("Showing 0 of 0")
        return

    start = (page - 1) * PAGE_SIZE + 1
    end = min(page * PAGE_SIZE, total)
    st.caption(f"Showing {start}-{end} of {total}")

    prev_col, page_col, next_col = st.columns([1, 2, 1])
    with prev_col:
        st.button(
            "Prev",
            disabled=page <= 1,
            on_click=_go_prev_page,
            key="canonical_page_prev",
        )
    with page_col:
        st.markdown(
            f"<div style='text-align:center'>Page {page} / {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with next_col:
        st.button(
            "Next",
            disabled=page >= total_pages,
            on_click=_go_next_page,
            key="canonical_page_next",
        )


def _short_rule_id(rule_id: str) -> str:
    return rule_id.split("-")[0]


def _compact_text(value: str | None, limit: int) -> str:
    if not value:
        return "—"
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


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


def _is_group_object(obj) -> bool:
    if obj is None:
        return False
    kind = obj.object_kind
    if isinstance(kind, ObjectKind):
        return kind in _GROUP_KINDS
    return str(kind) in {k.value for k in _GROUP_KINDS}


@st.cache_data(ttl=30, show_spinner=False)
def _cached_object_members(
    canonical_snapshot_id: str,
    parent_object_id: str,
) -> list[dict[str, str | int]]:
    """Load group members — same pattern as Trace _cached_object_members."""
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
            "child_object_id": str(member.child_object_id),
            "position": member.position,
        }
        for member in result.members
    ]


def _load_object_members(
    *,
    canonical_snapshot_id: UUID,
    parent_object_id: UUID,
) -> list[dict[str, str | int]]:
    try:
        return _cached_object_members(str(canonical_snapshot_id), str(parent_object_id))
    except Exception:
        return []


def _object_kind_label(obj) -> str:
    if obj is None:
        return "unknown"
    kind = getattr(obj, "object_kind", None)
    if kind is None:
        return "unknown"
    return kind.value if isinstance(kind, ObjectKind) else str(kind)


def _object_value_summary(obj) -> str:
    """Human-readable leaf payload (cidr/fqdn/ports) for inspector cards."""
    if obj is None:
        return "—"
    if obj.cidr:
        return obj.cidr
    if obj.fqdn:
        return obj.fqdn
    if obj.range_start and obj.range_end:
        return f"{obj.range_start}–{obj.range_end}"
    if obj.protocol:
        port = ""
        if obj.port_from is not None:
            if obj.port_to is not None and obj.port_to != obj.port_from:
                port = f" {obj.port_from}-{obj.port_to}"
            else:
                port = f"/{obj.port_from}"
        return f"{obj.protocol}{port}"
    return _object_kind_label(obj)


def _parse_description_pairs(description: str | None) -> list[tuple[str, str]]:
    if not description:
        return []
    pairs: list[tuple[str, str]] = []
    for chunk in description.split(";"):
        part = chunk.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            pairs.append((key.strip(), value.strip()))
        else:
            pairs.append(("note", part))
    return pairs


def _render_description_block(description: str | None) -> None:
    pairs = _parse_description_pairs(description)
    if not pairs:
        if description:
            st.caption(description)
        return
    with st.expander("Rule metadata", expanded=False):
        for key, value in pairs:
            st.markdown(f"- **{key}**: `{value}`")


def _render_group_members(
    *,
    canonical_snapshot_id: UUID,
    object_id: UUID,
    object_by_id: dict[str, object],
) -> None:
    members = _load_object_members(
        canonical_snapshot_id=canonical_snapshot_id,
        parent_object_id=object_id,
    )
    if not members:
        st.caption("Group has no members.")
        return
    st.markdown(f"**Members ({len(members)})**")
    for member in sorted(members, key=lambda item: int(item["position"])):
        child_id = str(member["child_object_id"])
        child = object_by_id.get(child_id)
        child_label = _object_label(child, UUID(child_id))
        kind = _object_kind_label(child)
        value = _object_value_summary(child)
        if value and value != kind:
            st.markdown(f"- `{child_label}` · {kind} · `{value}`")
        else:
            st.markdown(f"- `{child_label}` · {kind}")


def _render_object_side(
    *,
    title: str,
    role: str,
    canonical_snapshot_id: UUID,
    rule,
    object_by_id: dict[str, object],
) -> None:
    """Render SRC/DST/service object card: group members or leaf details."""
    st.markdown(f"**{title}**")
    operands = [
        op
        for op in (rule.operands or [])
        if op.target_object_id is not None and str(op.operand_role) == role
    ]
    if not operands:
        st.caption("—")
        return

    for operand in operands:
        obj = object_by_id.get(str(operand.target_object_id))
        label = _object_label(obj, operand.target_object_id)
        kind = _object_kind_label(obj)
        if _is_group_object(obj):
            with st.expander(f"Group · `{label}`", expanded=True):
                st.caption(f"kind: `{kind}`")
                _render_group_members(
                    canonical_snapshot_id=canonical_snapshot_id,
                    object_id=operand.target_object_id,
                    object_by_id=object_by_id,
                )
        else:
            with st.container(border=True):
                st.markdown(f"`{label}`")
                st.caption(f"Leaf · `{kind}` — no nested members")
                value = _object_value_summary(obj)
                if value and value != kind:
                    st.code(value, language=None)


def _render_rule_context_inspector(
    canonical_snapshot_id: UUID,
    rules: list,
    zone_by_id: dict[str, object],
    object_by_id: dict[str, object],
) -> None:
    st.markdown("### Inspect rule")
    options = {str(rule.id): rule for rule in rules}
    selected_rule_id = st.selectbox(
        "Rule on this page",
        options=list(options.keys()),
        format_func=lambda rule_id: (
            f"{_short_rule_id(rule_id)} | {options[rule_id].name}"
        ),
        key="canonical_context_rule_select",
    )
    selected_rule = options[selected_rule_id]
    labels = _resolve_rule_labels(selected_rule, zone_by_id, object_by_id)

    meta_cols = st.columns(4)
    meta_cols[0].metric("Action", selected_rule.action)
    meta_cols[1].metric("Enabled", "yes" if selected_rule.enabled else "no")
    meta_cols[2].metric("Priority", selected_rule.priority)
    meta_cols[3].metric("Section", selected_rule.section or "—")

    _render_description_block(selected_rule.description)

    tabs = st.tabs(["Overview", "Objects", "Service", "Operands"])
    with tabs[0]:
        left, right = st.columns(2)
        with left:
            st.markdown("**Source zone**")
            st.code(labels["src_zone"], language=None)
            st.markdown("**Source object**")
            st.code(labels["src_object"], language=None)
        with right:
            st.markdown("**Destination zone**")
            st.code(labels["dst_zone"], language=None)
            st.markdown("**Destination object**")
            st.code(labels["dst_object"], language=None)
        st.markdown("**Service**")
        st.code(labels["service"], language=None)

    with tabs[1]:
        st.caption(
            "Nested members are shown only for address/service **groups**. "
            "Leaf objects (host, subnet, …) have no children."
        )
        src_col, dst_col = st.columns(2)
        with src_col:
            _render_object_side(
                title="Source",
                role="src_object",
                canonical_snapshot_id=canonical_snapshot_id,
                rule=selected_rule,
                object_by_id=object_by_id,
            )
        with dst_col:
            _render_object_side(
                title="Destination",
                role="dst_object",
                canonical_snapshot_id=canonical_snapshot_id,
                rule=selected_rule,
                object_by_id=object_by_id,
            )

    with tabs[2]:
        _render_object_side(
            title="Service",
            role="service",
            canonical_snapshot_id=canonical_snapshot_id,
            rule=selected_rule,
            object_by_id=object_by_id,
        )

    with tabs[3]:
        st.json(
            [
                {
                    "role": str(operand.operand_role),
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
                for operand in selected_rule.operands or []
            ]
        )
