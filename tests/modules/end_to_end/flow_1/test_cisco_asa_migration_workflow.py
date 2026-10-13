"""Positive backend workflow from Cisco ASA upload to SD-WAN policy push."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.querying import Pagination
from app.di.container import AppContainer
from app.modules.canonical.application.use_cases.get_canonical_rules import (
    GetCanonicalRulesQuery,
)
from app.modules.execute.application.use_cases.get_execute_plan_rules import (
    GetExecutePlanRulesQuery,
)
from app.modules.execute.application.use_cases.prepare_execute_plan import (
    PrepareExecutePlanCommand,
)
from app.modules.execute.application.use_cases.push_execute_plan_rules import (
    PushExecutePlanRulesCommand,
)
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.imports.application.use_cases.create_import_source import (
    CreateImportSourceCommand,
)
from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactCommand,
)
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingCommand,
)
from app.modules.mapping.application.get_mapping_scope_rules import (
    GetMappingScopeRulesQuery,
)
from app.modules.mapping.application.map_canonical_to_sdwan import (
    MapCanonicalToSdwanCommand,
)
from app.modules.mapping.application.select_entity_candidate import (
    SelectEntityCandidateCommand,
)
from app.modules.mapping.application.select_sdwan_entity_directly import (
    SelectSdwanEntityDirectlyCommand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRulesPriority,
)
from app.modules.reports.application.use_cases.get_report_headers import (
    GetReportHeadersQuery,
)
from app.modules.reports.application.use_cases.get_report_rules import (
    GetReportRulesQuery,
)
from app.modules.reports.domain.enums import ReportRuleMigrationResult
from app.modules.reports.ports.report_repository import ReportHeaderFilters
from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionCommand as ConnectionCommand,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
)
from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from tests.modules.end_to_end.flow_1.fake_sdwan import FakeSDWANState

_ARTIFACT_PATH = Path(__file__).parent / "fixtures" / "cisco_asa_migration.cfg"


@pytest.mark.asyncio
async def test_cisco_asa_migration_workflow_resolves_mapping_and_pushes_only_new_rules(
    backend_container: AppContainer,
    combined_client_pem: str,
    sdwan_state: FakeSDWANState,
) -> None:
    """Run the production migration workflow through real backend composition."""

    # 1. Create an SD-WAN connection profile and verify its allowed VPCs.
    csp_profiles = backend_container.settings_module().csp_profiles()
    profile = await csp_profiles.create_profile_use_case().execute(
        CreateProfileCommand(
            name="Flow 1 CSP profile",
            base_url="https://fake-sdwan.flow-1.test",
            username="flow-1-operator",
            password="flow-1-password",
            certificate_bundle=CertificateBundleDTO(
                data=combined_client_pem.encode("utf-8"),
                format=CertificateBundleFormat.PEM,
                passphrase=None,
            ),
        )
    )

    connection = await csp_profiles.test_profile_connection_use_case().execute(
        ConnectionCommand(profile_id=profile.id)
    )
    assert connection.reachable is True
    assert connection.authenticated is True
    assert [vpc.vpc_id for vpc in connection.allowed_vpcs] == ["vpc-flow-1"]

    # 2. Upload the vendor artifact and turn it into canonical data with trace.
    imports_module = backend_container.imports_module()
    source = await imports_module.create_import_source_use_case().execute(
        CreateImportSourceCommand(
            vendor_code="cisco_asa",
            name="flow-1-cisco-asa",
        )
    )
    upload = await imports_module.upload_artifact_use_case().execute(
        UploadArtifactCommand(
            source_id=source.source.id,
            file_name=_ARTIFACT_PATH.name,
            raw_text=_ARTIFACT_PATH.read_text(),
            uploaded_by="flow_1",
            source_format="cisco_asa",
        )
    )
    canonical = (
        await backend_container.cisco_asa_module()
        .run_cisco_mapping_use_case()
        .execute(RunCiscoMappingCommand(source_snapshot_id=upload.snapshot.id))
    )
    assert canonical.trace_records_written > 0

    canonical_rules = (
        await backend_container.canonical_module()
        .get_canonical_rules_use_case()
        .execute(
            GetCanonicalRulesQuery(
                canonical_snapshot_id=canonical.canonical_snapshot_id,
                pagination=Pagination(limit=10, offset=0),
            )
        )
    )
    assert canonical_rules.pagination.total == 3

    # 3. Map selected canonical policies against the profile/VPC/target catalog.
    mapping = (
        await backend_container.mapping_module()
        .map_canonical_to_sdwan_use_case()
        .execute(
            MapCanonicalToSdwanCommand(
                mapping_scope_title="flow-1",
                csp_profile_id=profile.id,
                vpc_id="vpc-flow-1",
                sdwan_target_id="device-flow-1",
                rules_priority=MappingScopeRulesPriority.LOCAL,
                canonical_snapshot_id=canonical.canonical_snapshot_id,
                canonical_rules_ids=[rule.id for rule in canonical_rules.rules],
            )
        )
    )
    assert mapping.mapped_rules_count == 3
    assert mapping.mapping_results_summary.ambiguous == 1
    assert mapping.mapping_results_summary.unresolved == 1

    # 4. Inspect and resolve the intentionally ambiguous and unresolved objects.
    mapping_module = backend_container.mapping_module()
    before_resolution = await mapping_module.get_mapping_scope_rules_use_case().execute(
        GetMappingScopeRulesQuery(mapping_scope_id=mapping.mapping_scope_id)
    )
    ambiguous = next(
        result
        for result in before_resolution.mapping_results
        if result.result_status == MappingResultStatus.AMBIGUOUS
    )
    unresolved = next(
        result
        for result in before_resolution.mapping_results
        if result.result_status == MappingResultStatus.UNRESOLVED
    )
    assert ambiguous.entity_type == MappingEntityType.ADDR
    assert unresolved.entity_type == MappingEntityType.ADDR
    assert ambiguous.candidates is not None

    await mapping_module.select_entity_candidate_use_case().execute(
        SelectEntityCandidateCommand(
            mapping_scope_id=mapping.mapping_scope_id,
            mapping_entity_result_id=ambiguous.id,
            candidate_id=ambiguous.candidates[0].id,
        )
    )
    await mapping_module.select_sdwan_entity_directly_use_case().execute(
        SelectSdwanEntityDirectlyCommand(
            mapping_scope_id=mapping.mapping_scope_id,
            mapping_result_id=unresolved.id,
            sdwan_entity_id=104,
        )
    )

    after_resolution = await mapping_module.get_mapping_scope_rules_use_case().execute(
        GetMappingScopeRulesQuery(mapping_scope_id=mapping.mapping_scope_id)
    )
    assert {result.result_status for result in after_resolution.mapping_results} == {
        MappingResultStatus.MATCHED
    }

    # 5. Prepare a plan: one exact duplicate, one covered rule, and one new rule.
    execute_module = backend_container.execute_module()
    execute_plan = await execute_module.prepare_execute_plan_use_case().execute(
        PrepareExecutePlanCommand(mapping_scope_id=mapping.mapping_scope_id)
    )
    assert (
        execute_plan.new_rules,
        execute_plan.matched_rules,
        execute_plan.covered_rules,
        execute_plan.errors_through_match,
    ) == (1, 1, 1, 0)

    plan_rules = await execute_module.get_execute_plan_rules_use_case().execute(
        GetExecutePlanRulesQuery(execute_plan_id=execute_plan.id)
    )
    assert {rule.match_status for rule in plan_rules.plan_rules} == {
        RuleMatchStatus.NEW,
        RuleMatchStatus.EXACT_MATCH,
        RuleMatchStatus.COVERED_MATCH,
    }

    # 6. Push only the new policy and observe the resulting SD-WAN policy.
    pushed = await execute_module.push_execute_plan_rules_use_case().execute(
        PushExecutePlanRulesCommand(execute_plan_id=execute_plan.id)
    )
    assert [rule.policy_id for rule in pushed.rules] == [900]
    assert pushed.commit_info.commit_id == 1
    assert len(sdwan_state.commits) == 1
    assert len(sdwan_state.created_policy_requests) == 1
    assert sdwan_state.created_policy_requests[0].service == [12]
    assert all(
        profile_id == profile.id for profile_id, _ in sdwan_state.client_connections
    )
    assert {vpc_id for _, vpc_id in sdwan_state.client_connections} == {
        None,
        "vpc-flow-1",
    }

    # 7. Read the immutable report through its public application API.
    reports_module = backend_container.reports_module()
    report_headers = await reports_module.get_report_headers_use_case().execute(
        GetReportHeadersQuery(
            filters=ReportHeaderFilters(csp_profile_id=profile.id),
            pagination=Pagination(limit=10, offset=0),
        )
    )
    assert report_headers.pagination.total == 1
    report_header = report_headers.reports[0]
    assert report_header.title.startswith("flow-1 ")
    assert report_header.csp_profile.id == profile.id
    assert report_header.csp_profile.name == "Flow 1 CSP profile"
    assert report_header.csp_profile.base_url == "https://fake-sdwan.flow-1.test"
    assert report_header.project_name == "Flow 1 project"
    assert report_header.vpc_id == "vpc-flow-1"
    assert report_header.target_name == "Flow 1 device"
    assert report_header.target_id == "device-flow-1"

    report_rules = await reports_module.get_report_rules_use_case().execute(
        GetReportRulesQuery(
            report_id=report_header.id,
            pagination=Pagination(limit=10, offset=0),
        )
    )
    assert report_rules.pagination.total == 3
    assert [rule.priority for rule in report_rules.rules] == [1, 2, 3]
    assert {rule.migration_result for rule in report_rules.rules} == {
        ReportRuleMigrationResult.PUSHED,
        ReportRuleMigrationResult.MATCHED,
        ReportRuleMigrationResult.COVERED,
    }

    # 8. The persisted PUSHED snapshot matches the policy sent to SD-WAN.
    pushed_plan_rule = next(
        rule
        for rule in plan_rules.plan_rules
        if rule.match_status == RuleMatchStatus.NEW
    )
    pushed_report_rule = next(
        rule
        for rule in report_rules.rules
        if rule.migration_result == ReportRuleMigrationResult.PUSHED
    )
    assert pushed_report_rule.policy_name == pushed.rules[0].name
    assert pushed_report_rule.action.value == pushed.rules[0].action.value
    assert pushed_report_rule.priority == pushed_plan_rule.priority
    assert pushed_report_rule.src_zone_names == ("outside",)
    assert pushed_report_rule.dst_zone_names == ("inside",)
    assert pushed_report_rule.src_addr_values == ("10.0.0.1",)
    assert pushed_report_rule.dst_addr_values == ("10.0.0.4",)
    assert pushed_report_rule.service_values == ("tcp/22",)
    assert pushed_report_rule.reason == "Success"
