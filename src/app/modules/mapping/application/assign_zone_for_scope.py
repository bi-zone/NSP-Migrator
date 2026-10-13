from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.models import SdwanZone
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleOperandRole,
    SDWANZoneDirection,
)
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.domain.value_objects import MappingScopeRuleOperandPayload
from app.modules.mapping.ports.gateways import MappingSDWANGatewayProviderPort
from app.modules.mapping.ports.repositories import MappingRepositoryPort


@dataclass(frozen=True, slots=True)
class AssignZoneForScopeCommand:
    zone_direction: Literal[
        SDWANZoneDirection.SRC_ZONE,
        SDWANZoneDirection.DST_ZONE,
    ]
    zone_sdwan_id: int
    mapping_scope_id: UUID


@dataclass(frozen=True, slots=True)
class AssignZoneForScopeResult:
    mapping_result: MappingEntityResult
    operands: list[MappingScopeRuleOperand]


class AssignZoneForScopeUseCase:
    def __init__(
        self,
        mapping_repo: MappingRepositoryPort,
        sdwan_gateway_provider: MappingSDWANGatewayProviderPort,
    ) -> None:
        self.mapping_repo = mapping_repo
        self.sdwan_gateway_provider = sdwan_gateway_provider

    async def execute(
        self,
        command: AssignZoneForScopeCommand,
    ) -> AssignZoneForScopeResult:
        # -- prepare operation data
        mapping_scope = await self._get_scope_with_rules(command.mapping_scope_id)
        sdwan_zone = await self._get_sdwan_zone(mapping_scope, command.zone_sdwan_id)
        zone_role = self._map_zone_direction(command.zone_direction)
        matching_zone_results = await self._get_matching_zone_results(
            scope_id=mapping_scope.id,
            sdwan_zone_id=sdwan_zone.id,
        )

        # -- assign to every scope rule that is not already covered by this zone.
        rules_without_zone = self._rules_without_zone(
            rules=mapping_scope.rules or [],
            role=zone_role,
            matching_zone_results=matching_zone_results,
        )

        if not rules_without_zone:
            return AssignZoneForScopeResult(
                mapping_result=self._existing_mapping_result(matching_zone_results),
                operands=[],
            )

        # -- get or create mapping result for zone (without canonical link)
        manual_zone_mapping_result = await self._get_or_create_manual_zone_result(
            scope_id=mapping_scope.id,
            sdwan_zone_id=sdwan_zone.id,
            matching_zone_results=matching_zone_results,
        )
        # -- assign zone mapping result for rules operands of scope
        result_operands = await self._add_zone_operands(
            scope_id=mapping_scope.id,
            rules=rules_without_zone,
            role=zone_role,
            mapping_result_id=manual_zone_mapping_result.id,
        )

        return AssignZoneForScopeResult(
            mapping_result=manual_zone_mapping_result,
            operands=result_operands,
        )

    async def _get_scope_with_rules(self, scope_id: UUID) -> MappingScope:
        """Load a scope that can receive a manual zone assignment."""
        mapping_scope = await self.mapping_repo.get_scope_by_id(
            scope_id=scope_id,
            with_rules=True,
        )
        if mapping_scope is None:
            raise MappingModuleNotFoundError(
                f"Mapping scope with id {scope_id} not found"
            )
        if not mapping_scope.rules:
            raise MappingModuleNotFoundError(
                f"Not provided rules for mapping scope {scope_id}"
            )
        return mapping_scope

    async def _get_sdwan_zone(
        self,
        mapping_scope: MappingScope,
        zone_sdwan_id: int,
    ) -> SdwanZone:
        """Validate that the selected zone belongs to the scope's SD-WAN."""
        async with self.sdwan_gateway_provider.acquire(
            mapping_scope.csp_profile_id,
            mapping_scope.vpc_id,
        ) as sdwan_gateway:
            sdwan_zone = await sdwan_gateway.get_zone(zone_sdwan_id)

        if sdwan_zone is None:
            raise MappingModuleNotFoundError(
                f"Zone with id {zone_sdwan_id} not found in SD-WAN"
            )
        return sdwan_zone

    async def _get_matching_zone_results(
        self,
        *,
        scope_id: UUID,
        sdwan_zone_id: int,
    ) -> list[MappingEntityResult]:
        """Return mapped zone results that resolve to the selected SD-WAN zone."""
        zone_mapping_results = await self.mapping_repo.list_results(
            scope_id=scope_id,
            entity_type=MappingEntityType.ZONE,
        )
        return [
            result
            for result in zone_mapping_results
            if result.result_status == MappingResultStatus.MATCHED
            and result.selected_sdwan_entity_id == sdwan_zone_id
        ]

    async def _get_or_create_manual_zone_result(
        self,
        *,
        scope_id: UUID,
        sdwan_zone_id: int,
        matching_zone_results: list[MappingEntityResult],
    ) -> MappingEntityResult:
        """Reuse the manual result for the zone, or create it once for the scope."""
        manual_result = next(
            (
                result
                for result in matching_zone_results
                if result.canonical_zone_id is None
                and result.canonical_object_id is None
            ),
            None,
        )
        if manual_result is not None:
            return manual_result

        manual_result = MappingEntityResult.create_zone_manually_assigned(
            sdwan_zone_id=sdwan_zone_id,
            mapping_scope_id=scope_id,
        )
        await self.mapping_repo.add_results(
            scope_id=scope_id,
            results=[manual_result],
        )
        return manual_result

    async def _add_zone_operands(
        self,
        *,
        scope_id: UUID,
        rules: list[MappingScopeRule],
        role: MappingScopeRuleOperandRole,
        mapping_result_id: UUID,
    ) -> list[MappingScopeRuleOperand]:
        """Attach one manual zone result to each rule that still needs it."""
        operands: list[MappingScopeRuleOperand] = []
        for mapping_rule in rules:
            operand = MappingScopeRuleOperand.create(
                mapping_scope_rule_id=mapping_rule.id,
                payload=MappingScopeRuleOperandPayload(
                    role=role,
                    mapping_entity_result_id=mapping_result_id,
                ),
            )
            await self.mapping_repo.add_rule_operand(
                scope_id=scope_id,
                operand=operand,
            )
            operands.append(operand)
        return operands

    @staticmethod
    def _rules_without_zone(
        *,
        rules: list[MappingScopeRule],
        role: MappingScopeRuleOperandRole,
        matching_zone_results: list[MappingEntityResult],
    ) -> list[MappingScopeRule]:
        matching_result_ids = {result.id for result in matching_zone_results}
        return [
            rule
            for rule in rules
            if not any(
                operand.role == role
                and operand.mapping_entity_result_id in matching_result_ids
                for operand in rule.operands or []
            )
        ]

    @staticmethod
    def _existing_mapping_result(
        matching_zone_results: list[MappingEntityResult],
    ) -> MappingEntityResult:
        """Return the result that already proves the no-op assignment."""
        manual_result = next(
            (
                result
                for result in matching_zone_results
                if result.canonical_zone_id is None
                and result.canonical_object_id is None
            ),
            None,
        )
        if manual_result is not None:
            return manual_result
        return matching_zone_results[0]

    @staticmethod
    def _map_zone_direction(
        zone_direction: SDWANZoneDirection,
    ) -> MappingScopeRuleOperandRole:
        if zone_direction == SDWANZoneDirection.SRC_ZONE:
            return MappingScopeRuleOperandRole.SRC_ZONE

        if zone_direction == SDWANZoneDirection.DST_ZONE:
            return MappingScopeRuleOperandRole.DST_ZONE

        raise ValueError(f"Unsupported zone direction: {zone_direction}")
