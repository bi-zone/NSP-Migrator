from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from app.modules.common.domain.utils import get_utc_now
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleAction,
    MappingScopeRuleOperandRole,
    SdwanObjectSelectionMethod,
)
from app.modules.mapping.domain.value_objects import (
    MappingEntityCandidatePayload,
    MappingScopeRuleOperandPayload,
)


@dataclass(frozen=True, slots=True)
class MappingScopeRuleOperand:
    """
    Operand of persisted mapped rule skeleton.

    It does not duplicate SD-WAN ids.
    It points to MappingEntityResult, which owns selected/candidate SD-WAN ids.

    For canonical groups:
        We do not store group placeholder here.
        We store expanded leaf operands, each linked to its MappingEntityResult.
    """

    id: UUID
    mapping_scope_rule_id: UUID
    role: MappingScopeRuleOperandRole
    mapping_entity_result_id: UUID

    @classmethod
    def create(
        cls,
        *,
        mapping_scope_rule_id: UUID,
        payload: MappingScopeRuleOperandPayload,
    ) -> Self:
        return cls(
            id=uuid4(),
            mapping_scope_rule_id=mapping_scope_rule_id,
            role=payload.role,
            mapping_entity_result_id=payload.mapping_entity_result_id,
        )


@dataclass(frozen=True, slots=True)
class MappingScopeRule:
    """
    Canonical rule included into mapping scope.
    """

    id: UUID
    mapping_scope_id: UUID
    canonical_rule_id: UUID

    name: str
    action: MappingScopeRuleAction

    operands: list[MappingScopeRuleOperand] | None

    @classmethod
    def create(
        cls,
        *,
        mapping_scope_id: UUID,
        canonical_rule_id: UUID,
        name: str,
        action: MappingScopeRuleAction,
        operands_payloads: list[MappingScopeRuleOperandPayload],
    ) -> Self:
        rule_id = uuid4()

        return cls(
            id=rule_id,
            mapping_scope_id=mapping_scope_id,
            canonical_rule_id=canonical_rule_id,
            name=name,
            action=action,
            operands=[
                MappingScopeRuleOperand.create(
                    mapping_scope_rule_id=rule_id,
                    payload=payload,
                )
                for payload in operands_payloads
            ],
        )


@dataclass(frozen=True, slots=True)
class MappingScope:
    """Aggregate root of mapping module."""

    id: UUID
    title: str
    canonical_snapshot_id: UUID
    sdwan_target_id: str
    created_at: datetime
    rules: list[MappingScopeRule] | None = None

    @classmethod
    def create_header(
        cls,
        *,
        title: str,
        canonical_snapshot_id: UUID,
        sdwan_target_id: str,
    ) -> Self:
        """
        Create scope header.

        Rules are attached after object mapping results are built, because
        MappingScopeRuleOperand must reference MappingEntityResult.id.
        """
        return cls(
            id=uuid4(),
            title=title,
            canonical_snapshot_id=canonical_snapshot_id,
            sdwan_target_id=sdwan_target_id,
            created_at=get_utc_now(),
            rules=None,
        )

    def attach_rules(self, rules: list[MappingScopeRule]) -> Self:
        return replace(self, rules=rules)


@dataclass(frozen=True, slots=True)
class MappingEntityCandidate:
    """
    Candidate SD-WAN entity for one mapping result.
    """

    id: UUID
    result_id: UUID
    rank: int
    score: int
    strategy: CandidateMatchStrategy
    sdwan_entity_id: int

    @classmethod
    def create(
        cls,
        *,
        result_id: UUID,
        rank: int,
        score: int,
        strategy: CandidateMatchStrategy,
        sdwan_entity_id: int,
    ) -> Self:
        return cls(
            id=uuid4(),
            result_id=result_id,
            rank=rank,
            score=score,
            strategy=strategy,
            sdwan_entity_id=sdwan_entity_id,
        )


