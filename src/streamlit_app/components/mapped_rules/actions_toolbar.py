from uuid import UUID

import streamlit as st

from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeCommand,
)
from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeCommand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingScopeRuleOperandRole,
    SDWANZoneDirection,
)
from streamlit_app.components.mapped_rules.cache import (
    SdwanCatalogTableRow,
    invalidate_after_scope_mapping_mutation,
    invalidate_after_sdwan_catalog_mutation,
    load_cached_sdwan_catalog_rows,
)
from streamlit_app.components.mapped_rules.utils import (
    ENTITY_ROLE_LABELS,
    MappedRulesProjectionState,
)
from streamlit_app.services.use_cases import (
    get_assign_zone_for_scope,
    get_auto_select_entities_with_create,
    run_async,
)


def render_bulk_actions_toolbar(state: MappedRulesProjectionState) -> None:
    with st.expander("Bulk actions", expanded=False):
        tab_assign_zone, tab_auto_create = st.tabs(
            ["Assign zone for all rules", "Auto-create unresolved"]
        )

        with tab_assign_zone:
            _render_assign_zone_tab(
                mapping_scope_id=state.mapping_scope_id,
                zones=load_cached_sdwan_catalog_rows(MappingEntityType.ZONE),
            )

        with tab_auto_create:
            _render_auto_create_tab(state.mapping_scope_id)


def _render_assign_zone_tab(
    *,
    mapping_scope_id: UUID,
    zones: list[SdwanCatalogTableRow],
) -> None:
    if not zones:
        st.info("No SD-WAN zones found.")
        return

    zone_by_id: dict[str, SdwanCatalogTableRow] = {zone.id: zone for zone in zones}
    zone_ids: list[str] = list(zone_by_id.keys())

    _success_key = "mapped_rules_assign_zone_success"
    _error_key = "mapped_rules_assign_zone_error"

    with st.form("mapped_rules_assign_zone_form"):
        zone_id: str = st.selectbox(
            "SD-WAN zone",
            options=zone_ids,
            format_func=lambda value: _sdwan_zone_label(zone_by_id[value]),
        )
        direction: SDWANZoneDirection = st.selectbox(
            "Direction",
            options=[SDWANZoneDirection.SRC_ZONE, SDWANZoneDirection.DST_ZONE],
            format_func=lambda value: ENTITY_ROLE_LABELS[
                _zone_direction_to_role(value)
            ],
        )
        submitted = st.form_submit_button("Assign zone", type="primary")

        if submitted:
            try:
                with st.spinner("Assigning zones to policies of scope..."):
                    run_async(
                        get_assign_zone_for_scope().execute(
                            AssignZoneForScopeCommand(
                                zone_direction=direction,
                                zone_sdwan_id=int(zone_id),
                                mapping_scope_id=mapping_scope_id,
                            )
                        )
                    )
                invalidate_after_scope_mapping_mutation(
                    mapping_scope_id=mapping_scope_id,
                )
                st.session_state[_success_key] = (
                    "Zone assigned to rules in this mapping scope."
                )
                st.rerun()
            except Exception as error:
                st.session_state[_error_key] = f"Zone assign failed: {error}"

        if success_msg := st.session_state.pop(_success_key, None):
            st.success(success_msg)

        if error_msg := st.session_state.pop(_error_key, None):
            st.error(error_msg)


def _render_auto_create_tab(mapping_scope_id) -> None:
    _success_key = "mapped_rules_auto_create_success"
    _error_key = "mapped_rules_auto_create_error"

    st.write(
        "Creates and automatically selects unresolved address and service entities on SD-WAN. "
        "Zones are not auto-created."
    )
    if st.button("Auto-create unresolved", type="primary"):
        try:
            with st.spinner("Trying to create unresolved..."):
                result = run_async(
                    get_auto_select_entities_with_create().execute(
                        AutoSelectEntitiesWithCreateForScopeCommand(
                            mapping_scope_id=mapping_scope_id
                        )
                    )
                )

            invalidate_after_sdwan_catalog_mutation(mapping_scope_id=mapping_scope_id)

            fails_string = "\n - ".join(result.errors)
            st.session_state[_success_key] = (
                f"Completed. success={result.success_selects}, "
                f"failed={result.failed_selects}\n"
                f"\n - {fails_string}"
            )
            st.rerun()

        except Exception as error:
            st.session_state[_error_key] = f"Auto-create failed: {error}"

    if success_msg := st.session_state.pop(_success_key, None):
        st.success(success_msg)

    if error_msg := st.session_state.pop(_error_key, None):
        st.error(error_msg)


def _zone_direction_to_role(
    direction: SDWANZoneDirection,
) -> MappingScopeRuleOperandRole:
    if direction == SDWANZoneDirection.SRC_ZONE:
        return MappingScopeRuleOperandRole.SRC_ZONE
    return MappingScopeRuleOperandRole.DST_ZONE


def _sdwan_zone_label(zone: SdwanCatalogTableRow) -> str:
    return zone.name
