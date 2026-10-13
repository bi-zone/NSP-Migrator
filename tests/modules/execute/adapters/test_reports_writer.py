from uuid import UUID, uuid4

import pytest

from app.modules.execute.adapters.reports_writer import ExecuteReportsWriter
from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import (
    RuleMatchStatus,
    SdwanRuleAction,
)
from app.modules.execute.domain.value_objects import PlannedRuleDraft
from app.modules.reports.application.use_cases.save_report import SaveReportCommand
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)


class _SaveReportUseCase:
    def __init__(self) -> None:
        self.commands: list[SaveReportCommand] = []

    async def execute(self, command: SaveReportCommand) -> None:
        self.commands.append(command)


def _rule(
    *,
    execute_plan_id: UUID,
    name: str,
    priority: int,
    match_status: RuleMatchStatus,
    match_info: str,
) -> ExecutePlanRule:
    return ExecutePlanRule.create(
        execute_plan_id=execute_plan_id,
        mapping_scope_rule_id=uuid4(),
        priority=priority,
        draft=PlannedRuleDraft(
            name=name,
            action=SdwanRuleAction.ACCEPT,
            src_zones=[1],
            dst_zones=[2],
            src_addr_objects=[10],
            dst_addr_objects=[20],
            services=[30],
        ),
        matched_sdwan_rule_id=None,
        match_status=match_status,
        match_info=match_info,
    )


@pytest.mark.asyncio
async def test_writer_translates_every_execute_outcome_into_report_snapshot() -> None:
    execute_plan_id = uuid4()
    pushed_rule = _rule(
        execute_plan_id=execute_plan_id,
        name="pushed",
        priority=10,
        match_status=RuleMatchStatus.NEW,
        match_info="New policy",
    ).mark_push_succeeded(901)
    failed_rule = _rule(
        execute_plan_id=execute_plan_id,
        name="failed",
        priority=20,
        match_status=RuleMatchStatus.NEW,
        match_info="New policy",
    ).mark_push_failed("SD-WAN rejected policy: destination is invalid")
    matched_rule = _rule(
        execute_plan_id=execute_plan_id,
        name="matched",
        priority=30,
        match_status=RuleMatchStatus.EXACT_MATCH,
        match_info="Exact match with SD-WAN policy 501",
    )
    covered_rule = _rule(
        execute_plan_id=execute_plan_id,
        name="covered",
        priority=40,
        match_status=RuleMatchStatus.COVERED_MATCH,
        match_info="Covered by SD-WAN policy 502",
    )
    error_rule = _rule(
        execute_plan_id=execute_plan_id,
        name="validation-error",
        priority=50,
        match_status=RuleMatchStatus.MATCH_ERROR,
        match_info="Validation failed: service value is unavailable",
    )
    save_report_use_case = _SaveReportUseCase()
    writer = ExecuteReportsWriter(save_report_use_case)  # type: ignore[arg-type]
    profile_id = uuid4()

    await writer.save_report(
        scope_title="Branch migration",
        csp_profile_id=profile_id,
        vpc_id="vpc-1",
        target_id="target-1",
        commit_id=42,
        plan_rules=[
            pushed_rule,
            failed_rule,
            matched_rule,
            covered_rule,
            error_rule,
        ],
    )

    assert len(save_report_use_case.commands) == 1
    command = save_report_use_case.commands[0]
    assert (
        command.scope_title,
        command.csp_profile_id,
        command.vpc_id,
        command.target_id,
        command.commit_id,
    ) == ("Branch migration", profile_id, "vpc-1", "target-1", 42)
    assert [rule.policy_name for rule in command.rules] == [
        "pushed",
        "failed",
        "matched",
        "covered",
        "validation-error",
    ]
    assert [rule.priority for rule in command.rules] == [10, 20, 30, 40, 50]
    assert all(rule.action is ReportRuleAction.ACCEPT for rule in command.rules)
    assert all(rule.src_zone_ids == (1,) for rule in command.rules)
    assert all(rule.dst_zone_ids == (2,) for rule in command.rules)
    assert all(rule.src_addr_object_ids == (10,) for rule in command.rules)
    assert all(rule.dst_addr_object_ids == (20,) for rule in command.rules)
    assert all(rule.service_ids == (30,) for rule in command.rules)
    assert [(rule.migration_result, rule.reason) for rule in command.rules] == [
        (ReportRuleMigrationResult.PUSHED, "Success"),
        (
            ReportRuleMigrationResult.FAILED,
            "SD-WAN rejected policy: destination is invalid",
        ),
        (ReportRuleMigrationResult.MATCHED, "Exact match with SD-WAN policy 501"),
        (ReportRuleMigrationResult.COVERED, "Covered by SD-WAN policy 502"),
        (
            ReportRuleMigrationResult.ERROR,
            "Validation failed: service value is unavailable",
        ),
    ]
