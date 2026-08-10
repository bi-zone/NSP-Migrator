"""Single rule read with hydrated zone/object operand summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import (
    CanonicalRuleDTO,
    CanonicalRuleOperandDTO,
    CanonicalRuleOperandHydratedDTO,
)
from app.modules.canonical.application.mappers import (
    object_summary_to_dto,
    operand_to_dto,
    rule_to_dto,
    zone_summary_to_dto,
)
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalRuleQuery:
    """Input for single rule detail read."""

    canonical_snapshot_id: UUID
    rule_id: UUID


@dataclass(slots=True)
class GetCanonicalRuleResult:
    """Rule DTO with hydrated operands."""

    rule: CanonicalRuleDTO


class GetCanonicalRuleUseCase:
    """Load one rule and batch-resolve zone/object summaries for operands.

    Called by canonical/http/routers/rules.get_snapshot_rule and Streamlit.
    Unlike list endpoints, operands include target_zone / target_object
    summaries instead of bare IDs only.
    """

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalRuleQuery) -> GetCanonicalRuleResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        rule = await self.uow.rules.get_by_id_for_snapshot(
            canonical_snapshot_id=query.canonical_snapshot_id,
            rule_id=query.rule_id,
        )
        if rule is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical rule not found: {query.rule_id}"
            )

        operands = await self.uow.rules.get_operands_by_rule(
            canonical_snapshot_id=query.canonical_snapshot_id,
            rule_id=query.rule_id,
        )

        zone_ids = list(
            {op.target_zone_id for op in operands if op.target_zone_id is not None}
        )
        object_ids = list(
            {op.target_object_id for op in operands if op.target_object_id is not None}
        )
        zones = (
            await self.uow.zones.get_by_ids_for_snapshot(
                canonical_snapshot_id=query.canonical_snapshot_id,
                zone_ids=zone_ids,
            )
            if zone_ids
            else []
        )
        objects = (
            await self.uow.objects.get_by_ids_for_snapshot(
                canonical_snapshot_id=query.canonical_snapshot_id,
                object_ids=object_ids,
            )
            if object_ids
            else []
        )
        zone_by_id = {zone.id: zone for zone in zones}
        object_by_id = {obj.id: obj for obj in objects}

        hydrated: list[CanonicalRuleOperandHydratedDTO] = []
        for operand in operands:
            zone = (
                zone_by_id.get(operand.target_zone_id)
                if operand.target_zone_id
                else None
            )
            obj = (
                object_by_id.get(operand.target_object_id)
                if operand.target_object_id
                else None
            )
            operand_dto = operand_to_dto(operand)
            hydrated.append(
                CanonicalRuleOperandHydratedDTO(
                    id=operand_dto.id,
                    rule_id=operand_dto.rule_id,
                    operand_role=operand_dto.operand_role,
                    target_zone_id=operand_dto.target_zone_id,
                    target_object_id=operand_dto.target_object_id,
                    position=operand_dto.position,
                    target_zone=zone_summary_to_dto(zone) if zone else None,
                    target_object=object_summary_to_dto(obj) if obj else None,
                )
            )

        return GetCanonicalRuleResult(
            rule=rule_to_dto(
                rule,
                operands=cast(list[CanonicalRuleOperandDTO], hydrated),
            )
        )
