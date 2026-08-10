"""Repository port for import upload records."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.imports.domain.import_upload import ImportUpload


class ImportUploadRepositoryPort(IAsyncRepository[ImportUpload, UUID]):
    """Persistence contract for upload metadata and lookup projections."""

    @abstractmethod
    async def save(self, upload: ImportUpload) -> None:
        """Persist upload aggregate in current transactional context."""
        ...

    @abstractmethod
    async def get_by_id(self, upload_id: UUID) -> ImportUpload | None:
        """Return upload row by identifier or None when absent."""
        ...

    @abstractmethod
    async def list_by_source(
        self, source_id: UUID, *, limit: int = 50
    ) -> list[ImportUpload]:
        """Return recent uploads for source, bounded by limit."""
        ...

    @abstractmethod
    async def get_latest_by_snapshot(
        self, snapshot_id: UUID
    ) -> ImportUpload | None:
        """Return newest upload linked to snapshot or None."""
        ...
