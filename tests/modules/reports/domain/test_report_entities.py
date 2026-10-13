from uuid import uuid4

import pytest

from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.exceptions import ReportsModuleDomainValidationError
from app.modules.reports.domain.value_objects import (
    ReportEnvironmentSnapshot,
    ReportRuleSnapshot,
)


def _environment(**overrides: object) -> ReportEnvironmentSnapshot:
    data: dict[str, object] = {
        "project_name": "Firewall migration",
        "vpc_id": "vpc-1",
        "target_name": "Branch gateway",
        "target_id": "target-1",
    }
    data.update(overrides)
    return ReportEnvironmentSnapshot(**data)  # type: ignore[arg-type]


def _rule_snapshot(**overrides: object) -> ReportRuleSnapshot:
    data: dict[str, object] = {
        "policy_name": "allow-web",
        "action": ReportRuleAction.ACCEPT,
        "priority": 10,
        "src_zone_names": ("LAN",),
        "dst_zone_names": ("WAN",),
        "src_addr_values": ("10.10.0.0/24",),
        "dst_addr_values": ("203.0.113.10",),
        "service_values": ("tcp/443",),
        "migration_result": ReportRuleMigrationResult.PUSHED,
        "reason": "Success",
    }
    data.update(overrides)
    return ReportRuleSnapshot(**data)  # type: ignore[arg-type]


def test_create_report_builds_rule_graph_and_timestamp_title() -> None:
    profile_id = uuid4()
    report = Report.create(
        scope_title="Branch migration",
        csp_profile_id=profile_id,
        environment=_environment(),
        commit_id=42,
        rule_snapshots=(
            _rule_snapshot(),
            _rule_snapshot(
                policy_name="allow-dns",
                priority=20,
                migration_result=ReportRuleMigrationResult.FAILED,
                reason="SD-WAN rejected policy",
            ),
        ),
    )

    assert report.commit_id == 42
    assert report.csp_profile_id == profile_id
    assert report.title == (
        f"Branch migration — {report.created_at.strftime('%d.%m.%Y-%H:%M:%S')}"
    )
    assert report.environment.target_name == "Branch gateway"
    assert report.rules is not None
    assert [rule.policy_name for rule in report.rules] == ["allow-web", "allow-dns"]
    assert all(rule.report_id == report.id for rule in report.rules)
    assert report.rules[0].migration_result == ReportRuleMigrationResult.PUSHED
    assert report.rules[1].reason == "SD-WAN rejected policy"


def test_report_preserves_project_name_and_allows_null_commit_id() -> None:
    report = Report.create(
        scope_title="Branch migration",
        csp_profile_id=uuid4(),
        environment=_environment(project_name="Firewall migration"),
        rule_snapshots=(_rule_snapshot(),),
    )

    assert report.commit_id is None
    assert report.environment.project_name == "Firewall migration"


def test_rule_snapshot_preserves_empty_or_incomplete_policy_data() -> None:
    snapshot = _rule_snapshot(
        policy_name="",
        src_zone_names=(),
        src_addr_values=(),
        dst_addr_values=(),
        service_values=(),
        migration_result=ReportRuleMigrationResult.PUSHED,
        reason="",
    )

    assert snapshot.policy_name == ""
    assert snapshot.src_zone_names == ()
    assert snapshot.src_addr_values == ()
    assert snapshot.reason == ""


def test_report_rule_stores_display_values_without_sdwan_object_identity() -> None:
    report = Report.create(
        scope_title="Branch migration",
        csp_profile_id=uuid4(),
        environment=_environment(),
        rule_snapshots=(_rule_snapshot(),),
    )
    assert report.rules is not None
    rule = report.rules[0]

    assert rule.src_addr_values == ("10.10.0.0/24",)
    assert rule.service_values == ("tcp/443",)
    assert not {
        "src_addr_object_ids",
        "dst_addr_object_ids",
        "service_ids",
        "src_addr_object_names",
        "dst_addr_object_names",
        "service_names",
    } & set(rule.__dataclass_fields__)


def test_report_requires_scope_title_and_at_least_one_rule() -> None:
    with pytest.raises(ReportsModuleDomainValidationError, match="scope_title"):
        Report.create(
            scope_title=" ",
            csp_profile_id=uuid4(),
            environment=_environment(),
            rule_snapshots=(_rule_snapshot(),),
        )

    with pytest.raises(ReportsModuleDomainValidationError, match="at least one"):
        Report.create(
            scope_title="Branch migration",
            csp_profile_id=uuid4(),
            environment=_environment(),
            rule_snapshots=(),
        )


def test_attach_rules_rejects_rule_belonging_to_another_report() -> None:
    report = Report.create(
        scope_title="Branch migration",
        csp_profile_id=uuid4(),
        environment=_environment(),
        rule_snapshots=(_rule_snapshot(),),
    )
    foreign_rule = ReportRule.create(
        report_id=uuid4(),
        snapshot=_rule_snapshot(),
    )

    with pytest.raises(ReportsModuleDomainValidationError, match="belong"):
        report.attach_rules((foreign_rule,))
