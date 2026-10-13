"""Unit coverage for trace DTO and persistence mappers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.modules.trace.adapters.db.mappers import record_to_entity, record_to_model
from app.modules.trace.application.dto import TraceRecordDTO
from app.modules.trace.domain.enums import TraceCanonicalKind, TraceCanonicalRole
from app.modules.trace.domain.record import TraceRawToCanonicalRecord


def _record() -> TraceRawToCanonicalRecord:
    return TraceRawToCanonicalRecord(
        id=uuid4(),
        source_snapshot_id=uuid4(),
        canonical_snapshot_id=uuid4(),
        vendor_code="cisco_asa",
        normalizer_code="cisco_asa",
        normalizer_version="1",
        source_line_start=20,
        source_line_end=23,
        source_fragment="object network OBJ_APP\n host 10.0.0.1",
        canonical_kind=TraceCanonicalKind.OBJECT,
        canonical_id=uuid4(),
        canonical_role=TraceCanonicalRole.HEADER.value,
        note="header",
        created_at=datetime.now(UTC),
    )


def test_trace_record_dto_from_entity_serializes_kind_as_value() -> None:
    entity = _record()

    dto = TraceRecordDTO.from_entity(entity)

    assert dto.id == entity.id
    assert dto.canonical_kind == TraceCanonicalKind.OBJECT.value
    assert dto.canonical_role == TraceCanonicalRole.HEADER.value
    assert dto.source_line_start == 20
    assert dto.source_line_end == 23
    assert dto.source_fragment == entity.source_fragment


def test_record_to_model_and_back_preserves_fields() -> None:
    entity = _record()

    model = record_to_model(entity)
    # created_at is server-default on insert; set it for roundtrip without a session
    model.created_at = entity.created_at
    restored = record_to_entity(model)

    assert restored.id == entity.id
    assert restored.source_snapshot_id == entity.source_snapshot_id
    assert restored.canonical_snapshot_id == entity.canonical_snapshot_id
    assert restored.vendor_code == entity.vendor_code
    assert restored.normalizer_code == entity.normalizer_code
    assert restored.normalizer_version == entity.normalizer_version
    assert restored.source_line_start == entity.source_line_start
    assert restored.source_line_end == entity.source_line_end
    assert restored.source_fragment == entity.source_fragment
    assert restored.canonical_kind == entity.canonical_kind
    assert restored.canonical_id == entity.canonical_id
    assert restored.canonical_role == entity.canonical_role
    assert restored.note == entity.note
    assert restored.created_at == entity.created_at
    assert model.canonical_kind == TraceCanonicalKind.OBJECT.value
