"""List all rules for a snapshot with flat operands."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalRuleDTO
from app.modules.canonical.application.mappers import operands_by_rule, rule_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalRulesQuery:
    canonical_snapshot_id: UUID


@dataclass(slots=True)
class GetCanonicalRulesResult:
    rules: list[CanonicalRuleDTO]


class GetCanonicalRulesUseCase:
    """Read all rules and operands for one snapshot."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalRulesQuery) -> GetCanonicalRulesResult:
        snapshot = await self.uow.snapshots.get_by_id(query.canonical_snapshot_id)
        if snapshot is None:
            raise CanonicalModuleNotFoundError(
                f"Canonical snapshot not found: {query.canonical_snapshot_id}"
            )

        rules = await self.uow.rules.get_by_snapshot(query.canonical_snapshot_id)
        operands = await self.uow.rules.get_operands_by_snapshot(
            query.canonical_snapshot_id
        )
        grouped = operands_by_rule(operands)

        return GetCanonicalRulesResult(
            rules=[
                rule_to_dto(rule, operands=grouped.get(rule.id, [])) for rule in rules
            ]
        )
