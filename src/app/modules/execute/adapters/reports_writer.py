from uuid import UUID

from app.modules.execute.domain.entities import ExecutePlanRule
from app.modules.execute.domain.enums import RuleMatchStatus, RulePushStatus
from app.modules.execute.ports.reports_writer import ReportsWriterPort
from app.modules.reports.application.use_cases.save_report import (
    SaveReportCommand,
    SaveReportRuleCommand,
    SaveReportUseCase,
)
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)


class ExecuteReportsWriter(ReportsWriterPort):
    """Translate Execute plan outcomes into the Reports write command."""

    def __init__(self, save_report_use_case: SaveReportUseCase) -> None:
        self._save_report_use_case = save_report_use_case

    async def save_report(
        self,
        *,
        scope_title: str,
        csp_profile_id: UUID,
        vpc_id: str,
        target_id: str,
        commit_id: int,
        plan_rules: list[ExecutePlanRule],
    ) -> None:
        await self._save_report_use_case.execute(
            SaveReportCommand(
                scope_title=scope_title,
                csp_profile_id=csp_profile_id,
                vpc_id=vpc_id,
                target_id=target_id,
                commit_id=commit_id,
                rules=tuple(self._to_rule_command(rule) for rule in plan_rules),
            )
        )

    @staticmethod
    def _to_rule_command(rule: ExecutePlanRule) -> SaveReportRuleCommand:
        migration_result, reason = _report_rule_status_outcome(rule)
        return SaveReportRuleCommand(
            policy_name=rule.draft.name,
            action=ReportRuleAction(rule.draft.action),
            priority=rule.priority,
            src_zone_ids=tuple(rule.draft.src_zones),
            dst_zone_ids=tuple(rule.draft.dst_zones),
            src_addr_object_ids=tuple(rule.draft.src_addr_objects),
            dst_addr_object_ids=tuple(rule.draft.dst_addr_objects),
            service_ids=tuple(rule.draft.services),
            migration_result=migration_result,
            reason=reason,
        )


def _report_rule_status_outcome(
    rule: ExecutePlanRule,
) -> tuple[ReportRuleMigrationResult, str]:
    match rule.match_status:
        case RuleMatchStatus.EXACT_MATCH:
            return ReportRuleMigrationResult.MATCHED, rule.match_info
        case RuleMatchStatus.COVERED_MATCH:
            return ReportRuleMigrationResult.COVERED, rule.match_info
        case RuleMatchStatus.MATCH_ERROR:
            return ReportRuleMigrationResult.ERROR, rule.match_info
        case RuleMatchStatus.NEW:
            if rule.push_status == RulePushStatus.SUCCEEDED:
                return ReportRuleMigrationResult.PUSHED, "Success"
            if rule.push_status == RulePushStatus.FAILED:
                return (
                    ReportRuleMigrationResult.FAILED,
                    rule.push_error or "Push failed",
                )
            return ReportRuleMigrationResult.ERROR, "Push outcome was not recorded"
