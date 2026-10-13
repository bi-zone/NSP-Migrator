from __future__ import annotations

from uuid import uuid4

from app.modules.reports.adapters.db.mappers import (
    report_from_model,
    report_rule_from_model,
    report_rule_to_model,
    report_to_model,
)
from app.modules.reports.domain.entities import Report
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.value_objects import (
    ReportEnvironmentSnapshot,
    ReportRuleSnapshot,
)


def _report() -> Report:
    return Report.create(
        scope_title="Branch migration",
        csp_profile_id=uuid4(),
        commit_id=42,
        environment=ReportEnvironmentSnapshot(
            project_name="Firewall migration",
            vpc_id="vpc-1",
            target_name="Branch gateway",
            target_id="target-1",
        ),
        rule_snapshots=(
            ReportRuleSnapshot(
                policy_name="allow-web",
                action=ReportRuleAction.ACCEPT,
                priority=10,
                src_zone_names=("LAN",),
                dst_zone_names=("WAN",),
                src_addr_values=("10.10.0.0/24",),
                dst_addr_values=(),
                service_values=("tcp/443",),
                migration_result=ReportRuleMigrationResult.PUSHED,
                reason="Success",
            ),
        ),
    )


def test_report_mapper_roundtrip_preserves_header_snapshot() -> None:
    entity = _report()

    restored = report_from_model(report_to_model(entity))

    assert restored.id == entity.id
    assert restored.title == entity.title
    assert restored.created_at == entity.created_at
    assert restored.csp_profile_id == entity.csp_profile_id
    assert restored.commit_id == entity.commit_id
    assert restored.environment == entity.environment
    assert restored.rules is None


def test_report_rule_mapper_uses_json_lists_and_restores_domain_tuples() -> None:
    report = _report()
    assert report.rules is not None
    rule = report.rules[0]

    model = report_rule_to_model(rule)
    restored = report_rule_from_model(model)

    assert model.src_zone_names == ["LAN"]
    assert model.dst_addr_values == []
    assert model.action == "ACCEPT"
    assert model.migration_result == "PUSHED"
    assert restored == rule
