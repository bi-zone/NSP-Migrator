from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.imports.domain.enums import UploadStatus


@dataclass(slots=True)
class ImportUpload:
    id: UUID
    source_id: UUID
    file_name: str
    uploaded_by: str
    artifact_hash: str
    size_bytes: int
    raw_mime_type: str | None
    resolved_snapshot_id: UUID | None
    status: UploadStatus
    created_at: datetime
    consumed_at: datetime | None

    @classmethod
    def create(
        cls,
        *,
        source_id: UUID,
        file_name: str,
        uploaded_by: str,
        artifact_hash: str,
        size_bytes: int,
        raw_mime_type: str | None = None,
        resolved_snapshot_id: UUID | None = None,
        status: UploadStatus = UploadStatus.RECEIVED,
    ) -> ImportUpload:
        return cls(
            id=uuid4(),
            source_id=source_id,
            file_name=file_name,
            uploaded_by=uploaded_by,
            artifact_hash=artifact_hash,
            size_bytes=size_bytes,
            raw_mime_type=raw_mime_type,
            resolved_snapshot_id=resolved_snapshot_id,
            status=status,
            created_at=datetime.now(UTC),
            consumed_at=None,
        )
