from __future__ import annotations

from app.modules.imports.adapters.db.models import (
    ImportSourceModel,
    ImportUploadModel,
    ImportVendorModel,
    SourceArtifactModel,
    SourceSnapshotModel,
)
from app.modules.imports.domain.enums import UploadStatus
from app.modules.imports.domain.import_source import ImportSource
from app.modules.imports.domain.import_upload import ImportUpload
from app.modules.imports.domain.import_vendor import ImportVendor
from app.modules.imports.domain.source_artifact import SourceArtifact
from app.modules.imports.domain.source_snapshot import SourceSnapshot


def import_source_to_model(entity: ImportSource) -> ImportSourceModel:
    return ImportSourceModel(
        id=entity.id,
        vendor_code=entity.vendor_code,
        name=entity.name,
        description=entity.description,
        active=entity.active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def source_snapshot_to_model(entity: SourceSnapshot) -> SourceSnapshotModel:
    return SourceSnapshotModel(
        id=entity.id,
        source_id=entity.source_id,
        artifact_hash=entity.artifact_hash,
        source_format=entity.source_format,
        is_latest=entity.is_latest,
        created_at=entity.created_at,
    )


def source_artifact_to_model(entity: SourceArtifact) -> SourceArtifactModel:
    return SourceArtifactModel(
        snapshot_id=entity.snapshot_id,
        raw_text=entity.raw_text,
        line_count=entity.line_count,
        size_bytes=entity.size_bytes,
        created_at=entity.created_at,
    )


def import_upload_to_model(entity: ImportUpload) -> ImportUploadModel:
    return ImportUploadModel(
        id=entity.id,
        source_id=entity.source_id,
        file_name=entity.file_name,
        uploaded_by=entity.uploaded_by,
        artifact_hash=entity.artifact_hash,
        size_bytes=entity.size_bytes,
        raw_mime_type=entity.raw_mime_type,
        resolved_snapshot_id=entity.resolved_snapshot_id,
        status=entity.status.value,
        created_at=entity.created_at,
        consumed_at=entity.consumed_at,
    )


def import_source_from_model(model: ImportSourceModel) -> ImportSource:
    return ImportSource(
        id=model.id,
        vendor_code=model.vendor_code,
        name=model.name,
        description=model.description,
        active=model.active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def import_vendor_from_model(model: ImportVendorModel) -> ImportVendor:
    return ImportVendor(
        code=model.code,
        display_name=model.display_name,
        active=model.active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def source_snapshot_from_model(model: SourceSnapshotModel) -> SourceSnapshot:
    return SourceSnapshot(
        id=model.id,
        source_id=model.source_id,
        artifact_hash=model.artifact_hash,
        source_format=model.source_format,
        is_latest=model.is_latest,
        created_at=model.created_at,
    )


def source_artifact_from_model(model: SourceArtifactModel) -> SourceArtifact:
    return SourceArtifact(
        snapshot_id=model.snapshot_id,
        raw_text=model.raw_text,
        line_count=model.line_count,
        size_bytes=model.size_bytes,
        created_at=model.created_at,
    )


def import_upload_from_model(model: ImportUploadModel) -> ImportUpload:
    return ImportUpload(
        id=model.id,
        source_id=model.source_id,
        file_name=model.file_name,
        uploaded_by=model.uploaded_by,
        artifact_hash=model.artifact_hash,
        size_bytes=model.size_bytes,
        raw_mime_type=model.raw_mime_type,
        resolved_snapshot_id=model.resolved_snapshot_id,
        status=UploadStatus(model.status),
        created_at=model.created_at,
        consumed_at=model.consumed_at,
    )
