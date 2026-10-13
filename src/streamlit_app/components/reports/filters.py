"""Stateful filter controls for the Streamlit Reports history view."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import streamlit as st

from app.core.querying import SortDirection, Sorting
from app.modules.mapping.application.discover_allowed_vpcs import (
    DiscoverAllowedVpcsQuery,
)
from app.modules.mapping.application.get_sdwan_targets import GetSdwanTargetsQuery
from app.modules.reports.ports.report_repository import (
    ReportHeaderFilters,
    ReportHeaderSortField,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
)
from streamlit_app.services.use_cases import (
    get_csp_profiles,
    get_discover_allowed_vpcs,
    get_sdwan_targets,
    run_async,
)

REPORTS_PAGE_STATE_KEY = "reports_page"
SELECTED_REPORT_ID_STATE_KEY = "reports_selected_report_id"

_SEARCH_STATE_KEY = "reports_filter_search_by_name"
_CREATED_FROM_STATE_KEY = "reports_filter_created_from"
_CREATED_TO_STATE_KEY = "reports_filter_created_to"
_PROFILE_ID_STATE_KEY = "reports_filter_csp_profile_id"
_VPC_ID_STATE_KEY = "reports_filter_vpc_id"
_TARGET_IDS_STATE_KEY = "reports_filter_target_ids"
_SORT_DIRECTION_STATE_KEY = "reports_sort_direction"


@dataclass(frozen=True, slots=True)
class ReportListControls:
    """Normalized filters and order selected in the Reports view."""

    filters: ReportHeaderFilters
    sorting: Sorting[ReportHeaderSortField]


class SortCreatedAtOptions(StrEnum):
    NEWEST_FIRST = "Newest first"
    OLDEST_FIRST = "Oldest first"


def render_report_list_controls() -> ReportListControls:
    """Render dependent filters and return the Reports application values."""
    _ensure_state()

    with st.container(border=True):
        title_column, reset_column = st.columns([4, 1])
        with title_column:
            st.markdown("##### Filters")
            st.caption("Filter saved migration reports. All dates are UTC.")
        with reset_column:
            st.button(
                "Reset filters",
                key="reports_reset_filters",
                use_container_width=True,
                on_click=_reset_filters,
            )

        search_column, date_column, sort_column = st.columns([2, 2, 1])
        with search_column:
            st.text_input(
                "Search by migration name",
                key=_SEARCH_STATE_KEY,
                placeholder="Partial name match",
                help="Case-insensitive partial search in the report title.",
                on_change=_reset_page_and_selection,
            )
        with date_column:
            from_column, to_column = st.columns(2)
            with from_column:
                st.date_input(
                    "Created from",
                    max_value="today",
                    key=_CREATED_FROM_STATE_KEY,
                    on_change=_reset_page_and_selection,
                )
            with to_column:
                st.date_input(
                    "Created to",
                    max_value="today",
                    key=_CREATED_TO_STATE_KEY,
                    on_change=_reset_page_and_selection,
                )
        with sort_column:
            st.radio(
                "Creation date-time sorting",
                options=[
                    SortCreatedAtOptions.NEWEST_FIRST,
                    SortCreatedAtOptions.OLDEST_FIRST,
                ],
                key=_SORT_DIRECTION_STATE_KEY,
                horizontal=True,
                on_change=_reset_page_and_selection,
            )

        _render_dependent_selectors()

    return ReportListControls(
        filters=ReportHeaderFilters(
            search_by_name=_normalized_string(_SEARCH_STATE_KEY),
            created_from=st.session_state[_CREATED_FROM_STATE_KEY],
            created_to=st.session_state[_CREATED_TO_STATE_KEY],
            csp_profile_id=st.session_state[_PROFILE_ID_STATE_KEY],
            vpc_id=_normalized_string(_VPC_ID_STATE_KEY),
            target_ids=tuple(st.session_state[_TARGET_IDS_STATE_KEY]),
        ),
        sorting=Sorting(
            field=ReportHeaderSortField.CREATED_AT,
            direction=_selected_sort_direction(),
        ),
    )


def _ensure_state() -> None:
    st.session_state.setdefault(REPORTS_PAGE_STATE_KEY, 1)
    st.session_state.setdefault(SELECTED_REPORT_ID_STATE_KEY, None)
    st.session_state.setdefault(_SEARCH_STATE_KEY, "")
    st.session_state.setdefault(_CREATED_FROM_STATE_KEY, None)
    st.session_state.setdefault(_CREATED_TO_STATE_KEY, None)
    st.session_state.setdefault(_PROFILE_ID_STATE_KEY, None)
    st.session_state.setdefault(_VPC_ID_STATE_KEY, None)
    st.session_state.setdefault(_TARGET_IDS_STATE_KEY, [])
    st.session_state.setdefault(
        _SORT_DIRECTION_STATE_KEY, SortCreatedAtOptions.NEWEST_FIRST
    )


def _render_dependent_selectors() -> None:
    profile_column, vpc_column, target_column = st.columns(3)
    profiles = run_async(get_csp_profiles().execute(query=ListProfilesQuery())).profiles
    profile_by_id = {profile.id: profile for profile in profiles}
    _ensure_selected_value(_PROFILE_ID_STATE_KEY, set(profile_by_id))

    with profile_column:
        st.selectbox(
            "CSP profile",
            options=[None, *profile_by_id],
            format_func=lambda profile_id: (
                "All profiles" if profile_id is None else profile_by_id[profile_id].name
            ),
            key=_PROFILE_ID_STATE_KEY,
            on_change=_on_profile_change,
        )
    # -- if csp profile not selected - no options for vpcs and devices
    selected_profile_id: UUID | None = st.session_state[_PROFILE_ID_STATE_KEY]
    if selected_profile_id is None:
        with vpc_column:
            st.selectbox(
                "Project / VPC",
                options=[None],
                format_func=lambda _: "Choose a CSP profile first",
                disabled=True,
            )
        with target_column:
            st.multiselect(
                "Install on devices",
                options=[],
                disabled=True,
                help="Choose a CSP profile and Project / VPC first.",
            )
        return

    # -- load vpcs options for selected csp profile
    try:
        vpc_options: list[tuple[str, str]] = _load_vpc_options(selected_profile_id)
    except Exception as e:
        st.warning(
            f"Unable to load Projects / VPCs for the selected CSP profile ({e})."
        )
        return

    vpc_label_by_id: dict[str, str] = dict(vpc_options)
    _ensure_selected_value(_VPC_ID_STATE_KEY, set(vpc_label_by_id))
    with vpc_column:
        st.selectbox(
            "Project / VPC",
            options=[None, *vpc_label_by_id],
            format_func=lambda vpc_id: (
                "All projects" if vpc_id is None else vpc_label_by_id[vpc_id]
            ),
            key=_VPC_ID_STATE_KEY,
            on_change=_on_vpc_change,
        )
    # -- if vpc (project) not selected - no options for devices
    selected_vpc_id: str | None = st.session_state[_VPC_ID_STATE_KEY]
    if selected_vpc_id is None:
        with target_column:
            st.multiselect(
                "Install on devices",
                options=[],
                disabled=True,
                help="Choose a Project / VPC first.",
            )
        return

    # -- load devices for selected vpc
    try:
        target_options: list[tuple[str, str]] = _load_target_options(
            selected_profile_id, selected_vpc_id
        )
    except Exception:
        st.warning(
            "Unable to load installation devices for the selected Project / VPC."
        )
        return

    target_label_by_id: dict[str, str] = dict(target_options)
    selected_target_ids = [  # validated cached selections for devices
        target_id
        for target_id in st.session_state[_TARGET_IDS_STATE_KEY]
        if target_id in target_label_by_id
    ]
    st.session_state[_TARGET_IDS_STATE_KEY] = selected_target_ids
    with target_column:
        st.multiselect(
            "Install on devices",
            options=list(target_label_by_id),
            format_func=lambda target_id: target_label_by_id[target_id],
            key=_TARGET_IDS_STATE_KEY,
            help="Select one or more devices installed in the chosen Project / VPC.",
            on_change=_reset_page_and_selection,
        )


def _load_vpc_options(profile_id: UUID) -> list[tuple[str, str]]:
    """Returns vpc_id and vpc name tuples"""
    vpcs = run_async(
        get_discover_allowed_vpcs().execute(
            DiscoverAllowedVpcsQuery(csp_profile_id=profile_id)
        )
    ).vpcs
    return sorted(
        [
            (
                vpc.vpc_id,
                f"{vpc.project_name} ({vpc.customer_name})"
                if vpc.project_name and vpc.customer_name
                else vpc.vpc_id,
            )
            for vpc in vpcs
        ],
        key=lambda option: option[1].lower(),
    )


def _load_target_options(
    profile_id: UUID,
    vpc_id: str,
) -> list[tuple[str, str]]:
    targets = run_async(
        get_sdwan_targets().execute(
            GetSdwanTargetsQuery(csp_profile_id=profile_id, vpc_id=vpc_id)
        )
    ).targets
    return sorted(
        [
            (target.dev_obj_id, f"{target.name} ({target.type.value})")
            for target in targets
        ],
        key=lambda option: option[1].lower(),
    )


def _ensure_selected_value(state_key: str, valid_values: set[object]) -> None:
    if st.session_state[state_key] not in valid_values:
        st.session_state[state_key] = None


def _normalized_string(state_key: str) -> str | None:
    value = st.session_state[state_key]
    return value.strip() or None if isinstance(value, str) else None


def _selected_sort_direction() -> SortDirection:
    _sort_map = {
        SortCreatedAtOptions.NEWEST_FIRST: SortDirection.DESC,
        SortCreatedAtOptions.OLDEST_FIRST: SortDirection.ASC,
    }
    return _sort_map[st.session_state[_SORT_DIRECTION_STATE_KEY]]


def _on_profile_change() -> None:
    st.session_state[_VPC_ID_STATE_KEY] = None
    st.session_state[_TARGET_IDS_STATE_KEY] = []
    _reset_page_and_selection()


def _on_vpc_change() -> None:
    st.session_state[_TARGET_IDS_STATE_KEY] = []
    _reset_page_and_selection()


def _reset_filters() -> None:
    st.session_state[_SEARCH_STATE_KEY] = ""
    st.session_state[_CREATED_FROM_STATE_KEY] = None
    st.session_state[_CREATED_TO_STATE_KEY] = None
    st.session_state[_PROFILE_ID_STATE_KEY] = None
    st.session_state[_VPC_ID_STATE_KEY] = None
    st.session_state[_TARGET_IDS_STATE_KEY] = []
    st.session_state[_SORT_DIRECTION_STATE_KEY] = SortCreatedAtOptions.NEWEST_FIRST
    _reset_page_and_selection()


def _reset_page_and_selection() -> None:
    st.session_state[REPORTS_PAGE_STATE_KEY] = 1
    st.session_state[SELECTED_REPORT_ID_STATE_KEY] = None
