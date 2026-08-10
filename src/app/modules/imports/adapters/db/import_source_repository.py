from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.imports.adapters.db.mappers import (
    import_source_from_model,
    import_source_to_model,
)
from app.modules.imports.adapters.db.models import ImportSourceModel
from app.modules.imports.domain.import_source import ImportSource
from app.modules.imports.ports.import_source_repository import (
    ImportSourceRepositoryPort,
)


class SQLAlchemyImportSourceRepository(
    SqlAlchemyRepository[ImportSourceModel, UUID],
    ImportSourceRepositoryPort,
):
    """Implement persistence access for SQLAlchemyImportSourceRepository."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ImportSourceModel)

    async def save(self, source: ImportSource) -> None:
        self.session.add(import_source_to_model(source))
        await self.session.flush()

    async def get_by_id(self, source_id: UUID) -> ImportSource | None:
        model = await self.session.get(ImportSourceModel, source_id)
        return import_source_from_model(model) if model else None

    async def get_by_vendor_code_and_name(
        self, vendor_code: str, name: str
    ) -> ImportSource | None:
        row = await self.session.scalar(
            select(ImportSourceModel).where(
                ImportSourceModel.vendor_code == vendor_code,
                ImportSourceModel.name == name,
            )
        )
        return import_source_from_model(row) if row else None

    async def list_all(self) -> list[ImportSource]:
        rows = await self.session.scalars(
            select(ImportSourceModel).order_by(ImportSourceModel.created_at.desc())
        )
        return [import_source_from_model(m) for m in rows.all()]
