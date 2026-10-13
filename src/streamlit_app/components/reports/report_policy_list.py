"""Streamlit UI for the saved policy outcomes of one report."""

from math import ceil
from uuid import UUID

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from app.core.querying import Pagination
from app.modules.reports.application.dto import ReportHeaderDTO, ReportRuleDTO
from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfQuery,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesQuery,
    GetReportRulesResult,
)
from app.modules.reports.domain.enums import ReportRuleMigrationResult
from streamlit_app.components.mapped_rules.utils import (
    StatusStyleColor,
    status_cell_style,
)
from streamlit_app.components.reports.report_policy_filters import (
    REPORT_RULES_PAGE_STATE_KEY,
    render_report_policy_list_controls,
    reset_report_policy_list_controls,
)
from streamlit_app.services.use_cases import (
    get_generate_report_pdf,
    get_report_rules,
    run_async,
)

PAGE_SIZE = 30
_REPORT_RULES_FOR_REPORT_ID_STATE_KEY = "report_rules_for_report_id"


def render_report_policy_list(report: ReportHeaderDTO | None) -> None:
    """Render filtered saved policy outcomes for the selected report."""
    st.divider()

    if report is None:
        st.subheader("Report policies")
        st.info("Select one report row to view its policy results.")
        return

    report_id = report.id
    # Reset report selection before render pdf file control
    _reset_controls_for_report(report_id)

    subheader_column, download_column = st.columns([3, 1])
    with subheader_column:
        st.subheader(f"Report policies · {report.title}")
    with download_column:
        _render_report_pdf_actions(report_id)

    controls = render_report_policy_list_controls()
    result = _load_report_rules(
        query=GetReportRulesQuery(
            report_id=report_id,
            filters=controls.filters,
            pagination=Pagination(
                limit=PAGE_SIZE,
                offset=(_current_page() - 1) * PAGE_SIZE,
            ),
        )
    )
    _render_report_policy_table(result.rules)
    _render_pagination(total=result.pagination.total)


def _reset_controls_for_report(report_id: UUID) -> None:
    if st.session_state.get(_REPORT_RULES_FOR_REPORT_ID_STATE_KEY) != str(report_id):
        st.session_state[_REPORT_RULES_FOR_REPORT_ID_STATE_KEY] = str(report_id)
        reset_report_policy_list_controls()


def _render_report_pdf_actions(report_id: UUID) -> None:
    """Prepare a complete report PDF only after the user requests it."""

    def _generate_report_data() -> bytes:
        _result = run_async(
            get_generate_report_pdf().execute(
                GenerateReportPdfQuery(report_id=report_id)
            )
        )
        return _result.content

    st.download_button(
        "Download PDF",
        icon=":material/download:",
        icon_position="left",
        data=_generate_report_data,
        file_name=f"migration-report-{report_id}.pdf",
        mime="application/pdf",
        key=f"download_report_pdf_{report_id}",
        use_container_width=True,
    )


def _load_report_rules(query: GetReportRulesQuery) -> GetReportRulesResult:
    with st.spinner("Loading report policies..."):
        return run_async(get_report_rules().execute(query=query))


def _render_report_policy_table(rules: list[ReportRuleDTO]) -> None:
    if not rules:
        st.info("No policies found for the current filters.")
        return

    table = pd.DataFrame(
        [
            {
                "policy_name": rule.policy_name,
                "action": rule.action.value,
                "src_zones": _format_values(rule.src_zone_names),
                "dst_zones": _format_values(rule.dst_zone_names),
                "src_addresses": _format_values(rule.src_addr_values),
                "dst_addresses": _format_values(rule.dst_addr_values),
                "services": _format_values(rule.service_values),
                "migration_result": rule.migration_result.value,
                "reason": rule.reason,
            }
            for rule in rules
        ]
    )
    st.dataframe(
        _style_report_policy_dataframe(
            table,
            migration_results=[rule.migration_result for rule in rules],
        ),
        key=f"report_rules_table_{_current_page()}",
        width="stretch",
        hide_index=True,
        column_config={
            "policy_name": st.column_config.TextColumn("Policy name", width="medium"),
            "action": st.column_config.TextColumn("Action"),
            "src_zones": st.column_config.TextColumn("Src zones"),
            "dst_zones": st.column_config.TextColumn("Dst zones"),
            "src_addresses": st.column_config.TextColumn(
                "Src addresses", width="medium"
            ),
            "dst_addresses": st.column_config.TextColumn(
                "Dst addresses", width="medium"
            ),
            "services": st.column_config.TextColumn("Services", width="medium"),
            "migration_result": st.column_config.TextColumn("Migration result"),
            "reason": st.column_config.TextColumn("Reason"),
        },
        column_order=(
            "policy_name",
            "action",
            "src_zones",
            "dst_zones",
            "src_addresses",
            "dst_addresses",
            "services",
            "migration_result",
            "reason",
        ),
    )


def _format_values(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _style_report_policy_dataframe(
    dataframe: pd.DataFrame,
    *,
    migration_results: list[ReportRuleMigrationResult],
) -> Styler:
    def apply_row_style(row: pd.Series) -> list[str]:
        row_index = int(dataframe.index.get_loc(row.name))
        style = status_cell_style(
            _migration_result_style_color(migration_results[row_index])
        )
        return [style if column == "migration_result" else "" for column in row.index]

    return dataframe.style.apply(apply_row_style, axis=1)


def _migration_result_style_color(
    migration_result: ReportRuleMigrationResult,
) -> StatusStyleColor:
    if migration_result in {
        ReportRuleMigrationResult.FAILED,
        ReportRuleMigrationResult.ERROR,
    }:
        return StatusStyleColor.RED
    if migration_result == ReportRuleMigrationResult.PUSHED:
        return StatusStyleColor.GREEN
    return StatusStyleColor.YELLOW


def _render_pagination(total: int) -> None:
    total_pages = max(1, ceil(total / PAGE_SIZE))
    current_page = _current_page()
    if current_page > total_pages:
        st.session_state[REPORT_RULES_PAGE_STATE_KEY] = total_pages
        st.rerun()

    previous_column, label_column, next_column = st.columns([1, 2, 1])
    with previous_column:
        st.button(
            "<< Previous policies",
            key="report_rules_previous_page",
            disabled=current_page == 1,
            use_container_width=True,
            on_click=_change_page,
            args=(-1,),
        )
    with label_column:
        st.caption(
            f"Policies page {current_page} of {total_pages} · {total} total",
            text_alignment="center",
        )
    with next_column:
        st.button(
            "Next policies >>",
            key="report_rules_next_page",
            disabled=current_page == total_pages,
            use_container_width=True,
            on_click=_change_page,
            args=(1,),
        )


def _current_page() -> int:
    return st.session_state.get(REPORT_RULES_PAGE_STATE_KEY, 1)


def _change_page(delta: int) -> None:
    st.session_state[REPORT_RULES_PAGE_STATE_KEY] = max(1, _current_page() + delta)