@dataclass(frozen=True, slots=True)
class MappingEntityResult:
    """
    Mapping result for one canonical entity inside one mapping scope.

    This single domain object represents zone, address object or service result.

    It hides the physical DB difference:
    - zones are stored in canonical_zone table;
    - address/service objects are stored in canonical_object table.
    """

    id: UUID
    mapping_scope_id: UUID

    entity_type: MappingEntityType  # ZONE | ADDR | SERVICE
    canonical_zone_id: UUID | None  # ZONE -> canonical_zone
    canonical_object_id: UUID | None  # ADDR | SERVICE -> canonical_object

    result_status: MappingResultStatus
    selection_method: SdwanObjectSelectionMethod | None
    selected_sdwan_entity_id: int | None

    created_at: datetime

    candidates: list[MappingEntityCandidate] | None = None

    @property
    def canonical_entity_id(self) -> UUID:
        """
        Returns canonical_zone_id for ZONE, canonical_object_id for ADDR, SERVICE
        """
        if self.entity_type == MappingEntityType.ZONE:
            if self.canonical_zone_id is None:
                raise ValueError("ZONE have no canonical_zone_id")
            return self.canonical_zone_id

        if self.canonical_object_id is None:
            raise ValueError(f"{self.entity_type} result requires canonical_object_id")
        return self.canonical_object_id

    @staticmethod
    def _resolve_canonical_ids_fields(
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
    ) -> tuple[UUID | None, UUID | None]:
        """Returns pair of can zone id, can obj id"""
        if entity_type == MappingEntityType.ZONE:
            canonical_zone_id = canonical_entity_id
            canonical_object_id = None
        else:
            canonical_zone_id = None
            canonical_object_id = canonical_entity_id

        return canonical_zone_id, canonical_object_id

    @classmethod
    def create_unresolved(
        cls,
        *,
        mapping_scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
    ) -> Self:
        cz_id, co_id = cls._resolve_canonical_ids_fields(
            entity_type, canonical_entity_id
        )

        return cls(
            id=uuid4(),
            mapping_scope_id=mapping_scope_id,
            entity_type=entity_type,
            canonical_zone_id=cz_id,
            canonical_object_id=co_id,
            result_status=MappingResultStatus.UNRESOLVED,
            selection_method=None,
            selected_sdwan_entity_id=None,
            created_at=get_utc_now(),
            candidates=[],
        )

    @classmethod
    def create_ambiguous(
        cls,
        *,
        mapping_scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
        candidates_payloads: list[MappingEntityCandidatePayload],
    ) -> Self:
        result_id = uuid4()

        cz_id, co_id = cls._resolve_canonical_ids_fields(
            entity_type, canonical_entity_id
        )

        return cls(
            id=result_id,
            mapping_scope_id=mapping_scope_id,
            entity_type=entity_type,
            canonical_zone_id=cz_id,
            canonical_object_id=co_id,
            result_status=MappingResultStatus.AMBIGUOUS,
            selection_method=None,
            selected_sdwan_entity_id=None,
            created_at=get_utc_now(),
            candidates=[
                MappingEntityCandidate.create(
                    result_id=result_id,
                    rank=cp.rank,
                    score=cp.score,
                    strategy=cp.strategy,
                    sdwan_entity_id=cp.sdwan_entity_id,
                )
                for cp in candidates_payloads
            ],
        )

    @classmethod
    def create_matched_auto(
        cls,
        *,
        mapping_scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
        candidate_payload: MappingEntityCandidatePayload,
    ) -> Self:
        result_id = uuid4()

        cz_id, co_id = cls._resolve_canonical_ids_fields(
            entity_type, canonical_entity_id
        )

        return cls(
            id=result_id,
            mapping_scope_id=mapping_scope_id,
            entity_type=entity_type,
            canonical_zone_id=cz_id,
            canonical_object_id=co_id,
            result_status=MappingResultStatus.MATCHED,
            selection_method=SdwanObjectSelectionMethod.AUTO_SELECTED,
            selected_sdwan_entity_id=candidate_payload.sdwan_entity_id,
            created_at=get_utc_now(),
            candidates=[
                MappingEntityCandidate.create(
                    result_id=result_id,
                    rank=candidate_payload.rank,
                    score=candidate_payload.score,
                    strategy=candidate_payload.strategy,
                    sdwan_entity_id=candidate_payload.sdwan_entity_id,
                )
            ],
        )

    @classmethod
    def create_zone_manually_assigned(
        cls,
        *,
        mapping_scope_id: UUID,
        sdwan_zone_id: int,
    ) -> Self:
        result_id = uuid4()

        return cls(
            id=result_id,
            mapping_scope_id=mapping_scope_id,
            entity_type=MappingEntityType.ZONE,
            canonical_zone_id=None,
            canonical_object_id=None,
            result_status=MappingResultStatus.MATCHED,
            selection_method=SdwanObjectSelectionMethod.MANUAL_DIRECT,
            selected_sdwan_entity_id=sdwan_zone_id,
            created_at=get_utc_now(),
        )

    def select_candidate(self, candidate: MappingEntityCandidate) -> Self:
        """Select one of stored candidates manually."""
        if candidate.result_id != self.id:
            raise ValueError("Candidate does not belong to this mapping result")

        return replace(
            self,
            result_status=MappingResultStatus.MATCHED,
            selection_method=SdwanObjectSelectionMethod.MANUAL_CANDIDATE,
            selected_sdwan_entity_id=candidate.sdwan_entity_id,
        )

    def select_direct(self, sdwan_entity_id: int) -> Self:
        """Select SD-WAN entity directly, not from candidate list."""
        return replace(
            self,
            result_status=MappingResultStatus.MATCHED,
            selection_method=SdwanObjectSelectionMethod.MANUAL_DIRECT,
            selected_sdwan_entity_id=sdwan_entity_id,
        )

    def select_created(self, sdwan_entity_id: int) -> Self:
        """
        Select by object creation flow.

        Used when migration tool creates missing SD-WAN object and then stores
        created SD-WAN id as selected mapping result.
        """
        return replace(
            self,
            result_status=MappingResultStatus.MATCHED,
            selection_method=SdwanObjectSelectionMethod.AUTO_CREATED,
            selected_sdwan_entity_id=sdwan_entity_id,
        )
