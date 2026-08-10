from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.canonical.domain.rule import CanonicalRule, CanonicalRuleOperand


@dataclass(slots=True)
class CanonicalRuleFilters:
    """Filter contract for scoped canonical rule queries.

    Used by GetCanonicalRuleScopeUseCase and mapping CanonicalReader.
    fw_applicable_only currently matches Cisco metadata stored in
    CanonicalRule.description`.
    """
    rule_ids: list[UUID] | None = None
    name_contains: str | None = None
    action: str | None = None
    enabled: bool | None = None
    section: str | None = None
    operand_zone_ids: list[UUID] = field(default_factory=list)
    operand_object_ids: list[UUID] = field(default_factory=list)
    fw_applicable_only: bool | None = None

    def has_any(self) -> bool:
        """True when at least one filter is set; drives scope narrowing in rule_scope."""
        return any(
            (
                self.rule_ids,
                self.name_contains,
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
    ) -> list[CanonicalRule]:
        """Paginated filtered rules for rule_scope."""

    @abstractmethod
    async def get_operands_by_rule_ids(
        self, *, canonical_snapshot_id: UUID, rule_ids: list[UUID]
    ) -> list[CanonicalRuleOperand]:
        """Operands for a page of filtered rules."""
