"""Use case for fetching one import source by id."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.application.dto import ImportSourceDTO
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class GetImportSourceQuery:
    """Query object for source lookup."""
    source_id: UUID


@dataclass(slots=True)
class GetImportSourceResult:
    """Represent output payload returned by GetImportSource flow."""
    source: ImportSourceDTO | None


class GetImportSourceUseCase:
    """Read-only use case returning a single source projection."""
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetImportSourceQuery) -> GetImportSourceResult:
        """Fetch source by id and map entity to DTO.

        Args:
            query: Query carrying source identifier.

        Returns:
            Result with source set to None when no row exists.
        """
        s = await self.uow.sources.get_by_id(query.source_id)
        if not s:
            return GetImportSourceResult(source=None)
        return GetImportSourceResult(
            source=ImportSourceDTO(
                id=s.id,
                vendor_code=s.vendor_code,
                name=s.name,
                description=s.description,
                active=s.active,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
        )
