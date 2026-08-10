from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.imports.adapters.db.mappers import (
    source_artifact_from_model,
    source_artifact_to_model,
)
from app.modules.imports.adapters.db.models import SourceArtifactModel
from app.modules.imports.domain.source_artifact import SourceArtifact
from app.modules.imports.ports.source_artifact_repository import (
    SourceArtifactRepositoryPort,
)


class SQLAlchemySourceArtifactRepository(
    SqlAlchemyRepository[SourceArtifactModel, UUID],
    SourceArtifactRepositoryPort,
):
    """Implement persistence access for SQLAlchemySourceArtifactRepository."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SourceArtifactModel)

    async def save(self, artifact: SourceArtifact) -> None:
        self.session.add(source_artifact_to_model(artifact))
        await self.session.flush()

    async def get_by_snapshot_id(self, snapshot_id: UUID) -> SourceArtifact | None:
        model = await self.session.get(SourceArtifactModel, snapshot_id)
        return source_artifact_from_model(model) if model else None
