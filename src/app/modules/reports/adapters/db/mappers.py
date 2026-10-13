from app.modules.reports.adapters.db.models import ReportModel, ReportRuleModel
from app.modules.reports.domain.entities import Report, ReportRule
from app.modules.reports.domain.enums import (
    ReportRuleAction,
    ReportRuleMigrationResult,
)
from app.modules.reports.domain.value_objects import ReportEnvironmentSnapshot


def report_to_model(entity: Report) -> ReportModel:
    return ReportModel(
        id=entity.id,
        title=entity.title,
        created_at=entity.created_at,
        csp_profile_id=entity.csp_profile_id,
        commit_id=entity.commit_id,
        project_name=entity.environment.project_name,
        vpc_id=entity.environment.vpc_id,
        target_name=entity.environment.target_name,
        target_id=entity.environment.target_id,
    )


def report_rule_to_model(entity: ReportRule) -> ReportRuleModel:
    return ReportRuleModel(
        id=entity.id,
        report_id=entity.report_id,
        policy_name=entity.policy_name,
        action=entity.action.value,
        priority=entity.priority,
        src_zone_names=list(entity.src_zone_names),
        dst_zone_names=list(entity.dst_zone_names),
        src_addr_values=list(entity.src_addr_values),
        dst_addr_values=list(entity.dst_addr_values),
        service_values=list(entity.service_values),
        migration_result=entity.migration_result.value,
        reason=entity.reason,
    )


def report_from_model(
    model: ReportModel,
    *,
    rules: tuple[ReportRule, ...] | None = None,
) -> Report:
    return Report(
        id=model.id,
        title=model.title,
        created_at=model.created_at,
        csp_profile_id=model.csp_profile_id,
        commit_id=model.commit_id,
        environment=ReportEnvironmentSnapshot(
            project_name=model.project_name,
            vpc_id=model.vpc_id,
            target_name=model.target_name,
            target_id=model.target_id,
        ),
        rules=rules,
    )


def report_rule_from_model(model: ReportRuleModel) -> ReportRule:
    return ReportRule(
        id=model.id,
        report_id=model.report_id,
        policy_name=model.policy_name,
        action=ReportRuleAction(model.action),
        priority=model.priority,
        src_zone_names=tuple(model.src_zone_names),
        dst_zone_names=tuple(model.dst_zone_names),
        src_addr_values=tuple(model.src_addr_values),
        dst_addr_values=tuple(model.dst_addr_values),
        service_values=tuple(model.service_values),
        migration_result=ReportRuleMigrationResult(model.migration_result),
        reason=model.reason,
    )
