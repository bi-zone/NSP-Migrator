from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.imports.domain.enums import UploadStatus

# TODO: Describe why DTOs are used and where they should be applied.

@dataclass(slots=True)
class ImportSourceDTO:
    id: UUID
    vendor_code: str
    name: str
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ImportVendorDTO:
    code: str
    display_name: str
    active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class SourceSnapshotDTO:
    id: UUID
    source_id: UUID | None
    artifact_hash: str | None
    source_format: str | None
    is_latest: bool
    created_at: datetime


@dataclass(slots=True)
class ImportUploadDTO:
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


@dataclass(slots=True)
class SourceSnapshotListItemDTO:
    id: UUID
    source_id: UUID | None
    source_name: str | None
    file_name: str | None
    artifact_hash: str | None
    source_format: str | None
    is_latest: bool
    created_at: datetime
