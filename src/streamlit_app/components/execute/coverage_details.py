from dataclasses import asdict, dataclass

import streamlit as st

from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import CoverageField
from app.modules.execute.domain.value_objects import CoverageValue


@dataclass(frozen=True, slots=True)
class CoverageDetailTableRow:
    field: str
    covered_by_existing_object: str
    covered_planned_objects: str


_FIELD_LABELS: dict[CoverageField, str] = {
    CoverageField.SRC_ADDR_OBJECTS: "Source addresses",
    CoverageField.DST_ADDR_OBJECTS: "Destination addresses",
    CoverageField.SERVICES: "Services",
}


def render_coverage_details(plan_rule: ExecutePlanRule) -> None:
    """Render strict coverage evidence for the selected planned policy."""
    if not plan_rule.coverage_details:
        return

    st.markdown(
        f"##### Coverage details: "
        f"Planned policy `{plan_rule.draft.name}` "
        f"⊆ Existing policy #{plan_rule.matched_sdwan_rule_id}"
    )
    rows = build_coverage_detail_rows(plan_rule)

    st.caption(
        "Only strict coverage is shown. Exact values are omitted because they "
        "already match on both sides."
    )
    st.dataframe(
        [asdict(row) for row in rows],
        hide_index=True,
        width="stretch",
        column_config={
            "field": st.column_config.TextColumn("Field"),
            "covered_by_existing_object": st.column_config.TextColumn(
                "Covered by existing object",
                width="large",
            ),
            "covered_planned_objects": st.column_config.TextColumn(
                "Covered planned objects",
                width="large",
            ),
        },
    )


def build_coverage_detail_rows(
    plan_rule: ExecutePlanRule,
) -> list[CoverageDetailTableRow]:
    """Build one row per strict covering object, preserving grouped operands."""
    return [
        CoverageDetailTableRow(
            field=_FIELD_LABELS[detail.field],
            covered_by_existing_object=_coverage_value_label(detail.covering_value),
            covered_planned_objects="\n".join(
                _coverage_value_label(value) for value in detail.covered_values
            ),
        )
        for detail in plan_rule.coverage_details
    ]


def _coverage_value_label(value: CoverageValue) -> str:
    return f"{value.object_name} ({value.value})"
