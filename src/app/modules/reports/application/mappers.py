"""Application projections for Reports read use cases."""

from app.modules.reports.application.dto import ReportHeaderDTO, ReportRuleDTO
from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.ports.csp_profile_headers_reader import CSPProfileHeaderDTO


def report_to_header_dto(
    report: Report,
    *,
    csp_profile: CSPProfileHeaderDTO,
) -> ReportHeaderDTO:
    """Project an immutable Report aggregate into its list-header shape."""
    return ReportHeaderDTO(
        id=report.id,
        title=report.title,
        csp_profile=csp_profile,
        project_name=report.environment.project_name,
        vpc_id=report.environment.vpc_id,
        target_name=report.environment.target_name,
        target_id=report.environment.target_id,
        created_at=report.created_at,
    )


def report_rule_to_dto(rule: ReportRule) -> ReportRuleDTO:
    """Project one immutable saved policy outcome into its detail-list shape."""
    return ReportRuleDTO(
        policy_name=rule.policy_name,
        action=rule.action,
        priority=rule.priority,
        src_zone_names=rule.src_zone_names,
        dst_zone_names=rule.dst_zone_names,
        src_addr_values=rule.src_addr_values,
        dst_addr_values=rule.dst_addr_values,
        service_values=rule.service_values,
        migration_result=rule.migration_result,
        reason=rule.reason,
    )
