from datetime import UTC, datetime
from uuid import uuid4

from app.modules.reports.application.services.report_pdf_builder import ReportPdfBuilder
from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.value_objects import ReportEnvironmentSnapshot
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO


def test_report_pdf_builder_returns_pdf_with_report_snapshot_values() -> None:
    report_id = uuid4()
    profile_id = uuid4()
    report = Report(
        id=report_id,
        title="Branch migration",
        created_at=datetime(2026, 9, 14, 10, tzinfo=UTC),
        csp_profile_id=profile_id,
        commit_id=42,
        environment=ReportEnvironmentSnapshot(
            project_name="Firewall migration",
            vpc_id="vpc-1",
            target_name="Branch gateway",
            target_id="target-1",
        ),
        rules=(
            ReportRule(
                id=uuid4(),
                report_id=report_id,
                policy_name="allow-web",
                action=ReportRuleAction.ACCEPT,
                priority=10,
                src_zone_names=("LAN",),
                dst_zone_names=("WAN",),
                src_addr_values=("10.10.0.0/24",),
                dst_addr_values=("203.0.113.10",),
                service_values=("tcp/443",),
                migration_result=ReportRuleMigrationResult.PUSHED,
                reason="Success",
            ),
        ),
    )

    content = ReportPdfBuilder().build(
        report=report,
        csp_profile=CSPProfileHeaderDTO(
            id=profile_id,
            name="Production",
            base_url="https://example.com",
        ),
    )

    assert content.startswith(b"%PDF")
    assert len(content) > 1_000
