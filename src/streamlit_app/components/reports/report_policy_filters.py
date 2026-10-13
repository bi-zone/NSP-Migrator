"""Stateful filter controls for one report's saved policy outcomes."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from app.modules.reports.domain.enums import ReportRuleMigrationResult
from app.modules.reports.ports.report_repository import ReportRuleFilters

REPORT_RULES_PAGE_STATE_KEY = "report_rules_page"

_POLICY_NAME_SEARCH_STATE_KEY = "report_rules_filter_policy_name"
_OBJECT_VALUE_SEARCH_STATE_KEY = "report_rules_filter_object_value"
_MIGRATION_RESULTS_STATE_KEY = "report_rules_filter_migration_results"


@dataclass(frozen=True, slots=True)
class ReportPolicyListControls:
    """Normalized filters selected for one report's saved policy outcomes."""

    filters: ReportRuleFilters


def render_report_policy_list_controls() -> ReportPolicyListControls:
    """Render filters for the saved policy outcomes of the selected report."""
    _ensure_state()

    with st.container(border=True):
        title_column, reset_column = st.columns([4, 1])
        with title_column:
            st.markdown("##### Policy filters")
            st.caption("Filter saved policy outcomes in the selected report.")
        with reset_column:
            st.button(
                "Reset policy filters",
                key="report_rules_reset_filters",
                use_container_width=True,
                on_click=reset_report_policy_list_controls,
            )

        name_column, object_column, result_column = st.columns([2, 2, 1])
        with name_column:
            st.text_input(
                "Search by policy name",
                key=_POLICY_NAME_SEARCH_STATE_KEY,
                placeholder="Partial name match",
                help="Case-insensitive partial search in the saved policy name.",
                on_change=_reset_page,
            )
        with object_column:
            st.text_input(
                "Search by object value",
                key=_OBJECT_VALUE_SEARCH_STATE_KEY,
                placeholder="Partial zone, address, or service value",
                help=(
                    "Case-insensitive partial search across saved zones, "
                    "addresses, and services."
                ),
                on_change=_reset_page,
            )
        with result_column:
            st.multiselect(
                "Migration result",
                options=list(ReportRuleMigrationResult),
                format_func=lambda result: result.value,
                key=_MIGRATION_RESULTS_STATE_KEY,
                placeholder="All results",
                on_change=_reset_page,
            )

    return ReportPolicyListControls(
        filters=ReportRuleFilters(
            search_by_policy_name=_normalized_string(_POLICY_NAME_SEARCH_STATE_KEY),
            search_by_object_value=_normalized_string(_OBJECT_VALUE_SEARCH_STATE_KEY),
            migration_results=tuple(st.session_state[_MIGRATION_RESULTS_STATE_KEY]),
        )
    )


def reset_report_policy_list_controls() -> None:
    """Clear policy filters and return to the first policy-results page."""
    st.session_state[_POLICY_NAME_SEARCH_STATE_KEY] = ""
    st.session_state[_OBJECT_VALUE_SEARCH_STATE_KEY] = ""
    st.session_state[_MIGRATION_RESULTS_STATE_KEY] = []
    _reset_page()


def _ensure_state() -> None:
    st.session_state.setdefault(REPORT_RULES_PAGE_STATE_KEY, 1)
    st.session_state.setdefault(_POLICY_NAME_SEARCH_STATE_KEY, "")
    st.session_state.setdefault(_OBJECT_VALUE_SEARCH_STATE_KEY, "")
    st.session_state.setdefault(_MIGRATION_RESULTS_STATE_KEY, [])


def _normalized_string(state_key: str) -> str | None:
    value = st.session_state[state_key]
    return value.strip() or None if isinstance(value, str) else None


def _reset_page() -> None:
    st.session_state[REPORT_RULES_PAGE_STATE_KEY] = 1
