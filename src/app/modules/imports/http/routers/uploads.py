from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.modules.imports.application.use_cases.upload_artifact import (
    UploadArtifactCommand,
    UploadArtifactUseCase,
)
from app.modules.imports.di.dependencies import upload_artifact_uc
from app.modules.imports.http.schemas import (
    ImportUploadResponse,
    SourceSnapshotResponse,
    UploadArtifactRequest,
    UploadArtifactResponse,
)

router = APIRouter(tags=["imports"])


@router.post(
    "/sources/{source_id}/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadArtifactResponse,
    summary="Upload source artifact",
    description=(
        "Register raw source text upload for a source and return both upload "
        "metadata and linked source snapshot metadata."
    ),
)
async def upload_artifact(
    source_id: UUID,
    body: UploadArtifactRequest,
    use_case: UploadArtifactUseCase = Depends(upload_artifact_uc),
) -> UploadArtifactResponse:
    """Upload raw source text and resolve it to snapshot/upload metadata.

    Args:
        source_id: Source identifier owning the uploaded artifact.
        body: Upload payload containing raw text and uploader metadata.
        use_case: Application service performing deduplication by content hash.

    Returns:
        Composite response with persisted upload row and resolved snapshot.
    """
    result = await use_case.execute(
        UploadArtifactCommand(
            source_id=source_id,
            file_name=body.file_name,
            raw_text=body.raw_text,
            uploaded_by=body.uploaded_by,
            raw_mime_type=body.raw_mime_type,
            source_format=body.source_format,
        )
    )
    return UploadArtifactResponse(
        upload=ImportUploadResponse.model_validate(result.upload, from_attributes=True),
        snapshot=SourceSnapshotResponse.model_validate(
            result.snapshot,
            from_attributes=True,
        ),
    )
