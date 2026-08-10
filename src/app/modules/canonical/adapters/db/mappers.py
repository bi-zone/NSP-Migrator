"""Map domain entities to SQLAlchemy models and back.
Each entity has paired *_to_model/*_to_entity functions used by
adapters/db/*_repository.py.
"""

from app.modules.canonical.adapters.db import models
from app.modules.canonical.domain import (
    CanonicalIssue,
    CanonicalObject,
    CanonicalObjectMember,
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalSnapshot,
    CanonicalZone,
    ObjectFamily,
    ObjectKind,
    OperandRole,
    SnapshotStatus,
)


# TODO:: add generic model_validate-style mapper when entity/model fields are 1:1.
def snapshot_to_model(entity: CanonicalSnapshot) -> models.CanonicalSnapshotModel:
    return models.CanonicalSnapshotModel(
        id=entity.id,
        source_snapshot_id=entity.source_snapshot_id,
        normalizer_code=entity.normalizer_code,
        normalizer_version=entity.normalizer_version,
        status=entity.status.value,
        zones_total=entity.zones_total,
        objects_total=entity.objects_total,
        rules_total=entity.rules_total,
        issues_total=entity.issues_total,
    )


def snapshot_to_entity(model: models.CanonicalSnapshotModel) -> CanonicalSnapshot:
    return CanonicalSnapshot(
        id=model.id,
        source_snapshot_id=model.source_snapshot_id,
        normalizer_code=model.normalizer_code,
        normalizer_version=model.normalizer_version,
        status=SnapshotStatus(model.status),
        zones_total=model.zones_total,
        objects_total=model.objects_total,
        rules_total=model.rules_total,
        issues_total=model.issues_total,
        created_at=model.created_at,
    )


def issue_to_model(entity: CanonicalIssue) -> models.CanonicalIssueModel:
    return models.CanonicalIssueModel(
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


def issue_to_entity(model: models.CanonicalIssueModel) -> CanonicalIssue:
    return CanonicalIssue(
        id=model.id,
        canonical_snapshot_id=model.canonical_snapshot_id,
        entity_type=model.entity_type,
        entity_key=model.entity_key,
        issue_code=model.issue_code,
        message=model.message,
        source_line_start=model.source_line_start,
        source_line_end=model.source_line_end,
        created_at=model.created_at,
    )


def zone_to_model(entity: CanonicalZone) -> models.CanonicalZoneModel:
    return models.CanonicalZoneModel(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        zone_key=entity.zone_key,
        name=entity.name,
        direction_hint=entity.direction_hint,
        description=entity.description,
    )


def zone_to_entity(model: models.CanonicalZoneModel) -> CanonicalZone:
    return CanonicalZone(
        id=model.id,
        canonical_snapshot_id=model.canonical_snapshot_id,
        zone_key=model.zone_key,
        name=model.name,
        direction_hint=model.direction_hint,
        description=model.description,
    )


def object_to_model(entity: CanonicalObject) -> models.CanonicalObjectModel:
    return models.CanonicalObjectModel(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        object_key=entity.object_key,
        object_family=entity.object_family.value,
        object_kind=entity.object_kind.value,
        name=entity.name,
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


def object_to_entity(model: models.CanonicalObjectModel) -> CanonicalObject:
    return CanonicalObject(
        id=model.id,
        canonical_snapshot_id=model.canonical_snapshot_id,
        object_key=model.object_key,
        object_family=ObjectFamily(model.object_family),
        object_kind=ObjectKind(model.object_kind),
        name=model.name,
        ip_version=model.ip_version,
        cidr=model.cidr,
        range_start=model.range_start,
        range_end=model.range_end,
        fqdn=model.fqdn,
        protocol=model.protocol,
        port_from=model.port_from,
        port_to=model.port_to,
        icmp_type=model.icmp_type,
        icmp_code=model.icmp_code,
        description=model.description,
    )


def object_member_to_model(
    entity: CanonicalObjectMember,
) -> models.CanonicalObjectMemberModel:
    return models.CanonicalObjectMemberModel(
        id=entity.id,
        parent_object_id=entity.parent_object_id,
        child_object_id=entity.child_object_id,
        position=entity.position,
    )


def object_member_to_entity(
    model: models.CanonicalObjectMemberModel,
) -> CanonicalObjectMember:
    return CanonicalObjectMember(
        id=model.id,
        parent_object_id=model.parent_object_id,
        child_object_id=model.child_object_id,
        position=model.position,
    )


def rule_to_model(entity: CanonicalRule) -> models.CanonicalRuleModel:
    return models.CanonicalRuleModel(
        id=entity.id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        rule_key=entity.rule_key,
        name=entity.name,
        action=entity.action,
        enabled=entity.enabled,
        priority=entity.priority,
        section=entity.section,
        description=entity.description,
    )


def rule_to_entity(model: models.CanonicalRuleModel) -> CanonicalRule:
    return CanonicalRule(
        id=model.id,
        canonical_snapshot_id=model.canonical_snapshot_id,
        rule_key=model.rule_key,
        name=model.name,
        action=model.action,
        enabled=model.enabled,
        priority=model.priority,
        section=model.section,
        description=model.description,
    )


def operand_to_model(entity: CanonicalRuleOperand) -> models.CanonicalRuleOperandModel:
    return models.CanonicalRuleOperandModel(
        id=entity.id,
        rule_id=entity.rule_id,
        operand_role=entity.operand_role.value,
        target_zone_id=entity.target_zone_id,
        target_object_id=entity.target_object_id,
        position=entity.position,
    )


def operand_to_entity(model: models.CanonicalRuleOperandModel) -> CanonicalRuleOperand:
    return CanonicalRuleOperand(
        id=model.id,
        rule_id=model.rule_id,
        operand_role=OperandRole(model.operand_role),
        target_zone_id=model.target_zone_id,
        target_object_id=model.target_object_id,
        position=model.position,
    )
