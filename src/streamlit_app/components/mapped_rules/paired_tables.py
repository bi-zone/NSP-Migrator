from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeAlias

import pandas as pd
import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from app.modules.mapping.application.dto import (
    CanonicalRuleDisplayDTO,
    MappingCanonicalRuleProjectionDTO,
    MappingScopeRuleDisplayDTO,
)
from app.modules.mapping.domain.enums import MappingScopeRuleOperandRole
from streamlit_app.components.mapped_rules.mapping_details import (
    reset_mapping_details_entity_selection,
)
from streamlit_app.components.mapped_rules.utils import (
    ROLE_BY_COLUMN,
    ROLE_COLUMN_BY_ROLE,
    SELECTED_MAPPED_RULE_ID_KEY,
    STATUS_CELL_STYLE,
    MappedRulesProjectionState,
    StatusStyleColor,
    canonical_entities_for_role,
    count_need_mapping,
    entity_names_to_text,
    has_selected_sdwan_entity,
    mapped_entities_for_role,
    role_requires_mapped_entity,
    rule_rows_for_role,
    sdwan_names_to_text,
    status_color_for_rule,
)
from streamlit_app.services.utils import text


class MappedRuleRoleStatus(StrEnum):
    OK = "OK"
    NEED_MAPPING = "NEED_MAPPING"


MappedRuleRoleNeedMappingCount: TypeAlias = int
MappedRuleRoleStatusInfo: TypeAlias = tuple[
    MappedRuleRoleStatus, MappedRuleRoleNeedMappingCount
]


@dataclass(slots=True)
class CanonicalMappedPoliciesTablePair:
    mapped_rule_id: str
    canonical_rule_id: str
    canonical_row: dict[str, Any]
    mapped_row: dict[str, Any]
    canonical_role_styles: dict[str, StatusStyleColor]
    mapped_role_styles: dict[str, StatusStyleColor]
    mapped_row_roles_statuses: dict[str, MappedRuleRoleStatusInfo]
    mapped_rule_status_style: StatusStyleColor


def render_paired_tables(state: MappedRulesProjectionState) -> None:
    try:
        pairs: list[CanonicalMappedPoliciesTablePair] = _build_policy_pairs(state)
    except Exception as e:
        st.error(f"Error through rules tables building: {e}")
        return

    if not pairs:
        st.info("No mapped rules in this mapping scope.")
        return

    canonical_rows: list[dict] = [pair.canonical_row for pair in pairs]
    mapped_rows: list[dict] = [pair.mapped_row for pair in pairs]
    canonical_role_styles_by_row: list[dict[str, StatusStyleColor]] = [
        pair.canonical_role_styles for pair in pairs
    ]
    mapped_role_styles_by_row: list[dict[str, StatusStyleColor]] = [
        pair.mapped_role_styles for pair in pairs
    ]
    status_styles_by_row: list[StatusStyleColor] = [
        pair.mapped_rule_status_style for pair in pairs
    ]

    left_col, right_col = st.columns(2, gap="medium")

    with left_col:
        st.subheader("Canonical policies")
        st.caption("Only canonical rules selected for this mapping scope.")

        canonical_df = pd.DataFrame(canonical_rows)
        st.dataframe(
            _style_policy_dataframe(
                canonical_df,
                role_styles_by_row=canonical_role_styles_by_row,
                status_styles_by_row=status_styles_by_row,
            ),
            width="stretch",
            height=520,
            column_config=_policy_tables_columns_config(),
            hide_index=True,
        )

    with right_col:
        st.subheader("Mapped policies")
        st.caption("Rows are aligned with canonical policies on the left.")

        mapped_df = pd.DataFrame(mapped_rows)
        df_events = st.dataframe(
            _style_policy_dataframe(
                mapped_df,
                role_styles_by_row=mapped_role_styles_by_row,
                status_styles_by_row=status_styles_by_row,
            ),
            width="stretch",
            height=520,
            column_config=_policy_tables_columns_config(),
            on_select="rerun",
            selection_mode="single-row",
            hide_index=True,
        )
        selected_rows = df_events.selection.rows

        if selected_rows:
            selected_rule_id = mapped_df.iloc[selected_rows[0]]["id"]
            if st.session_state.get(SELECTED_MAPPED_RULE_ID_KEY) != selected_rule_id:
                reset_mapping_details_entity_selection()
            st.session_state[SELECTED_MAPPED_RULE_ID_KEY] = selected_rule_id


