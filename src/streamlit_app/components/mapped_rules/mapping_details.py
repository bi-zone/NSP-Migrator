from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import pandas as pd
import streamlit as st
from streamlit.elements.lib.column_types import ColumnConfig

from app.modules.mapping.application.dto import (
    CanonicalEntityDisplayDTO,
    CanonicalToSdwanEntityProjectionDTO,
    MappedSdwanEntityDisplayDTO,
    MappingCanonicalRuleProjectionDTO,
    MappingEntityCandidateDisplayDTO,
    MappingEntityResultDetailsDTO,
)
from app.modules.mapping.application.select_entity_candidate import (
    SelectEntityCandidateCommand,
)
from app.modules.mapping.application.select_sdwan_entity_directly import (
    SelectSdwanEntityDirectlyCommand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingScopeRuleOperandRole,
)
from streamlit_app.components.mapped_rules.cache import (
    invalidate_after_mapping_result_mutation,
    load_cached_mapping_result_details,
    load_cached_sdwan_catalog_rows,
)
from streamlit_app.components.mapped_rules.utils import (
    ROLE_FIELD_BY_ROLE,
    SELECTED_MAPPED_RULE_ID_KEY,
    STATUS_CELL_STYLE,
    MappedRulesProjectionState,
    StatusStyleColor,
    dash,
    short_uuid,
    status_color_for_mapping_result,
)
from streamlit_app.services.use_cases import (
    get_select_entity_candidate,
    get_select_sdwan_entity_directly,
    run_async,
)
from streamlit_app.services.utils import _filter_df_rows_by_search, short_id, text


@dataclass(frozen=True, slots=True)
class MappingDetailSectionConfig:
    section_id: str
    title: str
    role: MappingScopeRuleOperandRole
    entity_type: MappingEntityType
    direct_search_placeholder: str

    @property
    def selected_entity_state_key(self) -> str:
        return f"mapped_rules_selected_{self.section_id}_entity_id"


@dataclass(frozen=True, slots=True)
class CanonicalEntityTableRow:
    parent: str
    name: str
    value: str
    kind: str
    id: str
    canonical_entity_id: str


@dataclass(frozen=True, slots=True)
class MappedEntityTableRow:
    status: str
    strategy: str
    sdwan: str
    sdwan_value: str
    sdwan_type: str
    id: str
    entity_id: str
    _status_style_color: StatusStyleColor


MAPPING_DETAIL_SECTIONS: tuple[MappingDetailSectionConfig, ...] = (
    MappingDetailSectionConfig(
        section_id="src_zone",
        title="Source zones",
        role=MappingScopeRuleOperandRole.SRC_ZONE,
        entity_type=MappingEntityType.ZONE,
        direct_search_placeholder="name, id, zone type...",
    ),
    MappingDetailSectionConfig(
        section_id="dst_zone",
        title="Destination zones",
        role=MappingScopeRuleOperandRole.DST_ZONE,
        entity_type=MappingEntityType.ZONE,
        direct_search_placeholder="name, id, zone type...",
    ),
    MappingDetailSectionConfig(
        section_id="src_addr_obj",
        title="Source address objects",
        role=MappingScopeRuleOperandRole.SRC_ADDR_OBJECT,
        entity_type=MappingEntityType.ADDR,
        direct_search_placeholder="name, id, host, prefix, range, fqdn...",
    ),
    MappingDetailSectionConfig(
        section_id="dst_addr_obj",
        title="Destination address objects",
        role=MappingScopeRuleOperandRole.DST_ADDR_OBJECT,
        entity_type=MappingEntityType.ADDR,
        direct_search_placeholder="name, id, host, prefix, range, fqdn...",
    ),
    MappingDetailSectionConfig(
        section_id="service",
        title="Services",
        role=MappingScopeRuleOperandRole.SERVICE,
        entity_type=MappingEntityType.SERVICE,
        direct_search_placeholder="name, id, protocol, port, icmp type/code...",
    ),
)

