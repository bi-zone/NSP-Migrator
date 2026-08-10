from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.infrastructure.interfaces.db import IAsyncUnitOfWork


class SQLAlchemyUnitOfWork(IAsyncUnitOfWork):
    def __init__(self, session_factory: SQLAlchemySessionFactory) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._reuse_session = False

    def __call__(self, *, reuse_session: bool = False):
        self._reuse_session = reuse_session
        return self

    async def __aenter__(self):
        if not self.session or not self._reuse_session:
            self.session = self._session_factory.create_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[Exception] | None,
        exc_val: Exception | None,
        traceback,
    ) -> None:
        if not self._reuse_session and self.session:
            if exc_type:
                await self.rollback()
            await self.session.close()
            self.session = None
        self._reuse_session = False

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def flush(self) -> None:
        if self.session:
            await self.session.flush()

    async def refresh(self, item) -> None:
        if self.session:
            await self.session.refresh(item)

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
