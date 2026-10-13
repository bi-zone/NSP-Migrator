from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.modules.canonical.application.mappers import (
    object_to_dto,
    operands_by_rule,
    rule_to_dto,
    snapshot_to_dto,
    zone_to_dto,
)
from app.modules.canonical.domain import (
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalSnapshot,
    CanonicalZone,
    ObjectFamily,
    ObjectKind,
    OperandRole,
    SnapshotStatus,
)
from app.modules.canonical.domain.object import CanonicalObject


def test_snapshot_to_dto_maps_all_fields() -> None:
    snapshot_id = uuid4()
    source_snapshot_id = uuid4()
    created_at = datetime.now(UTC)
    entity = CanonicalSnapshot(
        id=snapshot_id,
        source_snapshot_id=source_snapshot_id,
        normalizer_code="cisco_asa",
        normalizer_version="1",
        status=SnapshotStatus.SUCCESS,
        zones_total=1,
        objects_total=2,
        rules_total=3,
        issues_total=4,
        created_at=created_at,
    )

    dto = snapshot_to_dto(entity)

    assert dto.id == snapshot_id
    assert dto.source_snapshot_id == source_snapshot_id
    assert dto.status == SnapshotStatus.SUCCESS
    assert dto.created_at == created_at


def test_zone_and_object_mappers_preserve_identity_fields() -> None:
    snapshot_id = uuid4()
    zone = CanonicalZone.create(
        canonical_snapshot_id=snapshot_id,
        zone_key="inside",
        name="inside",
    )
    obj = CanonicalObject.create(
        canonical_snapshot_id=snapshot_id,
        object_key="host-1",
        object_family=ObjectFamily.ADDR,
        object_kind=ObjectKind.HOST,
        name="host-1",
        cidr="10.0.0.1/32",
    )

    zone_dto = zone_to_dto(zone)
    object_dto = object_to_dto(obj, parent_ids=(uuid4(),))

    assert zone_dto.zone_key == "inside"
    assert object_dto.object_kind == ObjectKind.HOST
    assert object_dto.parent_ids


def test_operands_by_rule_groups_operands_per_rule() -> None:
    snapshot_id = uuid4()
    rule_a = CanonicalRule.create(
        canonical_snapshot_id=snapshot_id,
        rule_key="rule-a",
        name="rule-a",
        action="permit",
        enabled=True,
        priority=10,
    )
    rule_b = CanonicalRule.create(
        canonical_snapshot_id=snapshot_id,
        rule_key="rule-b",
        name="rule-b",
        action="deny",
        enabled=True,
        priority=20,
    )
    operands = [
        CanonicalRuleOperand.create(
            rule_id=rule_a.id,
            operand_role=OperandRole.SRC_OBJECT,
            target_object_id=uuid4(),
            position=0,
        ),
        CanonicalRuleOperand.create(
            rule_id=rule_b.id,
            operand_role=OperandRole.SERVICE,
            target_object_id=uuid4(),
            position=0,
        ),
        CanonicalRuleOperand.create(
            rule_id=rule_a.id,
            operand_role=OperandRole.DST_OBJECT,
            target_object_id=uuid4(),
            position=1,
        ),
    ]

    grouped = operands_by_rule(operands)

    assert len(grouped[rule_a.id]) == 2
    assert len(grouped[rule_b.id]) == 1
    assert rule_to_dto(rule_a, operands=grouped[rule_a.id]).operands is not None
