from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.imports.adapters.db.mappers import import_vendor_from_model
from app.modules.imports.adapters.db.models import ImportVendorModel
from app.modules.imports.domain.import_vendor import ImportVendor
from app.modules.imports.ports.import_vendor_repository import (
    ImportVendorRepositoryPort,
)


class SQLAlchemyImportVendorRepository(
    SqlAlchemyRepository[ImportVendorModel, str],
    ImportVendorRepositoryPort,
):
    """Implement persistence access for SQLAlchemyImportVendorRepository."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ImportVendorModel)

    async def get_by_code(self, code: str) -> ImportVendor | None:
        model = await self.session.get(ImportVendorModel, code)
        return import_vendor_from_model(model) if model else None

    async def list_active(self) -> list[ImportVendor]:
        rows = await self.session.scalars(
            select(ImportVendorModel)
            .where(ImportVendorModel.active.is_(True))
            .order_by(ImportVendorModel.display_name.asc())
        )
        return [import_vendor_from_model(m) for m in rows.all()]
