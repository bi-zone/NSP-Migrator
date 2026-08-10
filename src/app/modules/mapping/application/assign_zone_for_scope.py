from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.integrations.sdwan_csp_api.gateways.models import SdwanZone
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    MappingScopeRuleOperandRole,
    SDWANZoneDirection,
)
from app.modules.mapping.domain.exceptions import MappingModuleNotFoundError
from app.modules.mapping.domain.value_objects import MappingScopeRuleOperandPayload
from app.modules.mapping.ports.gateways import MappingSDWANGatewayPort
from app.modules.mapping.ports.uow import MappingUnitOfWorkPort


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
        uow: MappingUnitOfWorkPort,
        sdwan_gateway: MappingSDWANGatewayPort,
    ) -> None:
        self.uow = uow
        self.sdwan_gateway = sdwan_gateway

    @async_transactional(read_only=False)
    async def execute(
        self,
        command: AssignZoneForScopeCommand,
    ) -> AssignZoneForScopeResult:

        # -- get zone from sd-wan
        sdwan_zone: SdwanZone | None = await self.sdwan_gateway.get_zone(
            command.zone_sdwan_id
        )
        if not sdwan_zone:
            raise MappingModuleNotFoundError(
                f"Zone with id {command.zone_sdwan_id} not found in SD-WAN"
            )

        # -- get scope with rules to validate that requested policy belongs to scope
        mapping_scope: MappingScope | None = (
            await self.uow.mapping_scope_repo.get_scope_by_id(
                scope_id=command.mapping_scope_id,
                with_rules=True,
            )
        )
        if not mapping_scope:
            raise MappingModuleNotFoundError(
                f"Mapping scope with id {command.mapping_scope_id} not found"
            )
        if not mapping_scope.rules:
            raise MappingModuleNotFoundError(
                f"Not provided rules for mapping scope {command.mapping_scope_id}"
            )

        # -- create mapping result manually for zone without canonical counterpart
        zone_manual_mapping_result = MappingEntityResult.create_zone_manually_assigned(
            sdwan_zone_id=sdwan_zone.id,
            mapping_scope_id=mapping_scope.id,
        )
        await self.uow.mapping_result_repo.add_results(
            results=[zone_manual_mapping_result]
        )

        # -- attach result as an operand for scope rules
        result_operands = []
        for mapping_rule in mapping_scope.rules:
            operand = MappingScopeRuleOperand.create(
                mapping_scope_rule_id=mapping_rule.id,
                payload=MappingScopeRuleOperandPayload(
                    role=self._map_zone_direction(command.zone_direction),
                    mapping_entity_result_id=zone_manual_mapping_result.id,
                ),
            )
            await self.uow.mapping_scope_repo.add_rule_operand(
                scope_id=mapping_scope.id,
                operand=operand,
            )
            result_operands.append(operand)

        return AssignZoneForScopeResult(
            mapping_result=zone_manual_mapping_result,
            operands=result_operands,
        )

    @staticmethod
    def _map_zone_direction(
        zone_direction: SDWANZoneDirection,
    ) -> MappingScopeRuleOperandRole:
        if zone_direction == SDWANZoneDirection.SRC_ZONE:
            return MappingScopeRuleOperandRole.SRC_ZONE

        if zone_direction == SDWANZoneDirection.DST_ZONE:
            return MappingScopeRuleOperandRole.DST_ZONE

        raise ValueError(f"Unsupported zone direction: {zone_direction}")
