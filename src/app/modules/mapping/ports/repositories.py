from abc import ABC, abstractmethod
from uuid import UUID

from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingResultStatus,
)


class MappingScopeRepositoryPort(ABC):
    """
    Repository for MappingScope aggregate.

    Owns:
    - mapping_scope;
    - mapping_scope_rule.
    """

    @abstractmethod
    async def add_scope(self, scope: MappingScope) -> MappingScope:
        """Persist new mapping scope with optional selected rules."""
        ...

    @abstractmethod
    async def get_scope_by_id(
        self,
        scope_id: UUID,
        *,
        with_rules: bool = False,
    ) -> MappingScope | None:
        """Return scope by id."""
        ...

    @abstractmethod
    async def attach_rules(
        self,
        *,
        scope_id: UUID,
        rules: list[MappingScopeRule],
    ) -> None:
        """
        Attach persisted mapped rules for scope.

        Used after mapping results are built.
        """
        ...

    @abstractmethod
    async def add_rule_operand(
        self,
        *,
        scope_id: UUID,
        operand: MappingScopeRuleOperand,
    ) -> None:
        """
        Attach one operand to an existing mapped rule.

        Used by incremental UI flows, for example manual zone assignment when
        canonical rule does not contain source/destination zone operands.
        """
        ...

    @abstractmethod
    async def list_recent_scopes(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MappingScope]:
        """Return recent mapping scopes for UI list."""
        ...


class MappingEntityResultRepositoryPort(ABC):
    """
    Repository for MappingEntityResult aggregate.

    Owns:
    - mapping_entity_result;
    - mapping_entity_candidate.

    Candidate is a child entity.
    """

    @abstractmethod
    async def add_results(self, results: list[MappingEntityResult]) -> None:
        """
        Insert mapping results without deleting existing rows.

        Useful for incremental mapping flows.
        """
        ...

    @abstractmethod
    async def get_result_by_id(
        self,
        result_id: UUID,
        *,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        """Return one mapping result by id."""
        ...

    @abstractmethod
    async def get_result_by_canonical_entity(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        """
        Return mapping result by canonical entity id.

        For ZONE:
            canonical_entity_id means canonical_zone.id.

        For ADDR/SERVICE:
            canonical_entity_id means canonical_object.id.
        """
        ...

    @abstractmethod
    async def list_by_scope(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType | None = None,
        status: MappingResultStatus | None = None,
        with_candidates: bool = False,
    ) -> list[MappingEntityResult]:
        """
        Return mapping results for scope.

        Can be filtered by entity type and/or result status.
        """
        ...

    @abstractmethod
    async def save_result(self, result: MappingEntityResult) -> MappingEntityResult:
        """
        Save one mapping result aggregate (save updates).

        Usually used after manual candidate selection, direct selection or
        object creation flow.
        """
        ...
