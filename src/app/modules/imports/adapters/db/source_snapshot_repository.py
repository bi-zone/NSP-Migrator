from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.imports.adapters.db.mappers import (
    source_snapshot_from_model,
    source_snapshot_to_model,
)
from app.modules.imports.adapters.db.models import SourceSnapshotModel
from app.modules.imports.domain.source_snapshot import SourceSnapshot
from app.modules.imports.ports.source_snapshot_repository import (
    SourceSnapshotRepositoryPort,
)


class SQLAlchemySourceSnapshotRepository(
    SqlAlchemyRepository[SourceSnapshotModel, UUID],
    SourceSnapshotRepositoryPort,
):
    """Implement persistence access for SQLAlchemySourceSnapshotRepository."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SourceSnapshotModel)

    async def save(self, snapshot: SourceSnapshot) -> None:
        self.session.add(source_snapshot_to_model(snapshot))
        await self.session.flush()

    async def get_by_id(self, snapshot_id: UUID) -> SourceSnapshot | None:
        model = await self.session.get(SourceSnapshotModel, snapshot_id)
        return source_snapshot_from_model(model) if model else None

    async def get_by_hash(
        self, source_id: UUID, *, artifact_hash: str
    ) -> SourceSnapshot | None:
        row = (
            await self.session.scalars(
                select(SourceSnapshotModel)
                .where(SourceSnapshotModel.source_id == source_id)
                .where(SourceSnapshotModel.artifact_hash == artifact_hash)
                .limit(1)
            )
        ).first()
        return source_snapshot_from_model(row) if row else None

    async def get_latest_for_source(self, source_id: UUID) -> SourceSnapshot | None:
        row = (
            await self.session.scalars(
                select(SourceSnapshotModel)
                .where(SourceSnapshotModel.source_id == source_id)
                .order_by(SourceSnapshotModel.created_at.desc())
                .limit(1)
            )
        ).first()
        return source_snapshot_from_model(row) if row else None

    async def mark_previous_not_latest(self, source_id: UUID) -> None:
        """Update persisted state flags.

        Args:
            source_id: Identifier of the import source.

        Returns:
            None. Effects are applied to persistence context/unit of work.
        """
        await self.session.execute(
            update(SourceSnapshotModel)
            .where(SourceSnapshotModel.source_id == source_id)
            .where(SourceSnapshotModel.is_latest.is_(True))
            .values(is_latest=False)
        )

    async def list_recent(self, *, limit: int = 200) -> list[SourceSnapshot]:
        rows = await self.session.scalars(
            select(SourceSnapshotModel)
            .order_by(SourceSnapshotModel.created_at.desc())
            .limit(limit)
        )
        return [source_snapshot_from_model(row) for row in rows.all()]
