from sqlalchemy import inspect
from sqlalchemy.orm import NO_VALUE

from app.modules.mapping.adapters.db.models import (
    MappingEntityCandidateModel,
    MappingEntityResultModel,
    MappingScopeModel,
    MappingScopeRuleModel,
    MappingScopeRuleOperandModel,
)
from app.modules.mapping.domain.entities import (
    MappingEntityCandidate,
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleAction,
    MappingScopeRuleOperandRole,
    SdwanObjectSelectionMethod,
)


class MappingScopeRuleOperandMapper:
    """
    Converts mapping_scope_rule_operand ORM model to domain model and back.
    """

    @staticmethod
    def to_domain(model: MappingScopeRuleOperandModel) -> MappingScopeRuleOperand:
        return MappingScopeRuleOperand(
            id=model.id,
            mapping_scope_rule_id=model.mapping_scope_rule_id,
            role=MappingScopeRuleOperandRole(model.role),
            mapping_entity_result_id=model.mapping_entity_result_id,
        )

    @staticmethod
    def to_model(domain: MappingScopeRuleOperand) -> MappingScopeRuleOperandModel:
        return MappingScopeRuleOperandModel(
            id=domain.id,
            mapping_scope_rule_id=domain.mapping_scope_rule_id,
            role=domain.role,
            mapping_entity_result_id=domain.mapping_entity_result_id,
        )


class MappingScopeRuleMapper:
    """
    Converts mapping_scope_rule ORM model to domain model and back.
    """

    operand_mapper = MappingScopeRuleOperandMapper()

    @classmethod
    def to_domain(cls, model: MappingScopeRuleModel) -> MappingScopeRule:

        if inspect(model).attrs.operands.loaded_value is NO_VALUE:
            operands = None
        else:
            operands = [cls.operand_mapper.to_domain(c) for c in model.operands]

        return MappingScopeRule(
            id=model.id,
            mapping_scope_id=model.mapping_scope_id,
            canonical_rule_id=model.canonical_rule_id,
            name=model.name,
            action=MappingScopeRuleAction(model.action),
            operands=operands,
        )

    @classmethod
    def to_model(cls, domain: MappingScopeRule) -> MappingScopeRuleModel:
        return MappingScopeRuleModel(
            id=domain.id,
            mapping_scope_id=domain.mapping_scope_id,
            canonical_rule_id=domain.canonical_rule_id,
            name=domain.name,
            action=domain.action,
            operands=(
                [cls.operand_mapper.to_model(op) for op in domain.operands]
                if domain.operands
                else None
            ),
        )


class MappingScopeMapper:
    """
    Converts mapping scope aggregate between ORM and domain layers.

    Rules are included only when repository explicitly preloaded them.
    """

    rule_mapper = MappingScopeRuleMapper()

    @classmethod
    def to_domain(cls, model: MappingScopeModel) -> MappingScope:

        if inspect(model).attrs.rules.loaded_value is NO_VALUE:
            rules = None
        else:
            rules = [cls.rule_mapper.to_domain(c) for c in model.rules]

        return MappingScope(
            id=model.id,
            title=model.title,
            canonical_snapshot_id=model.canonical_snapshot_id,
            sdwan_target_id=model.sdwan_target_id,
            created_at=model.created_at,
            rules=rules,
        )

    @classmethod
    def to_model(cls, domain: MappingScope) -> MappingScopeModel:
        model = MappingScopeModel(
            id=domain.id,
            title=domain.title,
            canonical_snapshot_id=domain.canonical_snapshot_id,
            sdwan_target_id=domain.sdwan_target_id,
            created_at=domain.created_at,
        )

        if domain.rules is not None:
            model.rules = [cls.rule_mapper.to_model(rule) for rule in domain.rules]

        return model


class MappingEntityCandidateMapper:
    """
    Converts mapping entity candidate between ORM and domain layers.
    """

    @staticmethod
    def to_domain(model: MappingEntityCandidateModel) -> MappingEntityCandidate:
        return MappingEntityCandidate(
            id=model.id,
            result_id=model.result_id,
            rank=model.rank,
            score=model.score,
            strategy=CandidateMatchStrategy(model.strategy),
            sdwan_entity_id=model.sdwan_entity_id,
        )

    @staticmethod
    def to_model(domain: MappingEntityCandidate) -> MappingEntityCandidateModel:
        return MappingEntityCandidateModel(
            id=domain.id,
            result_id=domain.result_id,
            rank=domain.rank,
            score=domain.score,
            strategy=domain.strategy.value,
            sdwan_entity_id=domain.sdwan_entity_id,
        )


class MappingEntityResultMapper:
    """
    Converts generic mapping result between ORM and domain layers.

    This mapper does not validate that canonical_object belongs to ADDR or
    SERVICE family. That invariant belongs to application service/canonical
    reader because canonical object family lives in canonical module.
    """

    candidate_mapper = MappingEntityCandidateMapper()

    @classmethod
    def to_domain(cls, model: MappingEntityResultModel) -> MappingEntityResult:

        if inspect(model).attrs.candidates.loaded_value is NO_VALUE:
            candidates = None
        else:
            candidates = [cls.candidate_mapper.to_domain(c) for c in model.candidates]

        return MappingEntityResult(
            id=model.id,
            mapping_scope_id=model.mapping_scope_id,
            entity_type=MappingEntityType(model.entity_type),
            canonical_zone_id=model.canonical_zone_id,
            canonical_object_id=model.canonical_object_id,
            result_status=MappingResultStatus(model.result_status),
            selection_method=(
                SdwanObjectSelectionMethod(model.selection_method)
                if model.selection_method is not None
                else None
            ),
            selected_sdwan_entity_id=model.selected_sdwan_entity_id,
            created_at=model.created_at,
            candidates=candidates,
        )

    @classmethod
    def to_model(cls, domain: MappingEntityResult) -> MappingEntityResultModel:
        model = MappingEntityResultModel(
            id=domain.id,
            mapping_scope_id=domain.mapping_scope_id,
            entity_type=domain.entity_type.value,
            canonical_zone_id=domain.canonical_zone_id,
            canonical_object_id=domain.canonical_object_id,
            result_status=domain.result_status.value,
            selection_method=(
                domain.selection_method.value
                if domain.selection_method is not None
                else None
            ),
            selected_sdwan_entity_id=domain.selected_sdwan_entity_id,
            created_at=domain.created_at,
        )

        if domain.candidates is not None:
            model.candidates = [
                cls.candidate_mapper.to_model(candidate)
                for candidate in domain.candidates
            ]

        return model