def _build_policy_pairs(
    state: MappedRulesProjectionState,
) -> list[CanonicalMappedPoliciesTablePair]:
    pairs: list[CanonicalMappedPoliciesTablePair] = []

    for canonical_rule, mapped_rule in zip(state.canonical_rules, state.mapped_rules):
        details = state.details_by_rule_id.get(str(mapped_rule.mapping_scope_rule_id))
        if details is None:
            raise ValueError(
                f"Not found projection details for mapping rule "
                f"{mapped_rule.mapping_scope_rule_id}"
            )

        roles_statuses = _roles_statuses_of_rule(details)
        pairs.append(
            CanonicalMappedPoliciesTablePair(
                mapped_rule_id=str(mapped_rule.mapping_scope_rule_id),
                canonical_rule_id=str(canonical_rule.canonical_rule_id),
                canonical_row=_canonical_rule_row(canonical_rule),
                mapped_row=_mapped_rule_row(mapped_rule, roles_statuses),
                canonical_role_styles=_canonical_role_styles(
                    canonical_rule, roles_statuses
                ),
                mapped_role_styles=_mapped_role_styles(details, roles_statuses),
                mapped_row_roles_statuses=roles_statuses,
                mapped_rule_status_style=status_color_for_rule(mapped_rule.status),
            )
        )

    return pairs


def _canonical_rule_row(canonical_rule: CanonicalRuleDisplayDTO) -> dict[str, str]:
    return {
        "name": canonical_rule.name,
        "action": text(canonical_rule.action),
        "src_zone": _canonical_role_text(
            canonical_rule, MappingScopeRuleOperandRole.SRC_ZONE
        ),
        "dst_zone": _canonical_role_text(
            canonical_rule, MappingScopeRuleOperandRole.DST_ZONE
        ),
        "src_object": _canonical_role_text(
            canonical_rule, MappingScopeRuleOperandRole.SRC_ADDR_OBJECT
        ),
        "dst_object": _canonical_role_text(
            canonical_rule, MappingScopeRuleOperandRole.DST_ADDR_OBJECT
        ),
        "service": _canonical_role_text(
            canonical_rule, MappingScopeRuleOperandRole.SERVICE
        ),
    }


def _mapped_rule_row(
    mapped_rule: MappingScopeRuleDisplayDTO,
    roles_statuses: dict[str, MappedRuleRoleStatusInfo],
) -> dict[str, str]:
    _, need_mapping_count = _mapped_rule_row_status(roles_statuses)
    status_text = (
        "OK" if need_mapping_count == 0 else f"Need mapping: {need_mapping_count}"
    )

    return {
        "id": str(mapped_rule.mapping_scope_rule_id),
        "name": mapped_rule.name,
        "action": text(mapped_rule.action),
        "status": status_text,
        "src_zone": _mapped_role_text(
            mapped_rule, MappingScopeRuleOperandRole.SRC_ZONE
        ),
        "dst_zone": _mapped_role_text(
            mapped_rule, MappingScopeRuleOperandRole.DST_ZONE
        ),
        "src_object": _mapped_role_text(
            mapped_rule, MappingScopeRuleOperandRole.SRC_ADDR_OBJECT
        ),
        "dst_object": _mapped_role_text(
            mapped_rule, MappingScopeRuleOperandRole.DST_ADDR_OBJECT
        ),
        "service": _mapped_role_text(mapped_rule, MappingScopeRuleOperandRole.SERVICE),
    }


def _canonical_role_text(
    canonical_rule: CanonicalRuleDisplayDTO,
    role: MappingScopeRuleOperandRole,
) -> str:
    return entity_names_to_text(canonical_entities_for_role(canonical_rule, role))


def _mapped_role_text(
    mapped_rule: MappingScopeRuleDisplayDTO,
    role: MappingScopeRuleOperandRole,
) -> str:
    return sdwan_names_to_text(mapped_entities_for_role(mapped_rule, role))


