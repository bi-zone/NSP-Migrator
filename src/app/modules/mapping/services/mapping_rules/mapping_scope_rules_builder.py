from uuid import UUID

from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScopeRule,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingScopeRuleAction,
    MappingScopeRuleOperandRole,
)
from app.modules.mapping.domain.exceptions import (
    MappingModuleDomainValidationError,
)
from app.modules.mapping.domain.value_objects import (
    MappingScopeRuleOperandPayload,
)
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalRule,
    CanonicalRuleAction,
    CanonicalRuleOperand,
    CanonicalRuleOperandRole,
    CanonicalScopeEntities,
    CanonicalService,
)
from app.modules.mapping.services.mapping_rules.canonical_addr_objs_index import (
    CanonicalAddrObjectIndex,
)
from app.modules.mapping.services.mapping_rules.canonical_services_index import (
    CanonicalServiceIndex,
)
from app.modules.mapping.services.mapping_rules.mapping_results_index import (
    MappingResultsIndex,
)


class MappingScopeRulesBuilder:
    """
    Builds persisted mapped rule skeletons.

    Input:
        - canonical rules with operands;
        - canonical scope entities for group expansion;
        - mapping results built for canonical entities.

    Output:
        - MappingScopeRule list with operands linked to MappingEntityResult.

    Important:
        This builder expands canonical groups into leaf operands.
        Group placeholders are not persisted here because MappingScopeRuleOperand
        must reference MappingEntityResult.
    """

    def build(
        self,
        *,
        mapping_scope_id: UUID,
        canonical_rules: list[CanonicalRule],
        canonical_scope_entities: CanonicalScopeEntities,
        mapping_results: list[MappingEntityResult],
    ) -> list[MappingScopeRule]:
        results_index = MappingResultsIndex(mapping_results)
        addr_index = CanonicalAddrObjectIndex(canonical_scope_entities.addr_objects)
        service_index = CanonicalServiceIndex(canonical_scope_entities.services)

        return [
            MappingScopeRule.create(
                mapping_scope_id=mapping_scope_id,
                canonical_rule_id=rule.id,
                name=rule.name,
                action=self._map_rule_action(rule.action),
                operands_payloads=self._build_rule_operand_payloads(
                    rule=rule,
                    results_index=results_index,
                    addr_index=addr_index,
                    service_index=service_index,
                ),
            )
            for rule in canonical_rules
        ]

    def _build_rule_operand_payloads(
        self,
        *,
        rule: CanonicalRule,
        results_index: MappingResultsIndex,
        addr_index: CanonicalAddrObjectIndex,
        service_index: CanonicalServiceIndex,
    ) -> list[MappingScopeRuleOperandPayload]:
        payloads: list[MappingScopeRuleOperandPayload] = []

        for operand in rule.operands:
            entity_type, canonical_entity_ids = self._resolve_operand_targets(
                operand=operand,
                addr_index=addr_index,
                service_index=service_index,
            )

            for canonical_entity_id in canonical_entity_ids:
                mapping_result: MappingEntityResult | None = results_index.get(
                    entity_type=entity_type,
                    canonical_entity_id=canonical_entity_id,
                )

                if mapping_result is None:
                    raise MappingModuleDomainValidationError(
                        "Mapping result not found for rule operand: "
                        f"rule_id={rule.id}, "
                        f"operand_id={operand.id}, "
                        f"entity_type={entity_type}, "
                        f"canonical_entity_id={canonical_entity_id}"
                    )

                payloads.append(
                    MappingScopeRuleOperandPayload(
                        role=self._map_operand_role(operand.role),
                        mapping_entity_result_id=mapping_result.id,
                    )
                )

        return payloads

    def _resolve_operand_targets(  # noqa
        self,
        *,
        operand: CanonicalRuleOperand,
        addr_index: CanonicalAddrObjectIndex,
        service_index: CanonicalServiceIndex,
    ) -> tuple[MappingEntityType, list[UUID]]:
        """
        Resolve canonical operand to one or many canonical entity ids.

        Zone:
            one target_zone_id.

        Addr/service leaf:
            one target_object_id.

        Addr/service group:
            group is expanded to leaf canonical object ids.
        """

        if operand.role in (
            CanonicalRuleOperandRole.SRC_ZONE,
            CanonicalRuleOperandRole.DST_ZONE,
        ):
            if operand.target_zone_id is None:
                raise MappingModuleDomainValidationError(
                    f"ZONE operand {operand.id} has no target_zone_id"
                )

            return MappingEntityType.ZONE, [operand.target_zone_id]

        if operand.role in (
            CanonicalRuleOperandRole.SRC_OBJECT,
            CanonicalRuleOperandRole.DST_OBJECT,
        ):
            if operand.target_object_id is None:
                raise MappingModuleDomainValidationError(
                    f"ADDR operand {operand.id} has no target_object_id"
                )

            if addr_index.is_group(operand.target_object_id):
                leaf_objects: tuple[CanonicalAddrObject, ...] = (
                    addr_index.resolve_group_leaves(operand.target_object_id)
                )

                if not leaf_objects:
                    raise MappingModuleDomainValidationError(
                        f"ADDR group operand {operand.id} has no leaf objects"
                    )

                return MappingEntityType.ADDR, [item.id for item in leaf_objects]

            return MappingEntityType.ADDR, [operand.target_object_id]

        if operand.role == CanonicalRuleOperandRole.SERVICE:
            if operand.target_object_id is None:
                raise MappingModuleDomainValidationError(
                    f"SERVICE operand {operand.id} has no target_object_id"
                )

            if service_index.is_group(operand.target_object_id):
                leaf_services: tuple[CanonicalService, ...] = (
                    service_index.resolve_group_leaves(operand.target_object_id)
                )

                if not leaf_services:
                    raise MappingModuleDomainValidationError(
                        f"SERVICE group operand {operand.id} has no leaf services"
                    )

                return MappingEntityType.SERVICE, [item.id for item in leaf_services]

            return MappingEntityType.SERVICE, [operand.target_object_id]

        raise MappingModuleDomainValidationError(
            f"Unsupported operand role: {operand.role}"
        )

    @staticmethod
    def _map_rule_action(action: CanonicalRuleAction) -> MappingScopeRuleAction:
        if action == CanonicalRuleAction.PERMIT:
            return MappingScopeRuleAction.ACCEPT

        if action == CanonicalRuleAction.DENY:
            return MappingScopeRuleAction.REJECT

        raise MappingModuleDomainValidationError(
            f"Unsupported canonical rule action: {action}"
        )

    @staticmethod
    def _map_operand_role(
        role: CanonicalRuleOperandRole,
    ) -> MappingScopeRuleOperandRole:
        match role:
            case CanonicalRuleOperandRole.SRC_ZONE:
                return MappingScopeRuleOperandRole.SRC_ZONE
            case CanonicalRuleOperandRole.DST_ZONE:
                return MappingScopeRuleOperandRole.DST_ZONE
            case CanonicalRuleOperandRole.SRC_OBJECT:
                return MappingScopeRuleOperandRole.SRC_ADDR_OBJECT
            case CanonicalRuleOperandRole.DST_OBJECT:
                return MappingScopeRuleOperandRole.DST_ADDR_OBJECT
            case CanonicalRuleOperandRole.SERVICE:
                return MappingScopeRuleOperandRole.SERVICE

            case _:
                raise MappingModuleDomainValidationError(
                    f"Unsupported operand role: {role}"
                )
