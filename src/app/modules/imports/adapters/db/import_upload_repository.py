from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repository import SqlAlchemyRepository
from app.modules.imports.adapters.db.mappers import (
    import_upload_from_model,
    import_upload_to_model,
)
from app.modules.imports.adapters.db.models import ImportUploadModel
from app.modules.imports.domain.import_upload import ImportUpload
from app.modules.imports.ports.import_upload_repository import (
    ImportUploadRepositoryPort,
)


class SQLAlchemyImportUploadRepository(
    SqlAlchemyRepository[ImportUploadModel, UUID],
    ImportUploadRepositoryPort,
):
    """Implement persistence access for SQLAlchemyImportUploadRepository."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ImportUploadModel)

    async def save(self, upload: ImportUpload) -> None:
        self.session.add(import_upload_to_model(upload))
        await self.session.flush()

    async def get_by_id(self, upload_id: UUID) -> ImportUpload | None:
        model = await self.session.get(ImportUploadModel, upload_id)
        return import_upload_from_model(model) if model else None

    async def list_by_source(
        self, source_id: UUID, *, limit: int = 50
    ) -> list[ImportUpload]:
        rows = await self.session.scalars(
            select(ImportUploadModel)
            .where(ImportUploadModel.source_id == source_id)
            .order_by(ImportUploadModel.created_at.desc())
            .limit(limit)
        )
        return [import_upload_from_model(m) for m in rows.all()]

    async def get_latest_by_snapshot(self, snapshot_id: UUID) -> ImportUpload | None:
        row = (
            await self.session.scalars(
                select(ImportUploadModel)
                .where(ImportUploadModel.resolved_snapshot_id == snapshot_id)
                .order_by(ImportUploadModel.created_at.desc())
                .limit(1)
            )
        ).first()
        return import_upload_from_model(row) if row else None
