"""Repository port for import source aggregates."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.imports.domain.import_source import ImportSource


class ImportSourceRepositoryPort(IAsyncRepository):
    """Persistence contract for import source lifecycle operations."""

    @abstractmethod
    async def save(self, source: ImportSource) -> None:
        """Persist source aggregate changes within current unit of work."""
        ...

    @abstractmethod
    async def get_by_id(self, source_id: UUID) -> ImportSource | None:
        """Return source by identifier or None when it does not exist."""
        ...

    @abstractmethod
    async def get_by_vendor_code_and_name(
        self, vendor_code: str, name: str
    ) -> ImportSource | None:
        """Find source by vendor/name uniqueness key used for idempotency."""
        ...

    @abstractmethod
    async def list_all(self) -> list[ImportSource]:
        """Return all sources visible to imports management flows."""
        ...
