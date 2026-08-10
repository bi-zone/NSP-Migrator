from app.core.mappers import IBaseDomainModelMapper
from app.modules.execute.adapters.db.models import (
    ExecutePlanModel,
    ExecutePlanRuleModel,
)
from app.modules.execute.domain.entities import (
    ExecutePlan,
    ExecutePlanRule,
)
from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.domain.value_objects import PlannedRuleDraft


class ExecutePlanDomainModelMapper(
    IBaseDomainModelMapper[ExecutePlan, ExecutePlanModel]
):
    def to_model(self, entity: ExecutePlan) -> ExecutePlanModel:
        return ExecutePlanModel(
            id=entity.id,
            mapping_scope_id=entity.mapping_scope_id,
            created_at=entity.created_at,
        )

    def to_domain(self, model: ExecutePlanModel) -> ExecutePlan:
        return ExecutePlan(
            id=model.id,
            mapping_scope_id=model.mapping_scope_id,
            created_at=model.created_at,
        )


class ExecutePlanRuleDomainModelMapper(
    IBaseDomainModelMapper[ExecutePlanRule, ExecutePlanRuleModel]
):
    def to_model(self, entity: ExecutePlanRule) -> ExecutePlanRuleModel:
        return ExecutePlanRuleModel(
            id=entity.id,
            execute_plan_id=entity.execute_plan_id,
            mapping_scope_rule_id=entity.mapping_scope_rule_id,
            match_status=entity.match_status.value,
            matched_sdwan_rule_id=entity.matched_sdwan_rule_id,
            match_info=entity.match_info,
            draft_json=entity.draft.to_dict(),
        )

    def to_domain(self, model: ExecutePlanRuleModel) -> ExecutePlanRule:
        return ExecutePlanRule(
            id=model.id,
            execute_plan_id=model.execute_plan_id,
            mapping_scope_rule_id=model.mapping_scope_rule_id,
            match_status=RuleMatchStatus(model.match_status),
            matched_sdwan_rule_id=model.matched_sdwan_rule_id,
            match_info=model.match_info,
            draft=PlannedRuleDraft.from_dict(model.draft_json),
        )
