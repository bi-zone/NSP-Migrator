"""Map domain entities to application DTOs for read use cases and HTTP.

This is the **application layer** boundary: entity -> DTO consumed by use cases
and http/schemas.py.
For persistence mapping (entity <-> SQLAlchemy model)
see adapters/db/mappers.py.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from app.modules.canonical.application.dto import (
    CanonicalIssueDTO,
    CanonicalObjectDTO,
    CanonicalObjectSummaryDTO,
    CanonicalRuleDTO,
    CanonicalRuleOperandDTO,
    CanonicalSnapshotDTO,
    CanonicalZoneDTO,
    CanonicalZoneSummaryDTO,
)
from app.modules.canonical.domain import (
    CanonicalIssue,
    CanonicalObject,
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalSnapshot,
    CanonicalZone,
)


def snapshot_to_dto(entity: CanonicalSnapshot) -> CanonicalSnapshotDTO:
    """Map snapshot entity to DTO; used by list/get snapshot use cases."""
    return CanonicalSnapshotDTO(
        id=entity.id,
        source_snapshot_id=entity.source_snapshot_id,
        normalizer_code=entity.normalizer_code,
        normalizer_version=entity.normalizer_version,
        status=entity.status,
        zones_total=entity.zones_total,
        objects_total=entity.objects_total,
        rules_total=entity.rules_total,
        issues_total=entity.issues_total,
        created_at=entity.created_at,
    )


def zone_to_dto(entity: CanonicalZone) -> CanonicalZoneDTO:
    """Map zone entity to DTO; used by zone list and rule_scope collectors."""
    return CanonicalZoneDTO(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        zone_key=entity.zone_key,
        name=entity.name,
        direction_hint=entity.direction_hint,
        description=entity.description,
    )


def object_to_dto(
    entity: CanonicalObject,
    *,
    parent_id: UUID | None = None,
    parent_ids: tuple[UUID, ...] = (),
) -> CanonicalObjectDTO:
    """Map object entity to DTO.

    parent_id precedence: explicit parent_id arg, else first entry in
    parent_ids (set by GetCanonicalRuleScopeUseCase after group BFS).
    """
    return CanonicalObjectDTO(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        object_key=entity.object_key,
        object_family=entity.object_family,
        object_kind=entity.object_kind,
        name=entity.name,
        parent_id=parent_id if parent_id is not None else (parent_ids[0] if parent_ids else None),
        parent_ids=parent_ids,
        ip_version=entity.ip_version,
        cidr=entity.cidr,
        range_start=entity.range_start,
        range_end=entity.range_end,
        fqdn=entity.fqdn,
        protocol=entity.protocol,
        port_from=entity.port_from,
        port_to=entity.port_to,
        icmp_type=entity.icmp_type,
        icmp_code=entity.icmp_code,
        description=entity.description,
    )


def zone_summary_to_dto(entity: CanonicalZone) -> CanonicalZoneSummaryDTO:
    """Compact zone projection for hydrated rule operands."""
    return CanonicalZoneSummaryDTO(
        id=entity.id,
        zone_key=entity.zone_key,
        name=entity.name,
    )


def object_summary_to_dto(entity: CanonicalObject) -> CanonicalObjectSummaryDTO:
    """Compact object projection for hydrated rule operands."""
    return CanonicalObjectSummaryDTO(
        id=entity.id,
        object_key=entity.object_key,
        object_family=entity.object_family,
        object_kind=entity.object_kind,
        name=entity.name,
    )


def operand_to_dto(entity: CanonicalRuleOperand) -> CanonicalRuleOperandDTO:
    """Map flat rule operand; used by list and scope endpoints."""
    return CanonicalRuleOperandDTO(
        id=entity.id,
        rule_id=entity.rule_id,
        operand_role=entity.operand_role,
        target_zone_id=entity.target_zone_id,
        target_object_id=entity.target_object_id,
        position=entity.position,
    )


def operands_by_rule(
    operands: list[CanonicalRuleOperand],
) -> dict[UUID, list[CanonicalRuleOperandDTO]]:
    """Group flat operand rows by rule_id for batch rule DTO assembly."""
    grouped: dict[UUID, list[CanonicalRuleOperandDTO]] = defaultdict(list)
    for operand in operands:
        grouped[operand.rule_id].append(operand_to_dto(operand))
    return dict(grouped)


def rule_to_dto(
    entity: CanonicalRule,
    *,
    operands: list[CanonicalRuleOperandDTO] | None = None,
) -> CanonicalRuleDTO:
    """Map rule entity to DTO.

    operands is optional: list/scope endpoints attach flat operands;
    detail endpoint attaches hydrated CanonicalRuleOperandHydratedDTO list.
    """
    return CanonicalRuleDTO(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        rule_key=entity.rule_key,
        name=entity.name,
        action=entity.action,
        enabled=entity.enabled,
        priority=entity.priority,
        section=entity.section,
        description=entity.description,
        operands=operands,
    )


def issue_to_dto(entity: CanonicalIssue) -> CanonicalIssueDTO:
    """Map normalizer issue entity to DTO."""
    return CanonicalIssueDTO(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        entity_type=entity.entity_type,
        entity_key=entity.entity_key,
        issue_code=entity.issue_code,
        message=entity.message,
        source_line_start=entity.source_line_start,
        source_line_end=entity.source_line_end,
        created_at=entity.created_at,
    )
