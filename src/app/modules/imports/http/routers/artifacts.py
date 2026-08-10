from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.imports.application.use_cases.get_source_artifact import (
    GetSourceArtifactQuery,
    GetSourceArtifactUseCase,
)
from app.modules.imports.di.dependencies import get_source_artifact_uc
from app.modules.imports.errors import SourceArtifactNotFoundError
from app.modules.imports.http.schemas import SourceArtifactRawTextResponse

router = APIRouter(tags=["imports"])


@router.get(
    "/source-snapshots/{snapshot_id}/raw-text",
    response_model=SourceArtifactRawTextResponse,
    summary="Get snapshot raw text",
    description=(
        "Return raw artifact text and lightweight metadata for a source "
        "snapshot."
    ),
)
async def get_source_snapshot_raw_text(
    snapshot_id: UUID,
    use_case: GetSourceArtifactUseCase = Depends(get_source_artifact_uc),
) -> SourceArtifactRawTextResponse:
    """Return raw artifact payload for an existing source snapshot.

    Args:
        snapshot_id: Snapshot identifier from the imports pipeline.
        use_case: Read-only use case that loads stored artifact payload.

    Returns:
        Raw text plus lightweight metadata derived at write-time.

    Raises:
        HTTPException: With 404 status when artifact row is absent for the
            requested snapshot.
    """
    try:
        result = await use_case.execute(
            GetSourceArtifactQuery(source_snapshot_id=snapshot_id)
        )
    except SourceArtifactNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source artifact not found for snapshot",
        )
    return SourceArtifactRawTextResponse(
        source_snapshot_id=result.source_snapshot_id,
        raw_text=result.raw_text,
        line_count=result.line_count,
        size_bytes=result.size_bytes,
    )
