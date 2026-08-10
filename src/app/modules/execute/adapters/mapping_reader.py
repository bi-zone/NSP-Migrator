from uuid import UUID

from app.modules.execute.errors import ExecuteModuleError
from app.modules.execute.ports.mapping_reader.port import MappingReaderPort
from app.modules.execute.ports.mapping_reader.schemas import (
    MappedRuleData,
    MappedRuleDataAction,
    MappingScopeData,
)
from app.modules.mapping.application.get_mapping_scope import (
    GetMappingScopeQuery,
    GetMappingScopeResult,
    GetMappingScopeUseCase,
)
from app.modules.mapping.application.get_mapping_scope_rules import (
    GetMappingScopeRulesQuery,
    GetMappingScopeRulesResult,
    GetMappingScopeRulesUseCase,
)
from app.modules.mapping.domain.entities import MappingEntityResult
from app.modules.mapping.domain.enums import (
    MappingResultStatus,
    MappingScopeRuleOperandRole,
)


class MappingReader(MappingReaderPort):
    """Adapter that reads Mapping module data needed by execute use cases."""

    def __init__(
        self,
        get_mapped_rules: GetMappingScopeRulesUseCase,
        get_mapping_scope: GetMappingScopeUseCase,
    ) -> None:
        self.get_mapped_rules = get_mapped_rules
        self.get_mapping_scope = get_mapping_scope

    async def get_mapping_scope_rules(
        self, mapping_scope_id: UUID
    ) -> list[MappedRuleData]:
        """Return only fully matched Mapping rules as execute-ready SD-WAN ids."""
        result: GetMappingScopeRulesResult = await self.get_mapped_rules.execute(
            query=GetMappingScopeRulesQuery(
                mapping_scope_id=mapping_scope_id,
            )
        )

        if any(
            map_res.result_status != MappingResultStatus.MATCHED
            for map_res in result.mapping_results
        ):
            raise ExecuteModuleError(
                f"Mapping scope {mapping_scope_id} has unmatched objects."
            )

        mapping_results_by_id: dict[UUID, MappingEntityResult] = {
            map_res.id: map_res for map_res in result.mapping_results
        }

        mapped_rules_data: list[MappedRuleData] = []

        for mapped_rule in result.rules:
            rule_entities_ids_by_role: dict[MappingScopeRuleOperandRole, list[int]] = {
                MappingScopeRuleOperandRole.SRC_ZONE: [],
                MappingScopeRuleOperandRole.DST_ZONE: [],
                MappingScopeRuleOperandRole.SRC_ADDR_OBJECT: [],
                MappingScopeRuleOperandRole.DST_ADDR_OBJECT: [],
                MappingScopeRuleOperandRole.SERVICE: [],
            }

            if mapped_rule.operands is None:
                raise ExecuteModuleError(
                    f"Not provided operands for rule {mapped_rule.id}"
                )

            for operand in mapped_rule.operands:
                mapping_result: MappingEntityResult | None = mapping_results_by_id.get(
                    operand.mapping_entity_result_id,
                )
                if mapping_result is None:
                    raise ExecuteModuleError(
                        f"Not found mapping result for mapped rule operand {operand.id}"
                    )

                if mapping_result.selected_sdwan_entity_id is None:
                    raise ExecuteModuleError(
                        f"Mapping result of mapped rule operand {operand.id} has no assigned sdwan id"
                    )

                rule_entities_ids_by_role[operand.role].append(
                    mapping_result.selected_sdwan_entity_id
                )

            mapped_rules_data.append(
                MappedRuleData(
                    id=mapped_rule.id,
                    action=MappedRuleDataAction(mapped_rule.action),
                    src_zones=rule_entities_ids_by_role[
                        MappingScopeRuleOperandRole.SRC_ZONE
                    ],
                    dst_zones=rule_entities_ids_by_role[
                        MappingScopeRuleOperandRole.DST_ZONE
                    ],
                    src_addr_objects=rule_entities_ids_by_role[
                        MappingScopeRuleOperandRole.SRC_ADDR_OBJECT
                    ],
                    dst_addr_objects=rule_entities_ids_by_role[
                        MappingScopeRuleOperandRole.DST_ADDR_OBJECT
                    ],
                    services=rule_entities_ids_by_role[
                        MappingScopeRuleOperandRole.SERVICE
                    ],
                )
            )

        return mapped_rules_data

    async def get_mapping_scope_data(self, mapping_scope_id: UUID) -> MappingScopeData:
        """Return mapping scope metadata required to execute prepared plan."""
        result: GetMappingScopeResult = await self.get_mapping_scope.execute(
            query=GetMappingScopeQuery(mapping_scope_id=mapping_scope_id)
        )
        return MappingScopeData(
            id=result.mapping_scope.id,
            sdwan_target_id=result.mapping_scope.sdwan_target_id,
        )
