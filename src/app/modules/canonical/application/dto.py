"""Use-case projection DTOs for canonical read and write flows.

Mirrored by canonical/http/schemas.py for HTTP responses.
Mapping consumes DTOs via GetCanonicalRuleScopeUseCase without going through HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.canonical.domain.enums import (
    ObjectFamily,
    ObjectKind,
    OperandRole,
    SnapshotStatus,
)


@dataclass(slots=True)
class CanonicalSnapshotDTO:
    """Snapshot header with aggregate counts."""

    id: UUID
    source_snapshot_id: UUID
    normalizer_code: str
    normalizer_version: str
    status: SnapshotStatus
    zones_total: int
    objects_total: int
    rules_total: int
    issues_total: int
    created_at: datetime


@dataclass(slots=True)
class CanonicalZoneDTO:
    """Zone catalog entry."""

    id: UUID
    canonical_snapshot_id: UUID
    zone_key: str
    name: str
    direction_hint: str | None = None
    description: str | None = None


@dataclass(slots=True)
class CanonicalObjectDTO:
    """Address or service object.

    parent_ids is populated after group BFS in rule_scope; empty in
    list/detail endpoints unless explicitly set by the mapper.
    """

    id: UUID
    canonical_snapshot_id: UUID
    object_key: str
    object_family: ObjectFamily
    object_kind: ObjectKind
    name: str
    parent_id: UUID | None = None
    parent_ids: tuple[UUID, ...] = ()
    ip_version: int | None = None
    cidr: str | None = None
    range_start: str | None = None
    range_end: str | None = None
    fqdn: str | None = None
    protocol: str | None = None
    port_from: int | None = None
    port_to: int | None = None
    icmp_type: int | None = None
    icmp_code: int | None = None
    description: str | None = None


@dataclass(slots=True)
class CanonicalRuleOperandDTO:
    """Flat rule operand referencing zone or object by ID."""

    id: UUID
    rule_id: UUID
    operand_role: OperandRole
    target_zone_id: UUID | None
    target_object_id: UUID | None
    position: int


@dataclass(slots=True)
class CanonicalZoneSummaryDTO:
    """Compact zone projection embedded in hydrated operands."""

    id: UUID
    zone_key: str
    name: str


@dataclass(slots=True)
class CanonicalObjectSummaryDTO:
    """Compact object projection embedded in hydrated operands."""

    id: UUID
    object_key: str
    object_family: ObjectFamily
    object_kind: ObjectKind
    name: str


@dataclass(slots=True)
class CanonicalRuleOperandHydratedDTO(CanonicalRuleOperandDTO):
    """Operand with resolved zone/object summaries (rule detail only)."""

    target_zone: CanonicalZoneSummaryDTO | None = None
    target_object: CanonicalObjectSummaryDTO | None = None


@dataclass(slots=True)
class CanonicalRuleDTO:
    """Rule with optional operand list (flat or hydrated)."""

    id: UUID
    canonical_snapshot_id: UUID
    rule_key: str
    name: str
    action: str
    enabled: bool
    priority: int
    section: str | None = None
    description: str | None = None
    operands: list[CanonicalRuleOperandDTO] | None = None


@dataclass(slots=True)
class PaginationDTO:
    """Pagination metadata for rule_scope; limit=None means return all."""

    limit: int | None
    offset: int | None
    total: int


@dataclass(slots=True)
class CanonicalIssueDTO:
    """Normalizer issue linked to a snapshot."""

    id: UUID
    canonical_snapshot_id: UUID
    entity_type: str
    entity_key: str | None
    issue_code: str
    message: str
    source_line_start: int | None
    source_line_end: int | None
    created_at: datetime
