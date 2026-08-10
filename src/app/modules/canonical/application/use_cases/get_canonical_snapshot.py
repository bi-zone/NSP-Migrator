"""Full canonical snapshot graph read (internal use)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import (
    CanonicalObjectDTO,
    CanonicalRuleDTO,
    CanonicalSnapshotDTO,
    CanonicalZoneDTO,
)
from app.modules.canonical.application.mappers import (
    object_to_dto,
    operands_by_rule,
    rule_to_dto,
    snapshot_to_dto,
    zone_to_dto,
)
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalSnapshotQuery:
    """Input for full snapshot graph load."""

    canonical_snapshot_id: UUID


@dataclass(slots=True)
class GetCanonicalSnapshotResult:
    """Full snapshot graph: header plus zones, objects, and rules."""

    snapshot: CanonicalSnapshotDTO
    zones: list[CanonicalZoneDTO]
    objects: list[CanonicalObjectDTO]
    rules: list[CanonicalRuleDTO]


class GetCanonicalSnapshotUseCase:
    """Load the complete canonical graph for a snapshot.

    HTTP GET /snapshots/{id} exposes only result.snapshot (header).
    The full graph in this result is available for internal callers that need
    a single round-trip load.
    """

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(
        self, query: GetCanonicalSnapshotQuery
    ) -> GetCanonicalSnapshotResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        zones = await self.uow.zones.get_by_snapshot(query.canonical_snapshot_id)
        objects = await self.uow.objects.get_by_snapshot(query.canonical_snapshot_id)
        rules = await self.uow.rules.get_by_snapshot(query.canonical_snapshot_id)
        operands = await self.uow.rules.get_operands_by_snapshot(
            query.canonical_snapshot_id
        )
        grouped = operands_by_rule(operands)

        return GetCanonicalSnapshotResult(
            snapshot=snapshot_to_dto(snapshot),
            zones=[zone_to_dto(zone) for zone in zones],
            objects=[object_to_dto(obj) for obj in objects],
            rules=[
                rule_to_dto(rule, operands=grouped.get(rule.id, [])) for rule in rules
            ],
        )
