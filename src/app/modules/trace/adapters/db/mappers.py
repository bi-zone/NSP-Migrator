from app.modules.trace.adapters.db import models
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord


def record_to_model(
    entity: TraceRawToCanonicalRecord,
) -> models.TraceRawToCanonicalModel:
    return models.TraceRawToCanonicalModel(
        id=entity.id,
        source_snapshot_id=entity.source_snapshot_id,
        canonical_snapshot_id=entity.canonical_snapshot_id,
        vendor_code=entity.vendor_code,
        normalizer_code=entity.normalizer_code,
        normalizer_version=entity.normalizer_version,
        source_line_start=entity.source_line_start,
        source_line_end=entity.source_line_end,
        source_fragment=entity.source_fragment,
        canonical_kind=entity.canonical_kind.value,
        canonical_id=entity.canonical_id,
        canonical_role=entity.canonical_role,
        note=entity.note,
    )


def record_to_entity(
    model: models.TraceRawToCanonicalModel,
) -> TraceRawToCanonicalRecord:
    return TraceRawToCanonicalRecord(
        id=model.id,
        source_snapshot_id=model.source_snapshot_id,
        canonical_snapshot_id=model.canonical_snapshot_id,
        vendor_code=model.vendor_code,
        normalizer_code=model.normalizer_code,
        normalizer_version=model.normalizer_version,
        source_line_start=model.source_line_start,
        source_line_end=model.source_line_end,
        source_fragment=model.source_fragment,
        canonical_kind=TraceCanonicalKind(model.canonical_kind),
        canonical_id=model.canonical_id,
        canonical_role=model.canonical_role,
        note=model.note,
        created_at=model.created_at,
    )
