from dataclasses import dataclass
from uuid import UUID

from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappedRuleStatus,
    MappingEntityType,
    MappingResultStatus,
    MappingScopeRuleAction,
    SdwanObjectSelectionMethod,
)
from app.modules.mapping.ports.canonical_reader.schemas import CanonicalRuleAction


@dataclass(frozen=True, slots=True)
class MappingResultsSummary:

    total_entities: int
    matched_entities: int
    ambiguous: int
    unresolved: int
    zones_total: int
    zones_matched: int
    addr_total: int
    addr_matched: int
    services_total: int
    services_matched: int


# -- Display canonical, mapping tables DTO
@dataclass(frozen=True, slots=True)
class CanonicalEntityDisplayDTO:
    """
    Display-only canonical entity row for policy preview/details.

    canonical_id is None only for synthetic rows. parent_name is filled for
    group members so UI can render nested groups without knowing canonical's
    storage model.
    """

    canonical_id: UUID | None
    parent_name: str | None
    name: str
    type: str
    str_value: str | None


@dataclass(frozen=True, slots=True)
class MappedSdwanEntityDisplayDTO:
    """
    Display-only SD-WAN full entity row for policy preview/details
    with mapping details.

    name/type/str_value/selection_method are None when mapping result exists but no concrete
    SD-WAN entity is selected yet, for example unresolved or ambiguous result.
    """

    mapping_result_id: UUID | None
    match_status: MappingResultStatus
    selection_method: SdwanObjectSelectionMethod | None
    sdwan_id: int | None
    name: str | None
    type: str | None
    str_value: str | None


@dataclass(frozen=True, slots=True)
class CanonicalRuleDisplayDTO:
    """Top-level canonical policy row for UI table."""

    canonical_rule_id: UUID
    name: str
    action: CanonicalRuleAction

    src_zones: list[CanonicalEntityDisplayDTO]
    dst_zones: list[CanonicalEntityDisplayDTO]

    src_addr_objects: list[CanonicalEntityDisplayDTO]
    dst_addr_objects: list[CanonicalEntityDisplayDTO]

    services: list[CanonicalEntityDisplayDTO]


@dataclass(frozen=True, slots=True)
class MappingScopeRuleDisplayDTO:
    """Top-level mapped policy row aligned with CanonicalRuleDisplayDTO."""

    mapping_scope_rule_id: UUID
    canonical_rule_id: UUID
    name: str
    action: MappingScopeRuleAction
    status: MappedRuleStatus

    src_zones: list[MappedSdwanEntityDisplayDTO]
    dst_zones: list[MappedSdwanEntityDisplayDTO]

    src_addr_objects: list[MappedSdwanEntityDisplayDTO]
    dst_addr_objects: list[MappedSdwanEntityDisplayDTO]

    services: list[MappedSdwanEntityDisplayDTO]


# -- paired canonical-mapping view DTO
@dataclass(frozen=True, slots=True)
class CanonicalToSdwanEntityProjectionDTO:
    """
    One display row in policy details.

    canonical is None for manually assigned mapping operands that do not come
    from canonical policy, for example assigned WAN/LAN zones.
    sdwan is None for canonical group placeholder rows because SD-WAN groups are
    not used in mapped rules.
    """

    canonical: CanonicalEntityDisplayDTO | None
    sdwan: MappedSdwanEntityDisplayDTO | None


@dataclass(frozen=True, slots=True)
class MappingCanonicalRuleProjectionDTO:
    """Expanded per-role policy details for selected UI row."""

    mapping_scope_rule_id: UUID
    canonical_rule_id: UUID
    name: str
    action: MappingScopeRuleAction
    status: MappedRuleStatus

    src_zones: list[CanonicalToSdwanEntityProjectionDTO]
    dst_zones: list[CanonicalToSdwanEntityProjectionDTO]

    src_addr_objects: list[CanonicalToSdwanEntityProjectionDTO]
    dst_addr_objects: list[CanonicalToSdwanEntityProjectionDTO]

    services: list[CanonicalToSdwanEntityProjectionDTO]


@dataclass(frozen=True, slots=True)
class MappingScopeRulesProjectionDTO:
    """
    Full UI projection for mapping scope rules.

    canonical_rules and mapped_rules are aligned by index. details_by_rule_id is
    keyed by mapping_scope_rule_id for expand-on-select UI behaviour.
    """

    mapping_scope_id: UUID
    canonical_snapshot_id: UUID
    sdwan_target_id: str

    canonical_rules: list[CanonicalRuleDisplayDTO]
    mapped_rules: list[MappingScopeRuleDisplayDTO]
    details_by_rule_id: dict[UUID, MappingCanonicalRuleProjectionDTO]


# -- mapping result details for UI candidate/direct editors
@dataclass(frozen=True, slots=True)
class MappingEntityCandidateDisplayDTO:
    candidate_id: UUID
    rank: int
    score: int
    strategy: CandidateMatchStrategy
    sdwan_id: int
    name: str
    type: str
    str_value: str


@dataclass(frozen=True, slots=True)
class MappingEntityResultDetailsDTO:
    mapping_result_id: UUID
    mapping_scope_id: UUID
    entity_type: MappingEntityType
    canonical_entity_id: UUID | None
    match_status: MappingResultStatus
    selection_method: SdwanObjectSelectionMethod | None
    selected_sdwan: MappedSdwanEntityDisplayDTO | None
    candidates: list[MappingEntityCandidateDisplayDTO]
