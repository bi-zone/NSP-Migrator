"""Shared integration-test infrastructure.

These fixtures own the database lifecycle for module-level integration tests:
create a deterministic fresh PostgreSQL database, apply the current Alembic
schema, expose SQLAlchemy async sessions, and clean persisted state between
tests.

Module-specific fixtures must live closer to their modules so this file stays
reusable across settings, mapping, execute, imports, and future modules.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory

TEST_DB_NAME = os.environ.get("APP_TEST_DB_NAME", "policy_migrator_test")


def _test_db_env() -> dict[str, str]:
    return {
        "APP_DB_HOST": os.environ.get(
            "APP_TEST_DB_HOST", os.environ.get("APP_DB_HOST", "localhost")
        ),
        "APP_DB_PORT": os.environ.get(
            "APP_TEST_DB_PORT", os.environ.get("APP_DB_PORT", "5432")
        ),
        "APP_DB_USER": os.environ.get(
            "APP_TEST_DB_USER", os.environ.get("APP_DB_USER", "postgres")
        ),
        "APP_DB_PASSWORD": os.environ.get(
            "APP_TEST_DB_PASSWORD",
            os.environ.get("APP_DB_PASSWORD", "postgres"),
        ),
        "APP_DB_NAME": TEST_DB_NAME,
    }


def _admin_connection_info() -> dict[str, str | int]:
    env = _test_db_env()
    return {
        "host": env["APP_DB_HOST"],
        "port": int(env["APP_DB_PORT"]),
        "user": env["APP_DB_USER"],
        "password": env["APP_DB_PASSWORD"],
        "dbname": os.environ.get("APP_TEST_ADMIN_DB", "postgres"),
    }


def _sync_test_url() -> str:
    env = _test_db_env()
    return (
        f"postgresql+psycopg://{env['APP_DB_USER']}:{env['APP_DB_PASSWORD']}"
        f"@{env['APP_DB_HOST']}:{env['APP_DB_PORT']}/{env['APP_DB_NAME']}"
    )


def _async_test_url() -> str:
    env = _test_db_env()
    return (
        f"postgresql+asyncpg://{env['APP_DB_USER']}:{env['APP_DB_PASSWORD']}"
        f"@{env['APP_DB_HOST']}:{env['APP_DB_PORT']}/{env['APP_DB_NAME']}"
    )


def _reset_cached_settings() -> None:
    """Refresh global app settings after tests point APP_DB_* at the test DB."""
    import app.core.config as config_module

    config_module.get_settings.cache_clear()
    config_module.settings = config_module.get_settings()


def _drop_database(database_name: str) -> None:
    with psycopg.connect(**_admin_connection_info(), autocommit=True) as connection:
        connection.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')


def _create_database(database_name: str) -> None:
    with psycopg.connect(**_admin_connection_info(), autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{database_name}"')


def _upgrade_test_database() -> None:
    alembic_config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", _sync_test_url())
    command.upgrade(alembic_config, "head")


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> Iterator[str]:
    """Create a fresh deterministic DB and apply the current project schema."""
    os.environ.update(_test_db_env())
    _reset_cached_settings()
    _drop_database(TEST_DB_NAME)
    _create_database(TEST_DB_NAME)
    _upgrade_test_database()

    try:
        yield TEST_DB_NAME
    finally:
        _drop_database(TEST_DB_NAME)


@pytest.fixture
def fresh_migrated_test_database(migrated_test_database: str) -> str:
    """Reset the test DB for an end-to-end workflow requiring migration seeds."""
    _drop_database(migrated_test_database)
    _create_database(migrated_test_database)
    _upgrade_test_database()
    return migrated_test_database


@pytest_asyncio.fixture
async def async_engine(migrated_test_database: str) -> AsyncIterator[AsyncEngine]:
    """Expose one async SQLAlchemy engine bound to the migrated test database."""
    engine = create_async_engine(_async_test_url(), poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def async_session_maker(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Build async sessions with the same settings as production UoWs expect."""
    return async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def session_factory(
    async_session_maker: async_sessionmaker[AsyncSession],
) -> SQLAlchemySessionFactory:
    """Return the infrastructure session factory used by real SQLAlchemy UoWs."""
    return SQLAlchemySessionFactory(async_session_maker)


@pytest_asyncio.fixture
async def clean_database(async_engine: AsyncEngine) -> AsyncIterator[None]:
    """Remove persisted data between tests while preserving Alembic metadata."""
    async with async_engine.begin() as connection:
        tables = (
            await connection.execute(
                text("""
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                      AND tablename <> 'alembic_version'
                    """)
            )
        ).scalars()
        table_names = list(tables)
        if table_names:
            quoted = ", ".join(f'"{name}"' for name in table_names)
            await connection.execute(
                text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE")
            )

    yield


@pytest_asyncio.fixture
async def db_session(
    clean_database: None,
    async_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Provide a short-lived assertion session for integration tests."""
    async with async_session_maker() as session:
        yield session