def _roles_statuses_of_rule(
    details: MappingCanonicalRuleProjectionDTO,
) -> dict[str, MappedRuleRoleStatusInfo]:
    result: dict[str, MappedRuleRoleStatusInfo] = {}

    for role, column in ROLE_COLUMN_BY_ROLE.items():
        rows = rule_rows_for_role(details, role)
        unresolved_count = count_need_mapping(rows)
        missing_required_count = (
            1
            if role_requires_mapped_entity(role) and not has_selected_sdwan_entity(rows)
            else 0
        )
        need_mapping_count = max(unresolved_count, missing_required_count)
        role_status = (
            MappedRuleRoleStatus.NEED_MAPPING
            if need_mapping_count > 0
            else MappedRuleRoleStatus.OK
        )
        result[column] = (role_status, need_mapping_count)

    return result


def _canonical_role_styles(
    canonical_rule: CanonicalRuleDisplayDTO,
    roles_statuses: dict[str, MappedRuleRoleStatusInfo],
) -> dict[str, StatusStyleColor]:
    result: dict[str, StatusStyleColor] = {}

    for role, column in ROLE_COLUMN_BY_ROLE.items():
        if role_requires_mapped_entity(role) and not canonical_entities_for_role(
            canonical_rule, role
        ):
            result[column] = StatusStyleColor.GRAY
            continue

        role_status, _ = roles_statuses[column]
        result[column] = _role_status_color(role_status)

    return result


def _mapped_role_styles(
    details: MappingCanonicalRuleProjectionDTO,
    roles_statuses: dict[str, MappedRuleRoleStatusInfo],
) -> dict[str, StatusStyleColor]:
    result: dict[str, StatusStyleColor] = {}

    for role, column in ROLE_COLUMN_BY_ROLE.items():
        rows = rule_rows_for_role(details, role)
        if role_requires_mapped_entity(role) and not has_selected_sdwan_entity(rows):
            result[column] = StatusStyleColor.YELLOW
            continue

        role_status, _ = roles_statuses[column]
        result[column] = _role_status_color(role_status)

    return result


def _mapped_rule_row_status(
    roles_statuses: dict[str, MappedRuleRoleStatusInfo],
) -> tuple[MappedRuleRoleStatus, int]:
    need_mapping_count = sum(
        count
        for role_status, count in roles_statuses.values()
        if role_status == MappedRuleRoleStatus.NEED_MAPPING
    )

    if need_mapping_count > 0:
        return MappedRuleRoleStatus.NEED_MAPPING, need_mapping_count

    return MappedRuleRoleStatus.OK, 0


def _policy_tables_columns_config() -> dict[str, ColumnConfig]:
    return {
        "row_num": st.column_config.NumberColumn("#", width="small", pinned=True),
        "id": None,
        "priority": None,
        "name": st.column_config.TextColumn("Name", width="medium"),
        "action": st.column_config.TextColumn("Action", width="small"),
        "enabled": st.column_config.CheckboxColumn("Enabled", width="small"),
        "status": st.column_config.TextColumn("Status", width="medium"),
        "src_zone": st.column_config.TextColumn("SRC zone", width="medium"),
        "dst_zone": st.column_config.TextColumn("DST zone", width="medium"),
        "src_object": st.column_config.TextColumn("SRC obj", width="large"),
        "dst_object": st.column_config.TextColumn("DST obj", width="large"),
        "service": st.column_config.TextColumn("Service", width="large"),
    }


def _role_status_color(status: MappedRuleRoleStatus) -> StatusStyleColor:
    match status:
        case MappedRuleRoleStatus.OK:
            return StatusStyleColor.GREEN
        case MappedRuleRoleStatus.NEED_MAPPING:
            return StatusStyleColor.YELLOW


def _style_policy_dataframe(
    df: pd.DataFrame,
    *,
    role_styles_by_row: list[dict[str, StatusStyleColor]],
    status_styles_by_row: list[StatusStyleColor],
):
    df.insert(0, "row_num", range(1, len(df) + 1))

    def apply_row_style(row: pd.Series) -> list[str]:
        row_index: int = df.index.get_loc(row.name)
        role_styles: dict[str, StatusStyleColor] = role_styles_by_row[row_index]
        row_status_style = STATUS_CELL_STYLE[status_styles_by_row[row_index]]

        styles: list[str] = []
        for column in row.index:
            if column in ROLE_BY_COLUMN:
                styles.append(STATUS_CELL_STYLE[role_styles[column]])
            elif column == "status":
                styles.append(row_status_style)
            else:
                styles.append("")

        return styles

    return df.style.apply(apply_row_style, axis=1)
