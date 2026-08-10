"""OpenAPI response models for canonical read endpoints.

These schemas mirror application/dto.py projections exposed by
canonical/http/routers/.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# TODO:: Think about mirroring
from app.modules.canonical.domain.enums import (
    ObjectFamily,
    ObjectKind,
    OperandRole,
    SnapshotStatus,
)


class CanonicalSnapshotResponse(BaseModel):
    """Snapshot header with aggregate counts (no zones/objects/rules payload)."""

    id: UUID = Field(description="Canonical snapshot identifier.")
    source_snapshot_id: UUID = Field(
        description="Upstream imports snapshot that produced this canonical snapshot."
    )
    normalizer_code: str = Field(
        description="Normalizer identifier (for example cisco_asa)."
    )
    normalizer_version: str = Field(
        description="Normalizer version used when the snapshot was materialized."
    )
    status: SnapshotStatus = Field(
        description="Snapshot lifecycle status (see domain.enums.SnapshotStatus)."
    )
    zones_total: int = Field(description="Total zone count stored for this snapshot.")
    objects_total: int = Field(description="Total object count stored for this snapshot.")
    rules_total: int = Field(description="Total rule count stored for this snapshot.")
    issues_total: int = Field(
        description="Total normalizer issue count linked to this snapshot."
    )
    created_at: datetime = Field(
        description="UTC timestamp when the canonical snapshot was created."
    )

    model_config = {"from_attributes": True}


class CanonicalZoneResponse(BaseModel):
    """Zone catalog entry for a snapshot."""

    id: UUID = Field(description="Canonical zone identifier.")
    canonical_snapshot_id: UUID = Field(description="Owner canonical snapshot identifier.")
    zone_key: str = Field(description="Stable zone key within the snapshot.")
    name: str = Field(description="Human-readable zone name.")
    direction_hint: str | None = Field(
        default=None,
        description="Optional direction hint from the source normalizer.",
    )
    description: str | None = Field(
        default=None,
        description="Optional free-form zone description from source config.",
    )

    model_config = {"from_attributes": True}


class CanonicalObjectResponse(BaseModel):
    """Address or service object; list and scope endpoints return this shape."""

    id: UUID = Field(description="Canonical object identifier.")
    canonical_snapshot_id: UUID = Field(description="Owner canonical snapshot identifier.")
    object_key: str = Field(description="Stable object key within the snapshot.")
    object_family: ObjectFamily = Field(
        description="Object family: address or service (see domain.enums.ObjectFamily)."
    )
    object_kind: ObjectKind = Field(
        description="Concrete object kind, including group kinds (see domain.enums.ObjectKind)."
    )
    name: str = Field(description="Human-readable object name.")
    parent_id: UUID | None = Field(
        default=None,
        description="Direct parent group ID when object is a group member; null for roots.",
    )
    parent_ids: list[UUID] = Field(
        default_factory=list,
        description=(
            "Transitive parent group IDs after BFS expansion in rule_scope; "
            "empty for leaf objects in list/detail endpoints."
        ),
    )
    ip_version: int | None = Field(
        default=None, description="IP version for address objects (4 or 6)."
    )
    cidr: str | None = Field(default=None, description="CIDR notation for host/network objects.")
    range_start: str | None = Field(
        default=None, description="Range start for address-range objects."
    )
    range_end: str | None = Field(
        default=None, description="Range end for address-range objects."
    )
    fqdn: str | None = Field(default=None, description="FQDN for DNS-based address objects.")
    protocol: str | None = Field(
        default=None, description="Protocol for service objects (tcp, udp, icmp, ...)."
    )
    port_from: int | None = Field(default=None, description="Inclusive service port lower bound.")
    port_to: int | None = Field(default=None, description="Inclusive service port upper bound.")
    icmp_type: int | None = Field(default=None, description="ICMP type for icmp service objects.")
    icmp_code: int | None = Field(default=None, description="ICMP code for icmp service objects.")
    description: str | None = Field(
        default=None, description="Optional free-form object description from source config."
    )

    model_config = {"from_attributes": True}


class CanonicalRuleOperandResponse(BaseModel):
    """Flat rule operand referencing zone or object by ID (list/scope views)."""

    id: UUID = Field(description="Operand row identifier.")
    rule_id: UUID = Field(description="Owner rule identifier.")
    operand_role: OperandRole = Field(
        description="Operand role: src/dst zone, src/dst object, service (see OperandRole)."
    )
    target_zone_id: UUID | None = Field(
        default=None, description="Referenced zone ID when operand role is zone-based."
    )
    target_object_id: UUID | None = Field(
        default=None, description="Referenced object ID when operand role is object/service."
    )
    position: int = Field(description="Operand ordering within the rule.")

    model_config = {"from_attributes": True}


class CanonicalZoneSummaryResponse(BaseModel):
    """Compact zone projection embedded in hydrated rule operands."""

    id: UUID = Field(description="Canonical zone identifier.")
    zone_key: str = Field(description="Stable zone key within the snapshot.")
    name: str = Field(description="Human-readable zone name.")


class CanonicalObjectSummaryResponse(BaseModel):
    """Compact object projection embedded in hydrated rule operands."""

    id: UUID = Field(description="Canonical object identifier.")
    object_key: str = Field(description="Stable object key within the snapshot.")
    object_family: ObjectFamily = Field(description="Object family: address or service.")
    object_kind: ObjectKind = Field(description="Concrete object kind.")
    name: str = Field(description="Human-readable object name.")


class CanonicalRuleOperandHydratedResponse(CanonicalRuleOperandResponse):
    """Rule operand with resolved zone/object summaries (rule detail endpoint only)."""

    target_zone: CanonicalZoneSummaryResponse | None = Field(
        default=None,
        description="Resolved zone summary when target_zone_id is set.",
    )
    target_object: CanonicalObjectSummaryResponse | None = Field(
        default=None,
        description="Resolved object summary when target_object_id is set.",
    )


class CanonicalObjectMemberResponse(BaseModel):
    """Group membership edge: parent group to child object."""

    id: UUID = Field(description="Membership row identifier.")
    parent_object_id: UUID = Field(description="Parent group object identifier.")
    child_object_id: UUID = Field(description="Child member object identifier.")
    position: int = Field(description="Member ordering within the parent group.")

    model_config = {"from_attributes": True}


class CanonicalObjectDetailResponse(BaseModel):
    """Object detail with group members (object detail endpoint)."""

    object: CanonicalObjectResponse = Field(description="The requested object.")
    members: list[CanonicalObjectMemberResponse] = Field(
        default_factory=list,
        description="Ordered group members; empty for non-group objects.",
    )


class CanonicalRuleCoreResponse(BaseModel):
    """Rule metadata without operands (detail view exposes operands separately)."""

    id: UUID = Field(description="Canonical rule identifier.")
    canonical_snapshot_id: UUID = Field(description="Owner canonical snapshot identifier.")
    rule_key: str = Field(description="Stable rule key within the snapshot.")
    name: str = Field(description="Human-readable rule name.")
    action: str = Field(description="Rule action from source normalizer (permit, deny, ...).")
    enabled: bool = Field(description="Whether the rule is enabled in source config.")
    priority: int = Field(description="Rule ordering priority within its section.")
    section: str | None = Field(
        default=None, description="ACL section or policy block name from source config."
    )
    description: str | None = Field(
        default=None, description="Optional free-form rule description from source config."
    )

    model_config = {"from_attributes": True}


class CanonicalRuleDetailResponse(BaseModel):
    """Single rule with hydrated operands (rule detail endpoint)."""

    rule: CanonicalRuleCoreResponse = Field(description="Rule metadata without nested operands.")
    operands: list[CanonicalRuleOperandHydratedResponse] = Field(
        default_factory=list,
        description="Operands with resolved zone/object summaries for UI display.",
    )


class CanonicalRuleResponse(BaseModel):
    """Rule with flat operand IDs (list and rule_scope endpoints)."""

    id: UUID = Field(description="Canonical rule identifier.")
    canonical_snapshot_id: UUID = Field(description="Owner canonical snapshot identifier.")
    rule_key: str = Field(description="Stable rule key within the snapshot.")
    name: str = Field(description="Human-readable rule name.")
    action: str = Field(description="Rule action from source normalizer.")
    enabled: bool = Field(description="Whether the rule is enabled in source config.")
    priority: int = Field(description="Rule ordering priority within its section.")
    section: str | None = Field(default=None, description="ACL section or policy block name.")
    description: str | None = Field(
        default=None, description="Optional free-form rule description."
    )
    operands: list[CanonicalRuleOperandResponse] = Field(
        default_factory=list,
        description="Flat operands referencing zones/objects by ID only.",
    )

    model_config = {"from_attributes": True}


class PaginationResponse(BaseModel):
    """Pagination metadata for rule_scope responses."""

    limit: int | None = Field(
        default=None,
        description="Requested page size; null means return all matching rules.",
    )
    offset: int | None = Field(
        default=None,
        description="Requested row offset; null treated as zero by the use case.",
    )
    total: int = Field(description="Total rules matching filters before pagination slice.")

    # TODO: extract shared model_config into a BaseResponseSchema if more models need it.
    model_config = {"from_attributes": True}


class CanonicalRuleScopeResponse(BaseModel):
    """Composite projection for mapping: filtered rules plus referenced zones/objects."""

    rules: list[CanonicalRuleResponse] = Field(
        description="Rules matching filters (paginated when limit/offset are set)."
    )
    zones: list[CanonicalZoneResponse] = Field(
        description=(
            "Zones referenced by returned rules, or all snapshot zones when "
            "include_all_zones is true."
        )
    )
    objects: list[CanonicalObjectResponse] = Field(
        description=(
            "Objects referenced by returned rules, with transitive group expansion "
            "applied (parent_ids populated)."
        )
    )
    pagination: PaginationResponse = Field(
        description="Pagination totals for the rules slice."
    )

    model_config = {"from_attributes": True}


class CanonicalIssueResponse(BaseModel):
    """Normalizer issue emitted during canonical snapshot materialization."""

    id: UUID = Field(description="Issue row identifier.")
    canonical_snapshot_id: UUID = Field(description="Owner canonical snapshot identifier.")
    entity_type: str = Field(
        description="Entity type the issue relates to (rule, object, zone, ...)."
    )
    entity_key: str | None = Field(
        default=None, description="Stable entity key when available."
    )
    issue_code: str = Field(
        description="Stable issue code consumed by UI and diagnostics tooling."
    )
    message: str = Field(description="Human-readable issue description.")
    source_line_start: int | None = Field(
        default=None, description="Inclusive source config line start for traceability."
    )
    source_line_end: int | None = Field(
        default=None, description="Inclusive source config line end for traceability."
    )
    created_at: datetime = Field(description="UTC timestamp when the issue was recorded.")

    model_config = {"from_attributes": True}
