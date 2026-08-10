"""Repository port for import vendor reference data."""

from __future__ import annotations

from abc import abstractmethod

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.imports.domain.import_vendor import ImportVendor


class ImportVendorRepositoryPort(IAsyncRepository):
    """Contract for reading vendor registry entries."""

    @abstractmethod
    async def get_by_code(self, code: str) -> ImportVendor | None:
        """Return vendor by stable code or None when missing."""
        ...

    @abstractmethod
    async def list_active(self) -> list[ImportVendor]:
        """Return active vendors available for source onboarding."""
        ...