MAPPING_DETAILS_SELECTION_STATE_KEYS: tuple[str, ...] = tuple(
    section.selected_entity_state_key for section in MAPPING_DETAIL_SECTIONS
)


def ensure_mapping_details_state() -> None:
    for key in MAPPING_DETAILS_SELECTION_STATE_KEYS:
        st.session_state.setdefault(key, None)


def reset_mapping_details_entity_selection() -> None:
    for key in MAPPING_DETAILS_SELECTION_STATE_KEYS:
        st.session_state[key] = None


def render_mapping_details(state: MappedRulesProjectionState) -> None:
    ensure_mapping_details_state()

    selected_rule_id = st.session_state.get(SELECTED_MAPPED_RULE_ID_KEY)
    if not selected_rule_id:
        st.info("Select a mapped policy row to inspect it.")
        return

    details: MappingCanonicalRuleProjectionDTO | None = state.details_by_rule_id.get(
        str(selected_rule_id)
    )
    if details is None:
        st.warning(
            "Selected mapped policy is no longer available in this mapping scope."
        )
        st.session_state[SELECTED_MAPPED_RULE_ID_KEY] = None
        reset_mapping_details_entity_selection()
        return

    st.markdown("---")
    st.subheader(
        f"Mapping details: {short_id(details.mapping_scope_rule_id)} | {details.name}"
    )
    st.caption("Objects by roles of selected policy pair")

    for section in MAPPING_DETAIL_SECTIONS:
        _render_mapping_detail_section(
            section=section,
            details=details,
        )
        st.markdown("---")


def _render_mapping_detail_section(
    *,
    section: MappingDetailSectionConfig,
    details: MappingCanonicalRuleProjectionDTO,
) -> None:
    st.markdown(f"##### {section.title}")

    projection_rows = _projection_rows_for_role(details, section.role)
    canonical_rows: list[CanonicalEntityTableRow] = _build_canonical_rows(
        projection_rows
    )
    mapped_rows: list[MappedEntityTableRow] = _build_mapped_rows(projection_rows)

    left_col, right_col = st.columns(2, gap="large")

    with left_col:
        st.markdown("###### Canonical")
        _render_canonical_entities_table(rows=canonical_rows, section=section)

    with right_col:
        st.markdown("###### Mapped")
        selected_mapping_result_id = _render_mapped_entities_table(
            rows=mapped_rows,
            section=section,
            selected_rule_id=str(details.mapping_scope_rule_id),
        )

    if selected_mapping_result_id is None:
        return

    # Do not show mapping result editor for Zones section
    if section.entity_type == MappingEntityType.ZONE:
        st.info("Zones mapping results not available for edit.")
        return

    try:
        selected_result_details = load_cached_mapping_result_details(
            UUID(selected_mapping_result_id)
        )
    except Exception as error:
        st.error(f"Failed to load selected mapping result: {error}")
        return

    _render_selected_mapping_result_editor(
        details=selected_result_details,
        section=section,
    )


def _projection_rows_for_role(
    details: MappingCanonicalRuleProjectionDTO,
    role: MappingScopeRuleOperandRole,
) -> list[CanonicalToSdwanEntityProjectionDTO]:
    return list(getattr(details, ROLE_FIELD_BY_ROLE[role]))


def _render_canonical_entities_table(
    *,
    rows: Sequence[CanonicalEntityTableRow],
    section: MappingDetailSectionConfig,
) -> None:
    if not rows:
        st.info(f"Selected policy has no canonical {section.title.lower()}.")
        return

    df = pd.DataFrame(asdict(row) for row in rows)
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_order=("parent", "name", "value", "kind"),
        column_config={
            "parent": st.column_config.TextColumn("Parent name", width="medium"),
            "name": st.column_config.TextColumn("Name", width="medium"),
            "value": st.column_config.TextColumn("Value", width="large"),
            "kind": st.column_config.TextColumn("Kind", width="small"),
            "id": None,
            "canonical_entity_id": None,
        },
    )


