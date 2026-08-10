"""Use case for listing active import vendors."""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.application.dto import ImportVendorDTO
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class GetImportVendorsQuery:
    """Marker query for active vendor list retrieval."""


@dataclass(slots=True)
class GetImportVendorsResult:
    """Represent output payload returned by GetImportVendors flow."""
    vendors: list[ImportVendorDTO]


class GetImportVendorsUseCase:
    """Read-only use case for vendor registry projection."""
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetImportVendorsQuery) -> GetImportVendorsResult:
        """Return active vendors usable for source creation.

        Args:
            query: Marker query reserved for future filters.

        Returns:
            Result with active vendor DTO list.
        """
        vendors = await self.uow.vendors.list_active()
        return GetImportVendorsResult(
            vendors=[
                ImportVendorDTO(
                    code=v.code,
                    display_name=v.display_name,
                    active=v.active,
                    created_at=v.created_at,
                    updated_at=v.updated_at,
                )
                for v in vendors
            ]
        )
