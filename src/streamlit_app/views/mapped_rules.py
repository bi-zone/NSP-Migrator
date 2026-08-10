from uuid import UUID

import streamlit as st

from app.modules.mapping.application.get_mapping_scopes import (
    GetMappingScopesResult,
)
from app.modules.mapping.domain.entities import MappingScope
from streamlit_app.components.mapped_rules.actions_toolbar import (
    render_bulk_actions_toolbar,
)
from streamlit_app.components.mapped_rules.cache import (
    load_cached_projection_state,
)
from streamlit_app.components.mapped_rules.mapping_details import (
    ensure_mapping_details_state,
    render_mapping_details,
)
from streamlit_app.components.mapped_rules.paired_tables import render_paired_tables
from streamlit_app.components.mapped_rules.utils import (
    SELECTED_MAPPED_RULE_ID_KEY,
    MappedRulesProjectionState,
)
from streamlit_app.services.use_cases import (
    get_mapping_scopes,
    run_async,
)
from streamlit_app.services.utils import short_id, str_id
from streamlit_app.session.context import SessionContext, context_as_dict, get_context

MAPPING_SCOPE_ID_KEY = "mapping_scope_id"


def render() -> None:
    st.title("Mapped rules")
    st.caption(
        "Left table is canonical truth for mapped rules in the current mapping scope. "
        "Right table is SD-WAN mapping result. Use Manual object mapping to finish "
        "entity matching."
    )

    _ensure_page_state()

    scopes: list[MappingScope] = _load_mapping_scopes()
    if not scopes:
        st.info("No mapping scopes found yet. Map canonical rules from snapshot.")
        return

    mapping_scope_id: UUID | None = _render_mapping_scope_selector(scopes)
    if not mapping_scope_id:
        st.info("Run migration from Canonical rules page.")
        with st.expander("Session context"):
            st.json(context_as_dict())
        return

    try:
        state: MappedRulesProjectionState = _load_projection_state(mapping_scope_id)
    except Exception as error:
        st.error(f"Failed to load mapped rules projection: {error}")
        with st.expander("Error details"):
            st.exception(error)
        return

    if state.unmatched_rules_count > 0:
        st.warning(
            f"{state.unmatched_rules_count} rules of mapping scope need manual fixing."
        )
    else:
        st.success("All rules of mapping scope are clear - approved for execute!")

    render_bulk_actions_toolbar(state)
    render_paired_tables(state)
    render_mapping_details(state)


def _ensure_page_state() -> None:
    context = get_context()

    st.session_state.setdefault(
        MAPPING_SCOPE_ID_KEY,
        str(context.mapping_scope_id) if context.mapping_scope_id else "",
    )
    st.session_state.setdefault(SELECTED_MAPPED_RULE_ID_KEY, None)
    ensure_mapping_details_state()


def _load_mapping_scopes() -> list[MappingScope]:
    with st.spinner("Loading mapping scopes..."):
        result: GetMappingScopesResult = run_async(get_mapping_scopes().execute())
    return result.mapping_scopes


def _render_mapping_scope_selector(scopes: list[MappingScope]) -> UUID | None:
    options_by_id: dict[str, MappingScope] = {str_id(ms.id): ms for ms in scopes}

    def format_option(option_id: str) -> str:
        scope: MappingScope = options_by_id[option_id]
        created_label = scope.created_at.strftime("%Y-%m-%d %H:%M:%S")
        return f"{scope.title} | {short_id(scope.id)} | {created_label}"

    selected_mapping_scope_id: str | None = st.selectbox(
        "Mapping scope selector (use for debug only!)",
        placeholder="Filled automatically after 'Migrate selected rules' on Canonical rules page.",
        options=options_by_id.keys(),
        index=None,
        key=MAPPING_SCOPE_ID_KEY,
        format_func=format_option,
    )

    context: SessionContext = get_context()

    if selected_mapping_scope_id is None:
        context.mapping_scope_id = None
    else:
        context.mapping_scope_id = UUID(selected_mapping_scope_id)

    return context.mapping_scope_id


def _load_projection_state(mapping_scope_id: UUID) -> MappedRulesProjectionState:
    state = load_cached_projection_state(mapping_scope_id)

    if not state.mapped_rules:
        st.error(
            f"No provided rules for mapping scope {str_id(state.mapping_scope_id)}"
        )

    return state
