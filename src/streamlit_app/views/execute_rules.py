from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID

import pandas as pd
import streamlit as st

from app.core.hashers import json_hash
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
    SdwanDeviceObject,
    SdwanNetwork,
    SdwanService,
    SdwanZone,
)
from app.modules.execute.application.dto import SdwanRuleDTO
from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesQuery,
    GetExecutePlanRulesResult,
)
from app.modules.execute.application.use_cases.get_sdwan_rules import (
    GetSdwanRulesQuery,
    GetSdwanRulesResult,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanCommand,
    PrepareExecutePlanResult,
)
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesCommand,
    PushExecutePlanRulesResult,
)
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.domain.value_objects import PlannedRuleDraft
from app.modules.mapping.application.get_sdwan_addr_objects import (
    GetSdwanAddrObjectsResult,
)
from streamlit_app.components.mapped_rules.utils import (
    STATUS_CELL_STYLE,
    StatusStyleColor,
)
from streamlit_app.services.sdwan import sdwan_item_str_value
from streamlit_app.services.use_cases import (
    get_execute_plan_rules,
    get_prepare_execute_plan,
    get_push_execute_plan_rules,
    get_sdwan_addr_objects,
    get_sdwan_rules,
    get_sdwan_services,
    get_sdwan_targets,
    get_sdwan_zones,
    run_async,
)
from streamlit_app.services.utils import build_map_by_field, normalize_key_map
from streamlit_app.session.context import context_as_dict, get_context

PREPARED_EXECUTE_PLAN_RESULT_KEY = "prepared_execute_plan_result_key"
PUSH_RULES_RESULT_KEY = "push_rules_result_key"


@dataclass(frozen=True, slots=True)
class SdwanObjectsState:

    sdwan_zones: list[SdwanZone]
    sdwan_services: list[SdwanService]
    sdwan_addr_objects: list[SdwanAddrObject]
    sdwan_networks: list[SdwanNetwork]
    sdwan_dev_objects: list[SdwanDeviceObject]

    sdwan_zone_by_id: dict[str, SdwanZone]
    sdwan_service_by_id: dict[str, SdwanService]
    sdwan_addr_object_by_id: dict[str, SdwanAddrObject]
    sdwan_network_by_network_id: dict[str, SdwanNetwork]
    sdwan_dev_objects_by_dev_obj_id: dict[str, SdwanDeviceObject]


@dataclass(frozen=True, slots=True)
class SdwanRuleTableRow:

    rule_id: str
    action: str
    ingress_zone: str
    egress_zone: str
    src_address: str
    dst_address: str
    service: str


@dataclass(frozen=True, slots=True)
class PlanRuleMatchInfoRow:
    plan_rule_id: str
    mapping_scope_rule_id: str
    matched_sdwan_rule_id: str
    match_info: str


def render() -> None:
    st.title("Execute rules")
    context = get_context()

    if context.mapping_scope_id is None:
        st.info(
            "Mapping scope is missing. Run 'Migrate selected rules' on Canonical page."
        )
        return

    _prev_mapping_scope_id_key = "prev_mapping_scope_id"
    prev_mapping_scope_id: UUID | None = st.session_state.get(
        _prev_mapping_scope_id_key, None
    )

    if prev_mapping_scope_id is None:
        st.session_state[_prev_mapping_scope_id_key] = context.mapping_scope_id

    if prev_mapping_scope_id != context.mapping_scope_id:
        context.execute_plan_id = None
        st.session_state[_prev_mapping_scope_id_key] = context.mapping_scope_id

        if PREPARED_EXECUTE_PLAN_RESULT_KEY in st.session_state:
            st.session_state.pop(PREPARED_EXECUTE_PLAN_RESULT_KEY)

        if PUSH_RULES_RESULT_KEY in st.session_state:
            st.session_state.pop(PUSH_RULES_RESULT_KEY)

        st.rerun()

    st.caption(f"mapping_scope_id: `{context.mapping_scope_id}`")
    st.caption(f"execute_plan_id: `{context.execute_plan_id}`")

    # -- check if mapping scope is approved for execute
    prepare_plan_result: PrepareExecutePlanResult | None = st.session_state.get(
        PREPARED_EXECUTE_PLAN_RESULT_KEY, None
    )
    if not prepare_plan_result:
        # -- prepare execute plan from mapping scope
        prep_btn_placeholder = st.empty()
        if prep_btn_placeholder.button("Prepare execute plan", type="primary"):
            try:
                prep_btn_placeholder.button(
                    "Preparing...", icon="spinner", disabled=True
                )

                prepared: PrepareExecutePlanResult = run_async(
                    get_prepare_execute_plan().execute(
                        PrepareExecutePlanCommand(
                            mapping_scope_id=context.mapping_scope_id,
                        )
                    )
                )
                context.execute_plan_id = prepared.id
                st.session_state[PREPARED_EXECUTE_PLAN_RESULT_KEY] = prepared
                st.rerun()

            except Exception as e:
                st.error(f"Error through preparing execute plan: {e}")
                return
        else:
            return

    _render_prepare_execute_result(prepare_plan_result)  # type: ignore
    _render_push_rules_panel(prepare_plan_result)  # type: ignore

    with st.expander("Session context"):
        st.json(context_as_dict())

    # DEV
    if st.button("Reset execute cache", type="secondary"):
        st.session_state.pop(PREPARED_EXECUTE_PLAN_RESULT_KEY)
        context.execute_plan_id = None
        st.rerun()


