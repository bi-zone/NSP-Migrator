from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.interfaces.db import ISessionFactory


class SQLAlchemySessionFactory(ISessionFactory):
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    def create_session(self) -> AsyncSession:
        return self._session_maker()
