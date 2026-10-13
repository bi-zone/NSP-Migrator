"""Streamlit history view for saved migration reports."""

from datetime import UTC
from math import ceil

import pandas as pd
import streamlit as st

from app.core.querying import Pagination
from app.modules.reports.application.dto import ReportHeaderDTO
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersQuery,
    GetReportHeadersResult,
)
from streamlit_app.components.reports.filters import (
    REPORTS_PAGE_STATE_KEY,
    SELECTED_REPORT_ID_STATE_KEY,
    ReportListControls,
    render_report_list_controls,
)
from streamlit_app.components.reports.report_policy_list import (
    render_report_policy_list,
)
from streamlit_app.services.use_cases import get_report_headers, run_async

PAGE_SIZE = 30
_VISIBLE_REPORT_IDS_STATE_KEY = "reports_visible_report_ids"


def render() -> None:
    st.title("Reports")
    st.caption("Saved results of completed policy migrations.")

    controls: ReportListControls = render_report_list_controls()
    result = _load_report_headers(
        query=GetReportHeadersQuery(
            filters=controls.filters,
            sorting=controls.sorting,
            pagination=Pagination(
                limit=PAGE_SIZE,
                offset=(_current_page() - 1) * PAGE_SIZE,
            ),
        )
    )
    _render_report_table(result.reports)
    _render_pagination(total=result.pagination.total)
    render_report_policy_list(_selected_report(result.reports))


def _load_report_headers(query: GetReportHeadersQuery) -> GetReportHeadersResult:
    with st.spinner("Loading reports..."):
        return run_async(get_report_headers().execute(query=query))


def _render_report_table(reports: list[ReportHeaderDTO]) -> None:
    report_ids = tuple(str(report.id) for report in reports)
    if st.session_state.get(_VISIBLE_REPORT_IDS_STATE_KEY) != report_ids:
        st.session_state[_VISIBLE_REPORT_IDS_STATE_KEY] = report_ids
        st.session_state[SELECTED_REPORT_ID_STATE_KEY] = None

    if not reports:
        st.info("No reports found for the current filters.")
        return

    table = pd.DataFrame(
        [
            {
                "report_id": str(report.id),
                "migration_name": report.title,
                "csp_profile": f"{report.csp_profile.name} ({report.csp_profile.base_url})",
                "project": report.project_name,
                "install_on": report.target_name,
                "created_at": report.created_at.astimezone(UTC).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                ),
            }
            for report in reports
        ]
    )
    event = st.dataframe(
        table,
        key=f"reports_table_{_current_page()}_{hash(report_ids)}",
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "report_id": None,
            "migration_name": st.column_config.TextColumn(
                "Migration name",
                width="large",
            ),
            "csp_profile": st.column_config.TextColumn("CSP"),
            "project": st.column_config.TextColumn("Project"),
            "install_on": st.column_config.TextColumn("Install on"),
            "created_at": st.column_config.TextColumn("Created at"),
        },
        column_order=(
            "migration_name",
            "csp_profile",
            "project",
            "install_on",
            "created_at",
        ),
    )
    selected_rows = list(event.selection.rows)
    st.session_state[SELECTED_REPORT_ID_STATE_KEY] = (
        str(reports[selected_rows[0]].id) if selected_rows else None
    )


def _selected_report(reports: list[ReportHeaderDTO]) -> ReportHeaderDTO | None:
    selected_report_id: str | None = st.session_state[SELECTED_REPORT_ID_STATE_KEY]
    if selected_report_id is None:
        return None

    return next(
        (report for report in reports if str(report.id) == selected_report_id),
        None,
    )


def _render_pagination(total: int) -> None:
    total_pages = max(1, ceil(total / PAGE_SIZE))
    current_page = _current_page()
    if current_page > total_pages:
        st.session_state[REPORTS_PAGE_STATE_KEY] = total_pages
        st.rerun()

    previous_column, label_column, next_column = st.columns([1, 2, 1])
    with previous_column:
        st.button(
            "<< Previous",
            key="reports_previous_page",
            disabled=current_page == 1,
            use_container_width=True,
            on_click=_change_page,
            args=(-1,),
        )
    with label_column:
        st.caption(
            f"Page {current_page} of {total_pages} · {total} report(s) total",
            text_alignment="center",
        )
    with next_column:
        st.button(
            "Next >>",
            key="reports_next_page",
            disabled=current_page == total_pages,
            use_container_width=True,
            on_click=_change_page,
            args=(1,),
        )


def _current_page() -> int:
    return st.session_state.get(REPORTS_PAGE_STATE_KEY, 1)


def _change_page(delta: int) -> None:
    st.session_state[REPORTS_PAGE_STATE_KEY] = max(1, _current_page() + delta)
    st.session_state[SELECTED_REPORT_ID_STATE_KEY] = None
