from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingCommand,
    RunCiscoMappingUseCase,
)
from app.modules.imports.cisco_asa.di.dependencies import get_run_cisco_mapping_use_case
from app.modules.imports.errors import SourceArtifactNotFoundError
from app.modules.imports.http.schemas import RunCiscoMappingResponse

cisco_asa_router = APIRouter(prefix="/imports/cisco-asa", tags=["imports:cisco-asa"])


@cisco_asa_router.post(
    "/snapshots/{snapshot_id}/map-to-canonical",
    status_code=200,
    response_model=RunCiscoMappingResponse,
    summary="Map ASA snapshot to canonical",
    description=(
        "Run Cisco ASA parsing-to-canonical mapping for a source snapshot and "
        "return created canonical snapshot identifier."
    ),
)
async def map_snapshot_to_canonical(
    snapshot_id: UUID,
    use_case: RunCiscoMappingUseCase = Depends(get_run_cisco_mapping_use_case),
) -> RunCiscoMappingResponse:
    """Map one source snapshot to canonical and return canonical snapshot id.

    Args:
        snapshot_id: Source snapshot identifier to process.
        use_case: Use case running parser, normalizer, canonical save, and
            trace write orchestration.

    Returns:
        Canonical snapshot identifier created or reused by mapping pipeline.

    The endpoint preserves idempotent behavior from the use case. If mapping
    artifacts are missing for the provided snapshot id, the endpoint responds
    with HTTP 404.

    Raises:
        HTTPException: With 404 status when source artifact for snapshot
            does not exist.
    """
    try:
        result = await use_case.execute(
            RunCiscoMappingCommand(source_snapshot_id=snapshot_id)
        )
    except SourceArtifactNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source artifact not found for snapshot",
        )
    return RunCiscoMappingResponse(canonical_snapshot_id=result.canonical_snapshot_id)
