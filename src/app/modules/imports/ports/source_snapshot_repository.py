"""Repository port for source snapshot metadata."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.imports.domain.source_snapshot import SourceSnapshot


class SourceSnapshotRepositoryPort(IAsyncRepository[SourceSnapshot, UUID]):
    """Contract for snapshot persistence and query operations."""

    @abstractmethod
    async def save(self, snapshot: SourceSnapshot) -> None:
        """Persist snapshot aggregate and participating state flags."""
        ...

    @abstractmethod
    async def get_by_id(self, snapshot_id: UUID) -> SourceSnapshot | None:
        """Return snapshot by id or None if not found."""
        ...

    @abstractmethod
    async def get_by_hash(
        self, source_id: UUID, *, artifact_hash: str
    ) -> SourceSnapshot | None:
        """Find snapshot by source and content hash for deduplication."""
        ...

    @abstractmethod
    async def get_latest_for_source(self, source_id: UUID) -> SourceSnapshot | None:
        """Return latest snapshot marked for source, if any."""
        ...

    @abstractmethod
    async def mark_previous_not_latest(self, source_id: UUID) -> None:
        """Update persisted state flags according to repository rules.

        Args:
            source_id: Identifier of the import source.

        Returns:
            None. Effects are applied to persistence context/unit of work.
        """
        ...

    @abstractmethod
    async def list_recent(self, *, limit: int = 200) -> list[SourceSnapshot]:
        """Return recently created snapshots across sources."""
        ...
