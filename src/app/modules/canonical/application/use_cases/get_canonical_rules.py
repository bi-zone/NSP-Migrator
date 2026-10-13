"""List rules for a snapshot with optional filters, sort, and pagination."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.core.querying import Pagination, Sorting
from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.application.dto import CanonicalRuleDTO, PaginationDTO
from app.modules.canonical.application.mappers import operands_by_rule, rule_to_dto
from app.modules.canonical.domain.exceptions import CanonicalModuleNotFoundError
from app.modules.canonical.ports.rule_repository import (
    CanonicalRuleFilters,
    CanonicalRuleSortField,
)
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class GetCanonicalRulesQuery:
    """Input for paginated/filtered rule list."""

    canonical_snapshot_id: UUID
    filters: CanonicalRuleFilters = field(default_factory=CanonicalRuleFilters)
    pagination: Pagination = field(default_factory=Pagination)
    sorting: Sorting[CanonicalRuleSortField] | None = None


@dataclass(slots=True)
class GetCanonicalRulesResult:
    rules: list[CanonicalRuleDTO]
    pagination: PaginationDTO


class GetCanonicalRulesUseCase:
    """Read rules for one snapshot with shared filter/sort/pagination contract."""

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetCanonicalRulesQuery) -> GetCanonicalRulesResult:
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
            limit=query.pagination.limit,
            offset=query.pagination.offset,
            sort=query.sorting,
        )
        rule_ids = [rule.id for rule in rules]
        operands = await self.uow.rules.get_operands_by_rule_ids(
            canonical_snapshot_id=query.canonical_snapshot_id,
            rule_ids=rule_ids,
        )
        grouped = operands_by_rule(operands)

        return GetCanonicalRulesResult(
            rules=[
                rule_to_dto(rule, operands=grouped.get(rule.id, [])) for rule in rules
            ],
            pagination=PaginationDTO(
                limit=query.pagination.limit,
                offset=query.pagination.offset,
                total=total,
            ),
        )
