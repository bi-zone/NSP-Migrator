from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.canonical.adapters.db import mappers, models
from app.modules.canonical.domain.enums import SnapshotStatus
from app.modules.canonical.domain.issue import CanonicalIssue
from app.modules.canonical.domain.snapshot import CanonicalSnapshot
from app.modules.canonical.ports.snapshot_repository import (
    CanonicalSnapshotRepositoryPort,
)


class SQLAlchemyCanonicalSnapshotRepository(
    SqlAlchemyRepository[models.CanonicalSnapshotModel, UUID],
    CanonicalSnapshotRepositoryPort,
):
    """Snapshot header, idempotency lookup, counts, and issues."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.CanonicalSnapshotModel)

    async def save(self, snapshot: CanonicalSnapshot) -> None:
        """Insert or update snapshot header row."""
        self.session.add(mappers.snapshot_to_model(snapshot))
        await self.session.flush()

    async def save_issues(self, issues: list[CanonicalIssue]) -> None:
        """Bulk insert normalizer issues after graph write."""
        if not issues:
            return
        self.session.add_all([mappers.issue_to_model(i) for i in issues])
        await self.session.flush()

    async def update_counts(
        self,
        *,
        snapshot_id: UUID,
        zones_total: int,
        objects_total: int,
        rules_total: int,
        issues_total: int,
    ) -> None:
        """Refresh denormalized totals on snapshot header."""
        await self.session.execute(
            update(models.CanonicalSnapshotModel)
            .where(models.CanonicalSnapshotModel.id == snapshot_id)
            .values(
                zones_total=zones_total,
                objects_total=objects_total,
                rules_total=rules_total,
                issues_total=issues_total,
            )
        )

    async def update_status(self, snapshot_id: UUID, status: SnapshotStatus) -> None:
        """Mark snapshot SUCCESS/FAILED after materialization."""
        await self.session.execute(
            update(models.CanonicalSnapshotModel)
            .where(models.CanonicalSnapshotModel.id == snapshot_id)
            .values(status=status.value)
        )

    async def get_by_id(self, snapshot_id: UUID) -> CanonicalSnapshot | None:
        """Load snapshot header by primary key."""
        model = await super().get_by_id(snapshot_id)
        return mappers.snapshot_to_entity(model) if model else None

    async def get_latest_for_source(
        self, source_snapshot_id: UUID
    ) -> CanonicalSnapshot | None:
        """Most recent canonical row for an imports source snapshot."""
        q = (
            select(models.CanonicalSnapshotModel)
            .where(
                models.CanonicalSnapshotModel.source_snapshot_id == source_snapshot_id
            )
            .order_by(desc(models.CanonicalSnapshotModel.created_at))
            .limit(1)
        )
        model = (await self.session.scalars(q)).first()
        return mappers.snapshot_to_entity(model) if model else None

    async def get_by_source_and_normalizer(
        self,
        *,
        source_snapshot_id: UUID,
        normalizer_code: str,
        normalizer_version: str,
    ) -> CanonicalSnapshot | None:
        """Idempotency key lookup for ``SaveCanonicalSnapshotUseCase``."""
        q = (
            select(models.CanonicalSnapshotModel)
            .where(
                models.CanonicalSnapshotModel.source_snapshot_id == source_snapshot_id,
                models.CanonicalSnapshotModel.normalizer_code == normalizer_code,
                models.CanonicalSnapshotModel.normalizer_version == normalizer_version,
            )
            .order_by(desc(models.CanonicalSnapshotModel.created_at))
            .limit(1)
        )
        model = (await self.session.scalars(q)).first()
        return mappers.snapshot_to_entity(model) if model else None

    async def get_issues_by_snapshot(self, snapshot_id: UUID) -> list[CanonicalIssue]:
        """All issues linked to snapshot."""
        q = (
            select(models.CanonicalIssueModel)
            .where(models.CanonicalIssueModel.canonical_snapshot_id == snapshot_id)
            .order_by(models.CanonicalIssueModel.created_at.asc())
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.issue_to_entity(m) for m in rows]