def _load_sdwan_objects_state() -> SdwanObjectsState:

    context = get_context()

    _sdwan_objects_state_key = (
        f"_sdwan_objects_state_key_{context.mapping_scope_id}_{context.execute_plan_id}"
    )

    if _sdwan_objects_state_key not in st.session_state:
        sdwan_zones: list[SdwanZone] = list(
            run_async(get_sdwan_zones().execute()).zones or []
        )
        sdwan_services: list[SdwanService] = list(
            run_async(get_sdwan_services().execute()).services or []
        )
        addr_objects_result: GetSdwanAddrObjectsResult = run_async(
            get_sdwan_addr_objects().execute()
        )
        sdwan_addr_objects: list[SdwanAddrObject] = addr_objects_result.addr_objects
        sdwan_networks: list[SdwanNetwork] = addr_objects_result.networks

        sdwan_dev_objects: list[SdwanDeviceObject] = list(
            run_async(get_sdwan_targets().execute()).targets or []
        )

        _objects_state = SdwanObjectsState(
            sdwan_zones=sdwan_zones,
            sdwan_services=sdwan_services,
            sdwan_addr_objects=sdwan_addr_objects,
            sdwan_networks=sdwan_networks,
            sdwan_dev_objects=sdwan_dev_objects,
            sdwan_zone_by_id=normalize_key_map(build_map_by_field(sdwan_zones, "id")),
            sdwan_service_by_id=normalize_key_map(
                build_map_by_field(sdwan_services, "id")
            ),
            sdwan_addr_object_by_id=normalize_key_map(
                build_map_by_field(sdwan_addr_objects, "id")
            ),
            sdwan_network_by_network_id=normalize_key_map(
                build_map_by_field(sdwan_networks, "network_id")
            ),
            sdwan_dev_objects_by_dev_obj_id=normalize_key_map(
                build_map_by_field(sdwan_dev_objects, "dev_obj_id")
            ),
        )

        st.session_state[_sdwan_objects_state_key] = _objects_state

    return st.session_state[_sdwan_objects_state_key]


def _render_prepare_execute_result(
    preparing_result: PrepareExecutePlanResult,
) -> None:
    class _PrepMetricsEnum(StrEnum):
        TOTAL = "Analyzed rules"
        VALID = "Valid for apply"
        MATCHED = "Found matched rules on SD-WAN"
        COVERED = "Found covered rules on SD-WAN"
        ERROR = "Errors through analyze"

    df = pd.DataFrame(
        [
            (_PrepMetricsEnum.TOTAL, preparing_result.total_rules),
            (_PrepMetricsEnum.VALID, preparing_result.new_rules),
            (_PrepMetricsEnum.MATCHED, preparing_result.matched_rules),
            (_PrepMetricsEnum.COVERED, preparing_result.covered_rules),
            (_PrepMetricsEnum.ERROR, preparing_result.errors_through_match),
        ],
        columns=["metric", "value"],
    )

    def highlight(row: pd.Series):
        if row["metric"] == _PrepMetricsEnum.VALID and row["value"] > 0:
            return ["", STATUS_CELL_STYLE[StatusStyleColor.GREEN]]

        elif (
            row["metric"] in (_PrepMetricsEnum.MATCHED, _PrepMetricsEnum.COVERED)
            and row["value"] > 0
        ):
            return ["", STATUS_CELL_STYLE[StatusStyleColor.YELLOW]]

        elif row["metric"] == _PrepMetricsEnum.ERROR and row["value"] > 0:
            return ["", STATUS_CELL_STYLE[StatusStyleColor.RED]]

        return ["", ""]

    st.markdown("#### Planned for apply and existing rules matching result")

    st.dataframe(
        df.style.apply(highlight, axis=1),
        hide_index=True,
        width="content",
        column_config={
            "metric": st.column_config.TextColumn("Metric", width="large"),
            "value": st.column_config.NumberColumn("Value", width="medium"),
        },
    )

    # Execute plan rules tables by match status
    _render_analyzed_execute_plan_rules_tables(preparing_result.id)


