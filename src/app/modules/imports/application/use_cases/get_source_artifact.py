"""Use case for loading raw artifact text by source snapshot id."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.infrastructure.db.transactional import async_transactional
from app.modules.imports.errors import SourceArtifactNotFoundError
from app.modules.imports.ports.uow import ImportsUoWPort


@dataclass(slots=True)
class GetSourceArtifactQuery:
    """Query object referencing a source snapshot artifact."""
    source_snapshot_id: UUID


@dataclass(slots=True)
class GetSourceArtifactResult:
    """Raw source payload projection used by HTTP and downstream readers."""
    source_snapshot_id: UUID
    raw_text: str
    line_count: int
    size_bytes: int


class GetSourceArtifactUseCase:
    """Read-only use case returning raw text projection for parsing flows."""
    def __init__(self, uow: ImportsUoWPort) -> None:
        self.uow = uow

    @async_transactional(read_only=True)
    async def execute(self, query: GetSourceArtifactQuery) -> GetSourceArtifactResult:
        """Return raw text payload for source snapshot.

        Args:
            query: Snapshot reference for artifact lookup.

        Returns:
            Raw text projection with line and size metadata.

        Raises:
            SourceArtifactNotFoundError: When artifact is absent for snapshot.
        """
        artifact = await self.uow.artifacts.get_by_snapshot_id(query.source_snapshot_id)
        if artifact is None:
            raise SourceArtifactNotFoundError(
                f"source_artifact not found for snapshot_id={query.source_snapshot_id}"
            )
        return GetSourceArtifactResult(
            source_snapshot_id=artifact.snapshot_id,
            raw_text=artifact.raw_text,
            line_count=artifact.line_count,
            size_bytes=artifact.size_bytes,
        )
