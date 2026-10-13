from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from app.core.querying import Sorting
from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.canonical.domain.rule import CanonicalRule, CanonicalRuleOperand


class CanonicalRuleSortField(StrEnum):
    """Whitelist of rule columns allowed for client-driven sorting."""

    PRIORITY = "priority"
    NAME = "name"
    ACTION = "action"
    ENABLED = "enabled"
    SECTION = "section"
    RULE_KEY = "rule_key"
    DESCRIPTION = "description"


class CanonicalRuleSearchScope(StrEnum):
    """Where the case-insensitive search expression is applied."""

    ALL = "all"
    RULES = "rules"
    OBJECTS = "objects"
    ZONES = "zones"


@dataclass(slots=True)
class CanonicalRuleFilters:
    """Filter contract for scoped canonical rule queries.

    Used by GetCanonicalRuleScopeUseCase, GetCanonicalRulesUseCase,
    and mapping CanonicalReader.

    search applies case-insensitive LIKE according to search_scope:
    - all — rule fields + referenced object/zone names (incl. nested members)
    - rules — rule name/rule_key/section/description/action only
    - objects — object name/key/cidr/fqdn (and ancestor groups of matches)
    - zones — zone name/zone_key
    section is an exact match on the ACL / policy block name from source
    (for example global_access), not a free-text search.
    operand_object_ids matches both direct operands and ancestor groups that
    transitively contain the selected objects.
    fw_applicable_only currently matches Cisco metadata stored in
    CanonicalRule.description.
    """

    rule_ids: list[UUID] | None = None
    search: str | None = None
    search_scope: CanonicalRuleSearchScope = CanonicalRuleSearchScope.ALL
    action: str | None = None
    enabled: bool | None = None
    section: str | None = None
    operand_zone_ids: list[UUID] = field(default_factory=list)
    operand_object_ids: list[UUID] = field(default_factory=list)
    fw_applicable_only: bool | None = None

    def normalized_search(self) -> str | None:
        """Return stripped search text or None for a blank value."""
        if self.search and self.search.strip():
            return self.search.strip()
        return None

    def has_any(self) -> bool:
        """True when at least one filter is set; drives scope narrowing in rule_scope."""
        return any(
            (
                self.rule_ids,
                self.normalized_search(),
                self.action,
                self.enabled is not None,
                self.section,
                self.operand_zone_ids,
                self.operand_object_ids,
                self.fw_applicable_only is not None,
            )
        )


class CanonicalRuleRepositoryPort(IAsyncRepository[CanonicalRule, UUID]):
    """Persistence contract for rules, operands, and filtered scope reads."""

    @abstractmethod
    async def bulk_save(self, rules: list[CanonicalRule]) -> None:
        """Persist rule rows on snapshot write path."""

    @abstractmethod
    async def bulk_save_operands(
        self, operands: list[CanonicalRuleOperand]
    ) -> None:
        """Persist operand rows after rules."""

    @abstractmethod
    async def get_by_id_for_snapshot(
        self, *, canonical_snapshot_id: UUID, rule_id: UUID
    ) -> CanonicalRule | None:
        """Single rule within snapshot bounds."""

    @abstractmethod
    async def get_operands_by_rule(
        self, *, canonical_snapshot_id: UUID, rule_id: UUID
    ) -> list[CanonicalRuleOperand]:
        """Operands for one rule."""

    @abstractmethod
    async def get_by_snapshot(
        self, canonical_snapshot_id: UUID
    ) -> list[CanonicalRule]:
        """All rules in snapshot."""

    @abstractmethod
    async def get_operands_by_snapshot(
        self, canonical_snapshot_id: UUID
    ) -> list[CanonicalRuleOperand]:
        """All operands in snapshot."""

    # TODO:: consider returning count alongside list_filtered to avoid a second query.
    @abstractmethod
    async def count_filtered(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
    ) -> int:
        """Count rules matching scope filters."""

    @abstractmethod
    async def list_filtered(
        self,
        *,
        canonical_snapshot_id: UUID,
        filters: CanonicalRuleFilters,
        limit: int | None,
        offset: int | None,
        sort: Sorting[CanonicalRuleSortField] | None = None,
    ) -> list[CanonicalRule]:
        """Paginated filtered rules for rule_scope and list API."""
        # TODO(querying): accept Pagination after legacy rule_scope is migrated.

    @abstractmethod
    async def get_operands_by_rule_ids(
        self, *, canonical_snapshot_id: UUID, rule_ids: list[UUID]
    ) -> list[CanonicalRuleOperand]:
        """Operands for a page of filtered rules."""