def _render_push_rules_panel(preparing_result: PrepareExecutePlanResult) -> None:

    if preparing_result.new_rules == 0:
        st.warning("No valid rules for applying on SD-WAN")
        return

    result_key = f"{PUSH_RULES_RESULT_KEY}_{preparing_result.id}"

    push_result: PushExecutePlanRulesResult = st.session_state.get(result_key, None)

    if not push_result:
        push_btn_placeholder = st.empty()

        if push_btn_placeholder.button(
            f"Push {preparing_result.new_rules} rules to SD-WAN", type="primary"
        ):
            try:
                push_btn_placeholder.button(
                    "Applying...", icon="spinner", disabled=True
                )

                new_push_result: PushExecutePlanRulesResult = run_async(
                    get_push_execute_plan_rules().execute(
                        command=PushExecutePlanRulesCommand(
                            execute_plan_id=preparing_result.id,
                        )
                    )
                )

                st.session_state[result_key] = new_push_result
                st.rerun()

            except Exception as e:
                st.error(f"Error through applying rules: {e}")
                return

        else:
            return

    st.space("medium")
    st.markdown("#### Push rules to SD-WAN result")
    _render_sdwan_rules_table(rules=push_result.rules)


def _render_sdwan_rules_table_from_rows(rows: list[SdwanRuleTableRow]) -> None:
    st.dataframe(
        [asdict(r) for r in rows],
        column_config={
            "rule_id": st.column_config.TextColumn("ID", width="small"),
            "action": st.column_config.TextColumn("Action", width="small"),
            "ingress_zone": st.column_config.TextColumn(
                "Ingress Zones", width="medium"
            ),
            "egress_zone": st.column_config.TextColumn("Egress Zones", width="medium"),
            "src_address": st.column_config.TextColumn("Src Addresses", width="medium"),
            "dst_address": st.column_config.TextColumn("Dst Addresses", width="medium"),
            "service": st.column_config.TextColumn("Service", width="medium"),
        },
    )


def _render_sdwan_rules_table(rules: list[SdwanRuleDTO]) -> None:
    rows: list[SdwanRuleTableRow] = _build_sdwan_rules_rows(rules)
    _render_sdwan_rules_table_from_rows(rows)


def _build_sdwan_rules_rows(rules: list[SdwanRuleDTO]) -> list[SdwanRuleTableRow]:

    sdwan_objects_state: SdwanObjectsState = _load_sdwan_objects_state()
    rows: list[SdwanRuleTableRow] = []

    for rule in rules:

        _ingress_zones_names: list[str] = [
            sdwan_item_str_value(sdwan_objects_state.sdwan_zone_by_id[str(z_id)])
            for z_id in rule.ingress_zone
        ]
        _egress_zones_names: list[str] = [
            sdwan_item_str_value(sdwan_objects_state.sdwan_zone_by_id[str(z_id)])
            for z_id in rule.egress_zone
        ]
        _src_address_strings: list[str] = [
            sdwan_item_str_value(
                sdwan_objects_state.sdwan_addr_object_by_id[str(ao.id)],
            )
            for ao in rule.src_address
        ]
        _dst_address_strings: list[str] = [
            sdwan_item_str_value(
                sdwan_objects_state.sdwan_addr_object_by_id[str(ao.id)],
            )
            for ao in rule.dst_address
        ]
        _services_strings: list[str] = [
            sdwan_item_str_value(sdwan_objects_state.sdwan_service_by_id[str(s_id)])
            for s_id in rule.service
        ]

        rows.append(
            SdwanRuleTableRow(
                rule_id=str(rule.policy_id),
                action=rule.action,
                ingress_zone=", ".join(_ingress_zones_names),
                egress_zone=", ".join(_egress_zones_names),
                src_address=", ".join(_src_address_strings),
                dst_address=", ".join(_dst_address_strings),
                service=", ".join(_services_strings),
            )
        )

    return rows


def _build_sdwan_rules_rows_from_execute_plan_rules(
    plan_rules: list[ExecutePlanRule],
) -> list[SdwanRuleTableRow]:

    sdwan_objects_state: SdwanObjectsState = _load_sdwan_objects_state()
    rows: list[SdwanRuleTableRow] = []

    for plan_rule in plan_rules:
        draft: PlannedRuleDraft = plan_rule.draft

        _ingress_zones_names: list[str] = [
            sdwan_item_str_value(sdwan_objects_state.sdwan_zone_by_id[str(z_id)])
            for z_id in draft.src_zones
        ]
        _egress_zones_names: list[str] = [
            sdwan_item_str_value(sdwan_objects_state.sdwan_zone_by_id[str(z_id)])
            for z_id in draft.dst_zones
        ]
        _src_address_strings: list[str] = [
            sdwan_item_str_value(
                sdwan_objects_state.sdwan_addr_object_by_id[str(ao_id)],
            )
            for ao_id in draft.src_addr_objects
        ]
        _dst_address_strings: list[str] = [
            sdwan_item_str_value(
                sdwan_objects_state.sdwan_addr_object_by_id[str(ao_id)],
            )
            for ao_id in draft.dst_addr_objects
        ]
        _services_strings: list[str] = [
            sdwan_item_str_value(sdwan_objects_state.sdwan_service_by_id[str(s_id)])
            for s_id in draft.services
        ]

        rows.append(
            SdwanRuleTableRow(
                rule_id="#",
                action=draft.action,
                ingress_zone=", ".join(_ingress_zones_names),
                egress_zone=", ".join(_egress_zones_names),
                src_address=", ".join(_src_address_strings),
                dst_address=", ".join(_dst_address_strings),
                service=", ".join(_services_strings),
            )
        )

    return rows


