"""Use case for listing all import sources."""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.application.dto import ImportSourceDTO
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class GetImportSourcesQuery:
    """Marker query for full source list retrieval."""


@dataclass(slots=True)
class GetImportSourcesResult:
    """Represent output payload returned by GetImportSources flow."""
    sources: list[ImportSourceDTO]


class GetImportSourcesUseCase:
    """Read-only use case for source catalog listing."""
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetImportSourcesQuery) -> GetImportSourcesResult:
        """Return all import sources as API-ready DTOs.

        Args:
            query: Marker query reserved for future list parameters.

        Returns:
            Result containing all source projections.
        """
        sources = await self.uow.sources.list_all()
        return GetImportSourcesResult(
            sources=[
                ImportSourceDTO(
                    id=s.id,
                    vendor_code=s.vendor_code,
                    name=s.name,
                    description=s.description,
                    active=s.active,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in sources
            ]
        )
