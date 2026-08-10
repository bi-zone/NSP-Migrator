from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import ApplicationSettings
from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.infrastructure.http_requester.requester import HttpxRequester


class InfrastructureContainer(containers.DeclarativeContainer):
    config: ApplicationSettings = providers.Configuration()

    # -- Database dependencies
    async_engine = providers.Singleton(
        create_async_engine,
        config.database.async_url,
        echo=config.database.echo,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
    )

    session_maker = providers.Singleton(
        async_sessionmaker,
        bind=async_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    session_factory = providers.Singleton(
        SQLAlchemySessionFactory,
        session_maker=session_maker,
    )

    # -- Http Requester
    http_requester_factory = providers.Factory(HttpxRequester)
