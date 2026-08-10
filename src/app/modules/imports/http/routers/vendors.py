from __future__ import annotations

from fastapi import APIRouter, Depends

from app.modules.imports.application.use_cases.get_import_vendors import (
    GetImportVendorsQuery,
    GetImportVendorsUseCase,
)
from app.modules.imports.di.dependencies import list_import_vendors_uc
from app.modules.imports.http.schemas import ImportVendorResponse

router = APIRouter(tags=["imports"])


@router.get(
    "/vendors",
    response_model=list[ImportVendorResponse],
    summary="List import vendors",
    description="Return active import vendors available for source registration.",
)
async def list_import_vendors(
    use_case: GetImportVendorsUseCase = Depends(list_import_vendors_uc),
) -> list[ImportVendorResponse]:
    """List active vendors that can accept new import sources.

    Args:
        use_case: Read-only use case returning active vendor records.

    Returns:
        Vendor response list used by source-creation clients.
    """
    result = await use_case.execute(GetImportVendorsQuery())
    return [
        ImportVendorResponse.model_validate(vendor, from_attributes=True)
        for vendor in result.vendors
    ]
