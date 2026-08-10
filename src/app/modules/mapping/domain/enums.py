from enum import StrEnum


class MappingEntityType(StrEnum):
    """
    Canonical entity type processed by mapping module.

    zone:
        Canonical zone from canonical_zone table.

    addr:
        Canonical address object from canonical_object table.

    service:
        Canonical service object from canonical_object table.
    """

    ZONE = "zone"
    ADDR = "addr"
    SERVICE = "service"


class MappingResultStatus(StrEnum):
    """
    Result of processing one canonical entity inside one mapping scope.

    matched:
        SD-WAN id is selected.

    ambiguous:
        More than one candidate exists, but no final selection was made.

    unresolved:
        Entity was processed, but no candidate/match was found.
    """

    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class SdwanObjectSelectionMethod(StrEnum):
    """
    Explains how SD-WAN id was selected.

    auto_selected:
        Mapper selected one candidate automatically.

    manual_candidate:
        User selected one of candidates produced by mapper.

    manual_direct:
        User selected SD-WAN entity directly.

    auto_created:
        SD-WAN entity was created by migration tool and then selected.
    """

    AUTO_SELECTED = "auto_selected"
    MANUAL_CANDIDATE = "manual_candidate"
    MANUAL_DIRECT = "manual_direct"
    AUTO_CREATED = "auto_created"


class CandidateMatchStrategy(StrEnum):
    """Matching strategy that produced a candidate."""

    NORMALIZED_NAME = "normalized_name"
    EXACT_VALUE = "exact_value"
    BUILTIN_ANY = "builtin_any"
    SERVICE_ALIAS = "service_alias"
    SERVICE_SIGNATURE = "service_signature"


class SDWANZoneDirection(StrEnum):
    """Zone directions for auto-assign select"""

    SRC_ZONE = "src_zone"
    DST_ZONE = "dst_zone"


class MappedRuleStatus(StrEnum):
    """
    Aggregated mapping status for one policy/rule preview.

    MAPPED:
        All operands are mapped to selected SD-WAN entities.

    AMBIGUOUS:
        No unresolved operands, but at least one operand has multiple candidates.

    PARTIAL:
        Some operands are mapped, but some are unresolved/missing/ambiguous.

    UNRESOLVED:
        No useful complete mapping can be built.
    """

    MAPPED = "mapped"
    AMBIGUOUS = "ambiguous"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class MappedRuleOperandStatus(StrEnum):
    """
    Mapping status for one rule operand.
    """

    MAPPED = "mapped"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"

    GROUP_PLACEHOLDER = "group_placeholder"  # for groups now


class MappingScopeRuleOperandRole(StrEnum):
    """Operand of mapped rule"""

    SRC_ZONE = "src_zone"
    DST_ZONE = "dst_zone"
    SRC_ADDR_OBJECT = "src_addr_object"
    DST_ADDR_OBJECT = "dst_addr_object"
    SERVICE = "service"


class MappingScopeRuleAction(StrEnum):
    """Enum as in SD-WAN, will be mapped from canonical"""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
