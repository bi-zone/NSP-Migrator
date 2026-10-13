from __future__ import annotations

from app.infrastructure.db.uow import SQLAlchemyUnitOfWork
from app.modules.reports.adapters.db.report_repository import (
    SQLAlchemyReportsRepository,
)
from app.modules.reports.ports.uow import ReportsUnitOfWorkPort


class ReportsUnitOfWork(SQLAlchemyUnitOfWork, ReportsUnitOfWorkPort):
    """Bind the reports repository to one SQLAlchemy transaction."""

    async def __aenter__(self):
        await super().__aenter__()
        if self.session is None:
            raise RuntimeError("ReportsUnitOfWork session is not initialized")
        self.reports = SQLAlchemyReportsRepository(self.session)
        return self
