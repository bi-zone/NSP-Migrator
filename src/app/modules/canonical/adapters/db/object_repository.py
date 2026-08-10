from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.canonical.adapters.db import mappers, models
from app.modules.canonical.domain.object import CanonicalObject, CanonicalObjectMember
from app.modules.canonical.ports.object_repository import CanonicalObjectRepositoryPort


class SQLAlchemyCanonicalObjectRepository(
    SqlAlchemyRepository[models.CanonicalObjectModel, UUID],
    CanonicalObjectRepositoryPort,
):
    """Objects, group members, and batch reads for rule_scope expansion."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, models.CanonicalObjectModel)

    async def bulk_save(self, objects: list[CanonicalObject]) -> None:
        """Insert object rows on snapshot write path."""
        if not objects:
            return
        self.session.add_all([mappers.object_to_model(o) for o in objects])
        await self.session.flush()

    async def bulk_save_members(self, members: list[CanonicalObjectMember]) -> None:
        """Insert group membership edges."""
        if not members:
            return
        self.session.add_all([mappers.object_member_to_model(m) for m in members])
        await self.session.flush()

    async def get_by_id_for_snapshot(
        self, *, canonical_snapshot_id: UUID, object_id: UUID
    ) -> CanonicalObject | None:
        """Single object scoped to snapshot."""
        q = select(models.CanonicalObjectModel).where(
            models.CanonicalObjectModel.id == object_id,
            models.CanonicalObjectModel.canonical_snapshot_id == canonical_snapshot_id,
        )
        model = (await self.session.scalars(q)).first()
        return mappers.object_to_entity(model) if model else None

    async def get_members_by_parent(
        self, *, canonical_snapshot_id: UUID, parent_object_id: UUID
    ) -> list[CanonicalObjectMember]:
        """Ordered members of one group; used by object detail endpoint."""
        q = (
            select(models.CanonicalObjectMemberModel)
            .join(
                models.CanonicalObjectModel,
                models.CanonicalObjectModel.id
                == models.CanonicalObjectMemberModel.parent_object_id,
            )
            .where(
                models.CanonicalObjectModel.canonical_snapshot_id
                == canonical_snapshot_id,
                models.CanonicalObjectMemberModel.parent_object_id == parent_object_id,
            )
            .order_by(models.CanonicalObjectMemberModel.position.asc())
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.object_member_to_entity(m) for m in rows]

    async def get_by_snapshot(
        self, canonical_snapshot_id: UUID
    ) -> list[CanonicalObject]:
        """All objects in snapshot."""
        q = select(models.CanonicalObjectModel).where(
            models.CanonicalObjectModel.canonical_snapshot_id == canonical_snapshot_id
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.object_to_entity(m) for m in rows]

    async def get_by_ids_for_snapshot(
        self, *, canonical_snapshot_id: UUID, object_ids: list[UUID]
    ) -> list[CanonicalObject]:
        """Batch object fetch by id within snapshot."""
        if not object_ids:
            return []
        q = select(models.CanonicalObjectModel).where(
            models.CanonicalObjectModel.canonical_snapshot_id == canonical_snapshot_id,
            models.CanonicalObjectModel.id.in_(object_ids),
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.object_to_entity(m) for m in rows]

    async def get_members_by_parents(
        self, *, canonical_snapshot_id: UUID, parent_object_ids: list[UUID]
    ) -> list[CanonicalObjectMember]:
        """Batch group members; used by expand_object_groups."""
        if not parent_object_ids:
            return []
        q = (
            select(models.CanonicalObjectMemberModel)
            .join(
                models.CanonicalObjectModel,
                models.CanonicalObjectModel.id
                == models.CanonicalObjectMemberModel.parent_object_id,
            )
            .where(
                models.CanonicalObjectModel.canonical_snapshot_id
                == canonical_snapshot_id,
                models.CanonicalObjectMemberModel.parent_object_id.in_(
                    parent_object_ids
                ),
            )
            .order_by(
                models.CanonicalObjectMemberModel.parent_object_id.asc(),
                models.CanonicalObjectMemberModel.position.asc(),
            )
        )
        rows = list((await self.session.scalars(q)).all())
        return [mappers.object_member_to_entity(m) for m in rows]