def _render_sdwan_rule_rows_from_execute_plan_rules(
    plan_rules: list[ExecutePlanRule],
) -> None:
    rows: list[SdwanRuleTableRow] = _build_sdwan_rules_rows_from_execute_plan_rules(
        plan_rules
    )
    _render_sdwan_rules_table_from_rows(rows)


def _render_matched_rules_paired_tables(
    plan_rules: list[ExecutePlanRule],
) -> None:

    # prepare objects lists
    sdwan_rules_cache_hash_key: str = (
        f"sdwan_rules_{json_hash([str(rule.id) for rule in plan_rules])}"
    )

    if sdwan_rules_cache_hash_key not in st.session_state:
        sdwan_rules_ids: list[int] = []
        for rule in plan_rules:
            if rule.matched_sdwan_rule_id is not None:
                sdwan_rules_ids.append(rule.matched_sdwan_rule_id)

        sdwan_rules_res: GetSdwanRulesResult = run_async(
            get_sdwan_rules().execute(query=GetSdwanRulesQuery(sdwan_rules_ids))
        )
        sdwan_rules_by_id: dict[str, SdwanRuleDTO] = normalize_key_map(
            build_map_by_field(sdwan_rules_res.rules, "policy_id")
        )

        sdwan_rules: list[SdwanRuleDTO] = []
        for plan_rule in plan_rules:
            if plan_rule.matched_sdwan_rule_id is not None:
                sdwan_rules.append(
                    sdwan_rules_by_id[str(plan_rule.matched_sdwan_rule_id)]
                )
        st.session_state[sdwan_rules_cache_hash_key] = sdwan_rules

    left_col, right_col = st.columns(2, gap="medium")

    with left_col:
        st.markdown("##### Planned for apply rules")
        _render_sdwan_rule_rows_from_execute_plan_rules(plan_rules)

    with right_col:
        st.markdown("##### Rules on SD-WAN")
        _render_sdwan_rules_table(st.session_state[sdwan_rules_cache_hash_key])


def _render_analyzed_execute_plan_rules_tables(
    execute_plan_id: UUID,
) -> None:
    _render_plan_rules_section(
        title="Valid rules",
        execute_plan_id=execute_plan_id,
        match_status=RuleMatchStatus.NEW,
        render_tables_func=_render_sdwan_rule_rows_from_execute_plan_rules,
    )

    _render_plan_rules_section(
        title="Matched exactly rules",
        execute_plan_id=execute_plan_id,
        match_status=RuleMatchStatus.EXACT_MATCH,
        render_tables_func=_render_matched_rules_paired_tables,
    )

    _render_plan_rules_section(
        title="Covered rules",
        execute_plan_id=execute_plan_id,
        match_status=RuleMatchStatus.COVERED_MATCH,
        render_tables_func=_render_matched_rules_paired_tables,
    )

    _render_plan_rules_section(
        title="Error rules",
        execute_plan_id=execute_plan_id,
        match_status=RuleMatchStatus.MATCH_ERROR,
        render_tables_func=_render_sdwan_rule_rows_from_execute_plan_rules,
    )


def _render_plan_rules_section(
    title: str,
    execute_plan_id: UUID,
    match_status: RuleMatchStatus,
    render_tables_func: Callable[[list[ExecutePlanRule]], None],
) -> None:

    cache_key = f"rules_{execute_plan_id}_{match_status}"
    if cache_key not in st.session_state:
        with st.spinner("Loading rules..."):
            rules_res: GetExecutePlanRulesResult = run_async(
                get_execute_plan_rules().execute(
                    query=GetExecutePlanRulesQuery(
                        execute_plan_id=execute_plan_id,
                        match_status=match_status,
                    )
                )
            )
            st.session_state[cache_key] = rules_res.plan_rules

    section_rules: list[ExecutePlanRule] = st.session_state[cache_key]
    with st.expander(f"{title} [{len(section_rules)}]"):
        render_tables_func(section_rules)
