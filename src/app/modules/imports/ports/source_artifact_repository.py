"""Repository port for raw source artifacts tied to snapshots."""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from app.infrastructure.interfaces.db import IAsyncRepository
from app.modules.imports.domain.source_artifact import SourceArtifact


class SourceArtifactRepositoryPort(IAsyncRepository[SourceArtifact, UUID]):
    """Contract for storing and loading raw uploaded text artifacts."""

    @abstractmethod
    async def save(self, artifact: SourceArtifact) -> None:
        """Persist raw artifact payload for downstream parsing."""
        ...

    @abstractmethod
    async def get_by_snapshot_id(self, snapshot_id: UUID) -> SourceArtifact | None:
        """Return artifact for snapshot or None when missing."""
        ...
