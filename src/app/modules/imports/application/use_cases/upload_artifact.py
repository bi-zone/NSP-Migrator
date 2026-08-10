"""Use case for raw artifact upload registration and deduplication."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.application.dto import ImportUploadDTO, SourceSnapshotDTO
from app.modules.imports.domain.enums import UploadStatus
from app.modules.imports.domain.import_upload import ImportUpload
from app.modules.imports.domain.source_artifact import SourceArtifact
from app.modules.imports.domain.source_snapshot import SourceSnapshot
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class UploadArtifactCommand:
    """Input payload for artifact upload flow."""
    source_id: UUID
    file_name: str
    raw_text: str
    uploaded_by: str
    raw_mime_type: str | None = None
    source_format: str = "text/plain"


@dataclass(slots=True)
class UploadArtifactResult:
    """Represent output payload returned by UploadArtifact flow."""
    upload: ImportUploadDTO
    snapshot: SourceSnapshotDTO


class UploadArtifactUseCase:
    """Store uploaded raw text and resolve a source snapshot.

    The use case deduplicates snapshots by SHA-256 hash per source while still
    persisting a new upload event for auditability.
    """
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(self, command: UploadArtifactCommand) -> UploadArtifactResult:
        """Create upload row and resolve/create linked snapshot.

        Args:
            command: Upload payload with raw text and uploader metadata.

        Returns:
            Upload metadata plus snapshot metadata chosen by dedup flow.

        Side Effects:
            Persists snapshot/artifact rows on first-seen hash and always
            persists an upload row linked to resolved snapshot.
        """
        raw_bytes = command.raw_text.encode("utf-8")
        artifact_hash = hashlib.sha256(raw_bytes).hexdigest()
        size_bytes = len(raw_bytes)

        existing_snapshot = await self.uow.snapshots.get_by_hash(
            command.source_id, artifact_hash=artifact_hash
        )

        if existing_snapshot:
            snapshot_id = existing_snapshot.id
            snapshot_dto = SourceSnapshotDTO(
                id=existing_snapshot.id,
                source_id=existing_snapshot.source_id,
                artifact_hash=existing_snapshot.artifact_hash,
                source_format=existing_snapshot.source_format,
                is_latest=existing_snapshot.is_latest,
                created_at=existing_snapshot.created_at,
            )
        else:
            await self.uow.snapshots.mark_previous_not_latest(command.source_id)
            snapshot = SourceSnapshot.create(
                source_id=command.source_id,
                artifact_hash=artifact_hash,
                source_format=command.source_format,
                is_latest=True,
            )
            artifact = SourceArtifact.create(
                snapshot_id=snapshot.id, raw_text=command.raw_text
            )
            await self.uow.snapshots.save(snapshot)
            await self.uow.artifacts.save(artifact)
            snapshot_id = snapshot.id
            snapshot_dto = SourceSnapshotDTO(
                id=snapshot.id,
                source_id=snapshot.source_id,
                artifact_hash=snapshot.artifact_hash,
                source_format=snapshot.source_format,
                is_latest=snapshot.is_latest,
                created_at=snapshot.created_at,
            )

        upload = ImportUpload.create(
            source_id=command.source_id,
            file_name=command.file_name,
            uploaded_by=command.uploaded_by,
            artifact_hash=artifact_hash,
            size_bytes=size_bytes,
            raw_mime_type=command.raw_mime_type,
            resolved_snapshot_id=snapshot_id,
            status=UploadStatus.RESOLVED,
        )
        await self.uow.uploads.save(upload)

        return UploadArtifactResult(
            upload=ImportUploadDTO(
                id=upload.id,
                source_id=upload.source_id,
                file_name=upload.file_name,
                uploaded_by=upload.uploaded_by,
                artifact_hash=upload.artifact_hash,
                size_bytes=upload.size_bytes,
                raw_mime_type=upload.raw_mime_type,
                resolved_snapshot_id=upload.resolved_snapshot_id,
                status=upload.status,
                created_at=upload.created_at,
                consumed_at=upload.consumed_at,
            ),
            snapshot=snapshot_dto,
        )
