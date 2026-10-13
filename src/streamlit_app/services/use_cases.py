import asyncio
import atexit
import threading
from functools import lru_cache
from typing import Any

from app.di.container import AppContainer, create_di_container
from app.modules.canonical.application.use_cases.get_canonical_issues import (
    GetCanonicalIssuesUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_rule_scope import (
    GetCanonicalRuleScopeUseCase,
)
from app.modules.canonical.application.use_cases.get_latest_snapshot_for_source import (
    GetLatestCanonicalSnapshotForSourceUseCase,
)
from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesUseCase,
)
from app.modules.execute.application.use_cases.get_sdwan_rules import (
    GetSdwanRulesUseCase,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanUseCase,
)
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesUseCase,
)
from app.modules.imports.application.use_cases.create_import_source import (
    CreateImportSourceUseCase,
)
from app.modules.imports.application.use_cases.get_import_vendors import (
    GetImportVendorsUseCase,
)
from app.modules.imports.application.use_cases.get_source_artifact import (
    GetSourceArtifactUseCase,
)
from app.modules.imports.application.use_cases.get_source_snapshots import (
    GetSourceSnapshotsUseCase,
)
from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactUseCase,
)
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingUseCase,
)
from app.modules.mapping.application.assign_zone_for_scope import (
    AssignZoneForScopeUseCase,
)
from app.modules.mapping.application.auto_select_with_auto_create import (
    AutoSelectEntitiesWithCreateForScopeUseCase,
)
from app.modules.mapping.application.discover_allowed_vpcs import (
    DiscoverAllowedVpcsUseCase,
)
from app.modules.mapping.application.get_mapping_entity_result_details import (
    GetMappingEntityResultDetailsUseCase,
)
from app.modules.mapping.application.get_mapping_scope import GetMappingScopeUseCase
from app.modules.mapping.application.get_mapping_scope_rules import (
    GetMappingScopeRulesUseCase,
)
from app.modules.mapping.application.get_mapping_scope_rules_projection import (
    GetMappingScopeRulesProjectionUseCase,
)
from app.modules.mapping.application.get_mapping_scopes import (
    GetMappingScopesUseCase,
)
from app.modules.mapping.application.get_sdwan_addr_objects import (
    GetSdwanAddrObjectsUseCase,
)
from app.modules.mapping.application.get_sdwan_services import (
    GetSdwanServicesUseCase,
)
from app.modules.mapping.application.get_sdwan_targets import (
    GetSdwanTargetsUseCase,
)
from app.modules.mapping.application.get_sdwan_zones import GetSdwanZonesUseCase
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanUseCase,
)
from app.modules.mapping.application.select_entity_candidate import (
    SelectEntityCandidateUseCase,
)
from app.modules.mapping.application.select_entity_with_create_on_sdwan import (
    SelectEntityWithCreateOnSdwanUseCase,
)
from app.modules.mapping.application.select_sdwan_entity_directly import (
    SelectSdwanEntityDirectlyUseCase,
)
from app.modules.reports.application.use_cases.generate_report_pdf import (
    GenerateReportPdfUseCase,
)
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersUseCase,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesUseCase,
)
from app.modules.settings.csp_profiles.application.change_profile_active_status import (
    ChangeProfileActiveStatusUseCase,
)
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionUseCase,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileUseCase,
)
from app.modules.settings.csp_profiles.application.get_profile import (
    GetProfileUseCase,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordUseCase,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UpdateProfileUseCase,
)
from app.modules.trace.application.use_cases.get_trace_by_line_range import (
    GetTraceByLineRangeUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_canonical_snapshot import (
    GetTraceForCanonicalSnapshotUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_entity import (
    GetTraceForEntityUseCase,
)
from app.modules.trace.application.use_cases.get_trace_for_source_snapshot import (
    GetTraceForSourceSnapshotUseCase,
)

_STREAMLIT_LOOP: asyncio.AbstractEventLoop | None = None
_STREAMLIT_LOOP_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def get_container() -> AppContainer:
    return create_di_container()


def _start_streamlit_loop() -> asyncio.AbstractEventLoop:
    global _STREAMLIT_LOOP
    ready = threading.Event()

    def _loop_runner() -> None:
        global _STREAMLIT_LOOP
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _STREAMLIT_LOOP = loop
        ready.set()
        loop.run_forever()

    thread = threading.Thread(
        target=_loop_runner,
        daemon=True,
        name="streamlit-async-loop",
    )
    thread.start()
    ready.wait()
    assert _STREAMLIT_LOOP is not None
    return _STREAMLIT_LOOP


def _get_streamlit_loop() -> asyncio.AbstractEventLoop:
    global _STREAMLIT_LOOP
    if _STREAMLIT_LOOP is not None and _STREAMLIT_LOOP.is_running():
        return _STREAMLIT_LOOP

    with _STREAMLIT_LOOP_LOCK:
        if _STREAMLIT_LOOP is not None and _STREAMLIT_LOOP.is_running():
            return _STREAMLIT_LOOP
        return _start_streamlit_loop()


def run_async(coro: Any) -> Any:
    """Run async use-case coroutine from Streamlit's sync rerun context."""
    loop = _get_streamlit_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def _shutdown_streamlit_resources() -> None:
    global _STREAMLIT_LOOP
    loop = _STREAMLIT_LOOP
    if loop is None or not loop.is_running():
        return
    try:
        future = asyncio.run_coroutine_threadsafe(
            get_container().integrations().sdwan_client_provider().close_all(),
            loop,
        )
        future.result(timeout=10)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        _STREAMLIT_LOOP = None


atexit.register(_shutdown_streamlit_resources)


def get_import_vendors() -> GetImportVendorsUseCase:
    return get_container().imports_module().get_import_vendors_use_case()


def get_create_import_source() -> CreateImportSourceUseCase:
    return get_container().imports_module().create_import_source_use_case()


def get_upload_artifact() -> UploadArtifactUseCase:
    return get_container().imports_module().upload_artifact_use_case()


def get_source_snapshots() -> GetSourceSnapshotsUseCase:
    return get_container().imports_module().get_source_snapshots_use_case()


def get_source_artifact() -> GetSourceArtifactUseCase:
    return get_container().imports_module().get_source_artifact_use_case()


def get_canonical_rule_scope() -> GetCanonicalRuleScopeUseCase:
    return get_container().canonical_module().get_canonical_rule_scope_use_case()


def get_canonical_object() -> GetCanonicalObjectUseCase:
    return get_container().canonical_module().get_canonical_object_use_case()


def get_canonical_issues() -> GetCanonicalIssuesUseCase:
    return get_container().canonical_module().get_canonical_issues_use_case()


def get_map_canonical_to_sdwan() -> MapCanonicalToSdwanUseCase:
    return get_container().mapping_module().map_canonical_to_sdwan_use_case()


def get_run_cisco_mapping() -> RunCiscoMappingUseCase:
    return get_container().cisco_asa_module().run_cisco_mapping_use_case()


def get_latest_canonical_snapshot_for_source() -> (
    GetLatestCanonicalSnapshotForSourceUseCase
):
    return get_container().canonical_module().get_latest_snapshot_for_source_use_case()


def get_mapping_scope() -> GetMappingScopeUseCase:
    return get_container().mapping_module().get_mapping_scope_use_case()


def get_mapping_scope_rules() -> GetMappingScopeRulesUseCase:
    return get_container().mapping_module().get_mapping_scope_rules_use_case()


def get_select_entity_candidate() -> SelectEntityCandidateUseCase:
    return get_container().mapping_module().select_entity_candidate_use_case()


def get_select_sdwan_entity_directly() -> SelectSdwanEntityDirectlyUseCase:
    return get_container().mapping_module().select_sdwan_entity_directly_use_case()


def get_select_entity_with_create_on_sdwan() -> SelectEntityWithCreateOnSdwanUseCase:
    return (
        get_container().mapping_module().select_entity_with_create_on_sdwan_use_case()
    )


def get_sdwan_zones() -> GetSdwanZonesUseCase:
    return get_container().mapping_module().get_sdwan_zones_use_case()


def get_sdwan_services() -> GetSdwanServicesUseCase:
    return get_container().mapping_module().get_sdwan_services_use_case()


def get_sdwan_addr_objects() -> GetSdwanAddrObjectsUseCase:
    return get_container().mapping_module().get_sdwan_addr_objects_use_case()


def get_assign_zone_for_scope() -> AssignZoneForScopeUseCase:
    return get_container().mapping_module().assign_zone_for_scope_use_case()


def get_auto_select_entities_with_create() -> (
    AutoSelectEntitiesWithCreateForScopeUseCase
):
    return get_container().mapping_module().auto_select_entities_with_create_use_case()


def get_mapping_scopes() -> GetMappingScopesUseCase:
    return get_container().mapping_module().get_mapping_scopes_use_case()


def get_sdwan_targets() -> GetSdwanTargetsUseCase:
    return get_container().mapping_module().get_sdwan_targets_use_case()


def get_discover_allowed_vpcs() -> DiscoverAllowedVpcsUseCase:
    return get_container().mapping_module().discover_allowed_vpcs_use_case()


def get_report_headers() -> GetReportHeadersUseCase:
    return get_container().reports_module().get_report_headers_use_case()


def get_generate_report_pdf() -> GenerateReportPdfUseCase:
    return get_container().reports_module().generate_report_pdf_use_case()


def get_report_rules() -> GetReportRulesUseCase:
    return get_container().reports_module().get_report_rules_use_case()


def get_csp_profiles() -> ListProfilesUseCase:
    return get_container().settings_module().csp_profiles().list_profiles_use_case()


def get_create_csp_profile() -> CreateProfileUseCase:
    return get_container().settings_module().csp_profiles().create_profile_use_case()


def get_csp_profile() -> GetProfileUseCase:
    return get_container().settings_module().csp_profiles().get_profile_use_case()


def get_update_csp_profile() -> UpdateProfileUseCase:
    return get_container().settings_module().csp_profiles().update_profile_use_case()


def get_delete_csp_profile() -> DeleteProfileUseCase:
    return get_container().settings_module().csp_profiles().delete_profile_use_case()


def get_remove_csp_profile_password() -> RemoveProfilePasswordUseCase:
    return (
        get_container()
        .settings_module()
        .csp_profiles()
        .remove_profile_password_use_case()
    )


def get_test_csp_profile_connection() -> TestProfileConnectionUseCase:
    return (
        get_container()
        .settings_module()
        .csp_profiles()
        .test_profile_connection_use_case()
    )


def get_change_profile_active_status() -> ChangeProfileActiveStatusUseCase:
    return (
        get_container()
        .settings_module()
        .csp_profiles()
        .change_profile_active_status_use_case()
    )


def get_mapping_scope_rules_projection() -> GetMappingScopeRulesProjectionUseCase:
    return (
        get_container().mapping_module().get_mapping_scope_rules_projection_use_case()
    )


def get_mapping_entity_result_details() -> GetMappingEntityResultDetailsUseCase:
    return get_container().mapping_module().get_mapping_entity_result_details_use_case()


def get_prepare_execute_plan() -> PrepareExecutePlanUseCase:
    return get_container().execute_module().prepare_execute_plan_use_case()


def get_push_execute_plan_rules() -> PushExecutePlanRulesUseCase:
    return get_container().execute_module().push_execute_plan_rules_use_case()


def get_execute_plan_rules() -> GetExecutePlanRulesUseCase:
    return get_container().execute_module().get_execute_plan_rules_use_case()


def get_sdwan_rules() -> GetSdwanRulesUseCase:
    return get_container().execute_module().get_sdwan_rules_use_case()


def get_trace_for_canonical_snapshot() -> GetTraceForCanonicalSnapshotUseCase:
    return get_container().trace_module().get_trace_for_canonical_snapshot_use_case()


def get_trace_for_source_snapshot() -> GetTraceForSourceSnapshotUseCase:
    return get_container().trace_module().get_trace_for_source_snapshot_use_case()


def get_trace_for_entity() -> GetTraceForEntityUseCase:
    return get_container().trace_module().get_trace_for_entity_use_case()


def get_trace_by_line_range() -> GetTraceByLineRangeUseCase:
    return get_container().trace_module().get_trace_by_line_range_use_case()
