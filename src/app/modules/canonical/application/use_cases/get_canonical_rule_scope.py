"""Rule scope projection for mapping and HTTP rule_scope endpoint."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import (
    CanonicalObjectDTO,
    CanonicalRuleDTO,
    CanonicalZoneDTO,
    PaginationDTO,
)
from app.modules.canonical.application.mappers import (
    object_to_dto,
    operands_by_rule,
    rule_to_dto,
    zone_to_dto,
)
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.rule_repository import CanonicalRuleFilters
from app.modules.canonical.ports.uow import CanonicalUoWPort
from app.modules.canonical.services.group_expansion import expand_object_groups


@dataclass(slots=True)
class GetCanonicalRuleScopeQuery:
    """Input for mapping-oriented canonical scope projection."""

    canonical_snapshot_id: UUID
    limit: int | None = None
    offset: int | None = None
    filters: CanonicalRuleFilters = field(default_factory=CanonicalRuleFilters)
    include_all_zones: bool = False


@dataclass(slots=True)
class GetCanonicalRuleScopeResult:
    """Composite scope payload returned to mapping and HTTP consumers."""

    rules: list[CanonicalRuleDTO]
    zones: list[CanonicalZoneDTO]
    objects: list[CanonicalObjectDTO]
    pagination: PaginationDTO


class GetCanonicalRuleScopeUseCase:
    """Return filtered rules plus scoped zones/objects for mapping workflows.

    Called by mapping/adapters/canonical_reader and
    canonical/http/routers/rules.get_snapshot_rule_scope.
    """

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self, query: GetCanonicalRuleScopeQuery
    ) -> GetCanonicalRuleScopeResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        total = await self.uow.rules.count_filtered(
            canonical_snapshot_id=query.canonical_snapshot_id,
            filters=query.filters,
        )
        rules = await self.uow.rules.list_filtered(
            canonical_snapshot_id=query.canonical_snapshot_id,
            filters=query.filters,
            limit=query.limit,
            offset=query.offset,
        )
        rule_ids = [rule.id for rule in rules]
        operands = await self.uow.rules.get_operands_by_rule_ids(
            canonical_snapshot_id=query.canonical_snapshot_id,
            rule_ids=rule_ids,
        )
        grouped = operands_by_rule(operands)

        rule_dtos = [
            rule_to_dto(rule, operands=grouped.get(rule.id, [])) for rule in rules
        ]

        # When any filter is active, zones/objects are narrowed to rule operands
        # unless include_all_zones overrides zone collection.
        narrow_scope = query.filters.has_any()
        zone_dtos = await self._collect_zones(
            canonical_snapshot_id=query.canonical_snapshot_id,
            operands=operands,
            narrow_scope=narrow_scope,
            include_all_zones=query.include_all_zones,
        )
        object_dtos = await self._collect_objects(
            canonical_snapshot_id=query.canonical_snapshot_id,
            operands=operands,
            narrow_scope=narrow_scope,
        )

        return GetCanonicalRuleScopeResult(
            rules=rule_dtos,
            zones=zone_dtos,
            objects=object_dtos,
            pagination=PaginationDTO(
                limit=query.limit, offset=query.offset, total=total
            ),
        )

    async def _collect_zones(
        self,
        *,
        canonical_snapshot_id: UUID,
        operands: list,
        narrow_scope: bool,
        include_all_zones: bool,
    ) -> list[CanonicalZoneDTO]:
        """Load all snapshot zones or only zones referenced by rule operands."""
        if not narrow_scope or include_all_zones:
            zones = await self.uow.zones.get_by_snapshot(canonical_snapshot_id)
        else:
            zone_ids = list(
                {op.target_zone_id for op in operands if op.target_zone_id is not None}
            )
            zones = await self.uow.zones.get_by_ids_for_snapshot(
                canonical_snapshot_id=canonical_snapshot_id,
                zone_ids=zone_ids,
            )

        return [zone_to_dto(zone) for zone in zones]

    async def _collect_objects(
        self,
        *,
        canonical_snapshot_id: UUID,
        operands: list,
        narrow_scope: bool,
    ) -> list[CanonicalObjectDTO]:
        """Load all objects or operand seeds with transitive group expansion."""
        if not narrow_scope:
            objects = await self.uow.objects.get_by_snapshot(canonical_snapshot_id)
            return [object_to_dto(obj) for obj in objects]

        seed_ids = {
            op.target_object_id for op in operands if op.target_object_id is not None
        }
        if not seed_ids:
            return []

        objects, parent_ids = await expand_object_groups(
            objects=self.uow.objects,
            canonical_snapshot_id=canonical_snapshot_id,
            seed_ids=seed_ids,
        )
        return [
            object_to_dto(
                obj,
                parent_ids=tuple(sorted(parent_ids.get(obj.id, set()), key=str)),
            )
            for obj in objects
        ]
