from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.modules.imports.application.use_cases.create_import_source import (
    CreateImportSourceCommand,
    CreateImportSourceUseCase,
)
from app.modules.imports.application.use_cases.get_import_source import (
    GetImportSourceQuery,
    GetImportSourceUseCase,
)
from app.modules.imports.application.use_cases.get_import_sources import (
    GetImportSourcesQuery,
    GetImportSourcesUseCase,
)
from app.modules.imports.di.dependencies import (
    create_import_source_uc,
    get_import_source_uc,
    list_import_sources_uc,
)
from app.modules.imports.http.schemas import (
    CreateImportSourceRequest,
    ImportSourceResponse,
)

router = APIRouter(tags=["imports"])


@router.post(
    "/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportSourceResponse,
    summary="Create import source",
    description=(
        "Create a new import source for a vendor. If a source with the same "
        "vendor/name already exists, return that source and respond with 200."
    ),
)
async def create_import_source(
    body: CreateImportSourceRequest,
    response: Response,
    use_case: CreateImportSourceUseCase = Depends(create_import_source_uc),
) -> ImportSourceResponse:
    """Create a new source or return an existing source with same identity.

    Args:
        body: Client payload describing vendor-bound source metadata.
        response: FastAPI response object used to downgrade status to 200
            when an existing source is reused.
        use_case: Application service implementing vendor validation and
            idempotent source creation semantics.

    Returns:
        Canonical API projection of the created or reused source.
    """
    result = await use_case.execute(
        CreateImportSourceCommand(
            vendor_code=body.vendor_code,
            name=body.name,
            description=body.description,
            active=body.active,
        )
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    source = result.source
    return ImportSourceResponse(
        id=source.id,
        vendor_code=source.vendor_code,
        name=source.name,
        description=source.description,
        active=source.active,
        created_at=source.created_at,
        updated_at=source.updated_at,
        created=result.created,
    )


@router.get(
    "/sources",
    response_model=list[ImportSourceResponse],
    summary="List import sources",
    description="Return all import sources available in the imports context.",
)
async def list_import_sources(
    use_case: GetImportSourcesUseCase = Depends(list_import_sources_uc),
) -> list[ImportSourceResponse]:
    """Return all registered import sources for management UIs and clients.

    Args:
        use_case: Read-only use case that returns all source DTO records.

    Returns:
        Ordered list of source response models from repository projection.
    """
    result = await use_case.execute(GetImportSourcesQuery())
    return [
        ImportSourceResponse.model_validate(source, from_attributes=True)
        for source in result.sources
    ]


@router.get(
    "/sources/{source_id}",
    response_model=ImportSourceResponse,
    summary="Get import source",
    description="Return one import source by identifier or 404 when not found.",
)
async def get_import_source(
    source_id: UUID,
    use_case: GetImportSourceUseCase = Depends(get_import_source_uc),
) -> ImportSourceResponse:
    """Get a single import source by identifier.

    Args:
        source_id: Stable source identifier from path parameter.
        use_case: Read-only use case for source lookup.

    Returns:
        Source response model when the source exists.

    Raises:
        HTTPException: With 404 status when source identifier is unknown.
    """
    result = await use_case.execute(GetImportSourceQuery(source_id=source_id))
    if result.source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import source not found",
        )
    return ImportSourceResponse.model_validate(result.source, from_attributes=True)