def _render_mapped_entities_table(
    *,
    rows: Sequence[MappedEntityTableRow],
    section: MappingDetailSectionConfig,
    selected_rule_id: str,
) -> str | None:
    selection_state_key = section.selected_entity_state_key

    if not rows:
        st.info(f"Selected policy has no mapped {section.title.lower()}.")
        st.session_state[selection_state_key] = None
        return None

    row_payload = [asdict(row) for row in rows]
    status_by_row = [row._status_style_color for row in rows]
    visible_entity_ids = {row.entity_id for row in rows if row.entity_id != "—"}

    current_entity_id = st.session_state.get(selection_state_key)
    if current_entity_id not in visible_entity_ids:
        st.session_state[selection_state_key] = None

    event = st.dataframe(
        _style_mapped_entities_dataframe(pd.DataFrame(row_payload), status_by_row),
        key=f"mapped_rules_{section.section_id}_table_{selected_rule_id}",
        width="stretch",
        hide_index=True,
        column_order=("status", "strategy", "sdwan", "sdwan_value", "sdwan_type"),
        column_config=_mapped_table_column_config(),
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows: list[int] = list(event.selection.rows)
    if selected_rows:
        selected_row_index: int = selected_rows[0]
        selected_entity_id = rows[selected_row_index].entity_id
        st.session_state[selection_state_key] = (
            selected_entity_id if selected_entity_id != "—" else None
        )
    else:
        st.session_state.pop(selection_state_key, None)

    selected_entity_id = st.session_state.get(selection_state_key)
    if selected_entity_id:
        st.caption(f"Selected mapping result: {short_id(selected_entity_id)}")

    return str(selected_entity_id) if selected_entity_id else None


def _build_canonical_rows(
    projection_rows: Sequence[CanonicalToSdwanEntityProjectionDTO],
) -> list[CanonicalEntityTableRow]:
    rows: list[CanonicalEntityTableRow] = []

    for projection_row in projection_rows:
        canonical = projection_row.canonical
        if canonical is None:
            continue
        rows.append(_canonical_table_row(canonical))

    return rows


def _build_mapped_rows(
    projection_rows: Sequence[CanonicalToSdwanEntityProjectionDTO],
) -> list[MappedEntityTableRow]:
    rows: list[MappedEntityTableRow] = []

    for projection_row in projection_rows:
        if projection_row.sdwan is None:
            rows.append(_group_placeholder_mapped_row())
            continue

        rows.append(_mapped_table_row(projection_row.sdwan))

    return rows


def _canonical_table_row(entity: CanonicalEntityDisplayDTO) -> CanonicalEntityTableRow:
    return CanonicalEntityTableRow(
        parent=dash(entity.parent_name),
        name=dash(entity.name),
        value=dash(entity.str_value),
        kind=dash(entity.type),
        id=short_uuid(entity.canonical_id),
        canonical_entity_id=dash(entity.canonical_id),
    )


def _mapped_table_row(entity: MappedSdwanEntityDisplayDTO) -> MappedEntityTableRow:
    return MappedEntityTableRow(
        status=text(entity.match_status),
        strategy=text(entity.selection_method),
        sdwan=_sdwan_label(entity),
        sdwan_value=dash(entity.str_value),
        sdwan_type=text(entity.type),
        id=short_uuid(entity.mapping_result_id),
        entity_id=dash(entity.mapping_result_id),
        _status_style_color=status_color_for_mapping_result(entity.match_status),
    )


def _group_placeholder_mapped_row() -> MappedEntityTableRow:
    return MappedEntityTableRow(
        status="—",
        strategy="—",
        sdwan="—",
        sdwan_value="—",
        sdwan_type="—",
        id="—",
        entity_id="—",
        _status_style_color=StatusStyleColor.GRAY,
    )


def _sdwan_label(entity: MappedSdwanEntityDisplayDTO) -> str:
    if entity.sdwan_id is None:
        return "—"
    if not entity.name:
        return f"{dash(entity.type)} #{entity.sdwan_id}"
    return f"{entity.name} ({dash(entity.type)} #{entity.sdwan_id})"


def _mapped_table_column_config() -> dict[str, ColumnConfig]:
    return {
        "status": st.column_config.TextColumn("Status", width="medium"),
        "strategy": st.column_config.TextColumn("Selection", width="medium"),
        "sdwan": st.column_config.TextColumn("SD-WAN id", width="medium"),
        "sdwan_value": st.column_config.TextColumn("SD-WAN value", width="medium"),
        "sdwan_type": st.column_config.TextColumn("SD-WAN type", width="medium"),
        "id": None,
        "entity_id": None,
        "_status_style_color": None,
    }


def _style_mapped_entities_dataframe(
    df: pd.DataFrame,
    status_by_row: Sequence[StatusStyleColor],
):
    def apply_row_style(row: pd.Series) -> list[str]:
        row_index = int(df.index.get_loc(row.name))
        status_kind: StatusStyleColor = status_by_row[row_index]
        status_style = STATUS_CELL_STYLE[status_kind]
        return [status_style if column == "status" else "" for column in row.index]

    return df.style.apply(apply_row_style, axis=1)


def _render_selected_mapping_result_editor(
    *,
    details: MappingEntityResultDetailsDTO,
    section: MappingDetailSectionConfig,
) -> None:
    if details.entity_type != section.entity_type:
        st.warning(
            f"Selected mapping result has type {details.entity_type}, "
            f"but current section expects {section.entity_type}."
        )
        return

    st.markdown(f"###### Selected {section.title.lower()} mapping result")
    candidate_tab, direct_tab = st.tabs(["Candidates", "Assign directly"])

    with candidate_tab:
        _render_candidate_selector(details, section)

    with direct_tab:
        _render_direct_assign(details, section)


def _render_candidate_selector(
    details: MappingEntityResultDetailsDTO,
    section: MappingDetailSectionConfig,
) -> None:
    candidates: list[MappingEntityCandidateDisplayDTO] = list(details.candidates or [])
    if not candidates:
        st.info("No candidates for this mapping result.")
        return

    candidates_dataframe = pd.DataFrame(
        _candidate_row(candidate) for candidate in candidates
    )

    df_candidates = st.dataframe(
        candidates_dataframe,
        key=f"mapped_rules_{section.section_id}_candidate_table_{details.mapping_result_id}",
        width="stretch",
        hide_index=True,
        column_config={
            "rank": st.column_config.NumberColumn("Rank", width="small"),
            "score": st.column_config.NumberColumn("Score", width="small"),
            "strategy": st.column_config.TextColumn(
                "Auto-map strategy", width="medium"
            ),
            "sdwan": st.column_config.TextColumn("SD-WAN id", width="medium"),
            "sdwan_value": st.column_config.TextColumn("SD-WAN value", width="medium"),
            "candidate_id": None,
        },
        selection_mode="single-row",
        on_select="rerun",
    )
    selected_rows = df_candidates.selection.rows

    selected_candidate_id_key = (
        f"mapped_rules_{section.section_id}_candidate_{details.mapping_result_id}"
    )
    if selected_rows:
        st.session_state[selected_candidate_id_key] = candidates_dataframe.iloc[
            selected_rows[0]
        ]["candidate_id"]

    candidate_id: str | None = st.session_state.get(selected_candidate_id_key)

    if len(candidates) == 1:
        st.caption("This mapping result has a single candidate.")
        return

    success_key = "mapped_rules_select_candidate_success"
    error_key = "mapped_rules_select_candidate_error"

    if st.button(
        "Select candidate",
        type="primary",
        disabled=candidate_id is None,
        key=f"mapped_rules_{section.section_id}_candidate_btn_{details.mapping_result_id}",
    ):
        with st.spinner("Assigning candidate for mapping result..."):
            try:
                run_async(
                    get_select_entity_candidate().execute(
                        SelectEntityCandidateCommand(
                            mapping_entity_result_id=details.mapping_result_id,
                            candidate_id=UUID(candidate_id),
                        )
                    )
                )
                invalidate_after_mapping_result_mutation(
                    mapping_scope_id=details.mapping_scope_id,
                    mapping_result_id=details.mapping_result_id,
                )
                st.session_state[success_key] = f"Candidate {candidate_id} selected."
                st.rerun()

            except Exception as error:
                st.session_state[error_key] = f"Candidate select failed: {error}"

    if success_msg := st.session_state.pop(success_key, None):
        st.success(success_msg)

    if error_msg := st.session_state.pop(error_key, None):
        st.error(error_msg)


def _render_direct_assign(
    details: MappingEntityResultDetailsDTO,
    section: MappingDetailSectionConfig,
) -> None:
    rows = load_cached_sdwan_catalog_rows(section.entity_type)
    if not rows:
        st.info(f"No SD-WAN entities found for {section.title.lower()}.")
        return

    sdwan_catalog_rows_df = pd.DataFrame(asdict(row) for row in rows)

    selected_item_id_key = f"mapped_rules_{section.section_id}_direct_assign_item_{details.mapping_result_id}"

    search_query: str | None = st.text_input(
        "Search SD-WAN entity",
        placeholder=section.direct_search_placeholder,
        key=f"mapped_rules_{section.section_id}_direct_assign_search_{details.mapping_result_id}",
    )
    filtered_by_search_df = _filter_df_rows_by_search(
        df=sdwan_catalog_rows_df,
        search_query=search_query,
        search_columns=["name", "value"],
    )

    if filtered_by_search_df.empty:
        st.info("No SD-WAN entities match the search query.")
        st.session_state[selected_item_id_key] = None
        direct_assign_item_id = None

    else:
        direct_assign_df = st.dataframe(
            filtered_by_search_df,
            key=f"mapped_rules_{section.section_id}_direct_assign_editor_{details.mapping_result_id}",
            width="stretch",
            hide_index=True,
            column_config={
                "id": None,
                "name": st.column_config.TextColumn("SD-WAN id", width="medium"),
                "value": st.column_config.TextColumn("SD-WAN value", width="large"),
            },
            selection_mode="single-row",
            on_select="rerun",
        )

        selected_rows = direct_assign_df.selection.rows

        if selected_rows:
            st.session_state[selected_item_id_key] = filtered_by_search_df.iloc[
                selected_rows[0]
            ]["id"]

        direct_assign_item_id: str | None = st.session_state.get(selected_item_id_key)  # type: ignore[no-redef]

    success_key = "mapped_rules_direct_assign_success"
    error_key = "mapped_rules_direct_assign_error"

    if st.button(
        f"Assign selected {section.entity_type}",
        type="primary",
        disabled=direct_assign_item_id is None,
        key=f"mapped_rules_{section.section_id}_assign_directly_{details.mapping_result_id}",
    ):
        with st.spinner("Assigning SD-WAN object directly..."):
            try:
                run_async(
                    get_select_sdwan_entity_directly().execute(
                        SelectSdwanEntityDirectlyCommand(
                            mapping_result_id=details.mapping_result_id,
                            sdwan_entity_id=int(direct_assign_item_id),  # type: ignore
                        )
                    )
                )
                invalidate_after_mapping_result_mutation(
                    mapping_scope_id=details.mapping_scope_id,
                    mapping_result_id=details.mapping_result_id,
                )
                st.session_state[success_key] = (
                    f"SD-WAN entity {direct_assign_item_id} assigned directly."
                )
                st.rerun()

            except Exception as error:
                st.session_state[error_key] = f"Direct assign failed: {error}"

    if success_msg := st.session_state.pop(success_key, None):
        st.success(success_msg)

    if error_msg := st.session_state.pop(error_key, None):
        st.error(error_msg)


def _candidate_row(candidate: MappingEntityCandidateDisplayDTO) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "score": candidate.score,
        "strategy": text(candidate.strategy),
        "sdwan": f"{candidate.name} ({candidate.type}) #{candidate.sdwan_id})",
        "sdwan_value": dash(candidate.str_value),
        "candidate_id": str(candidate.candidate_id),
    }
