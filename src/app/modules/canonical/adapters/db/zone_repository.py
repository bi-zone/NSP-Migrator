from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.canonical.adapters.db import mappers, models
from app.modules.canonical.domain.zone import CanonicalZone
from app.modules.canonical.ports.zone_repository import CanonicalZoneRepositoryPort


class SQLAlchemyCanonicalZoneRepository(
    SqlAlchemyRepository[models.CanonicalZoneModel, UUID],
    CanonicalZoneRepositoryPort,
):
    """Zone catalog reads and bulk writes for snapshots."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.CanonicalZoneModel)

    async def bulk_save(self, zones: list[CanonicalZone]) -> None:
        """Insert zone rows on snapshot write path."""
        if not zones:
            return
        self.session.add_all([mappers.zone_to_model(z) for z in zones])
        await self.session.flush()

    async def get_by_id_for_snapshot(
        self, *, canonical_snapshot_id: UUID, zone_id: UUID
    ) -> CanonicalZone | None:
        """Single zone scoped to snapshot."""
        q = select(models.CanonicalZoneModel).where(
            models.CanonicalZoneModel.id == zone_id,
            models.CanonicalZoneModel.canonical_snapshot_id == canonical_snapshot_id,
        )
        model = (await self.session.scalars(q)).first()
        return mappers.zone_to_entity(model) if model else None

    async def get_by_snapshot(self, canonical_snapshot_id: UUID) -> list[CanonicalZone]:
        """All zones in snapshot."""
        q = select(models.CanonicalZoneModel).where(
            models.CanonicalZoneModel.canonical_snapshot_id == canonical_snapshot_id
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.zone_to_entity(m) for m in rows]

    async def get_by_ids_for_snapshot(
        self, *, canonical_snapshot_id: UUID, zone_ids: list[UUID]
    ) -> list[CanonicalZone]:
        """Batch zone fetch for rule operand hydration."""
        if not zone_ids:
            return []
        q = select(models.CanonicalZoneModel).where(
            models.CanonicalZoneModel.canonical_snapshot_id == canonical_snapshot_id,
            models.CanonicalZoneModel.id.in_(zone_ids),
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.zone_to_entity(m) for m in rows]
