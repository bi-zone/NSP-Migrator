from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.csp_profiles.adapters.db.mappers import (
    csp_profile_from_models,
    csp_profile_to_model,
)
from app.modules.settings.csp_profiles.adapters.db.models import (
    CSPProfileCredentialsModel,
    CSPProfileModel,
)
from app.modules.settings.csp_profiles.domain.entities import CSPProfile
from app.modules.settings.csp_profiles.ports.profile_repository import (
    CSPProfileRepositoryPort,
)


class SQLAlchemyCSPProfileRepository(CSPProfileRepositoryPort):
    """Persist profile metadata without loading encrypted payload contents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, profile: CSPProfile) -> None:
        await self.session.merge(csp_profile_to_model(profile))
        await self.session.flush()

    async def get_by_id(self, profile_id: UUID) -> CSPProfile | None:
        row = (
            await self.session.execute(
                self._select_with_metadata().where(CSPProfileModel.id == profile_id)
            )
        ).one_or_none()
        return csp_profile_from_models(*row) if row else None

    async def get_by_name(self, name: str) -> CSPProfile | None:
        row = (
            await self.session.execute(
                self._select_with_metadata().where(
                    func.lower(CSPProfileModel.name) == name.strip().lower()
                )
            )
        ).one_or_none()
        return csp_profile_from_models(*row) if row else None

    async def list_all(
        self,
        active_only: bool = False,
        profile_ids: tuple[UUID, ...] | None = None,
    ) -> list[CSPProfile]:
        stmt: Select = self._select_with_metadata().order_by(
            CSPProfileModel.created_at.desc()
        )

        if active_only:
            stmt = stmt.where(CSPProfileModel.is_active.is_(True))
        if profile_ids is not None:
            stmt = stmt.where(CSPProfileModel.id.in_(profile_ids))

        rows = await self.session.execute(stmt)
        return [csp_profile_from_models(*row) for row in rows.all()]

    async def update(self, profile: CSPProfile) -> bool:
        result = await self.session.execute(
            update(CSPProfileModel)
            .where(CSPProfileModel.id == profile.id)
            .values(
                name=profile.name,
                base_url=profile.base_url,
                username=profile.username,
                updated_at=profile.updated_at,
            )
        )
        await self.session.flush()
        return bool(result.rowcount)

    async def change_active_status(self, profile_id: UUID, new_status: bool) -> bool:
        result = await self.session.execute(
            update(CSPProfileModel)
            .where(CSPProfileModel.id == profile_id)
            .values(is_active=new_status)
        )
        await self.session.flush()
        return bool(result.rowcount)

    async def delete(self, profile_id: UUID) -> bool:
        result = await self.session.execute(
            delete(CSPProfileModel).where(
                CSPProfileModel.id == profile_id,
            )
        )
        await self.session.flush()
        return bool(result.rowcount)

    @staticmethod
    def _select_with_metadata():
        return select(CSPProfileModel, CSPProfileCredentialsModel).outerjoin(
            CSPProfileCredentialsModel,
            CSPProfileCredentialsModel.profile_id == CSPProfileModel.id,
        )
