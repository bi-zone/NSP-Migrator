from __future__ import annotations

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings

# -- Execute module models
from app.modules.execute.adapters.db.models import *  # noqa: F401, F403
from app.modules.mapping.adapters.db.models import *  # noqa: F401, F403

# -- Canonical module models
from app.modules.canonical.adapters.db.models import *  # noqa: F401, F403

# -- Imports module models
from app.modules.imports.adapters.db.models import *  # noqa: F401, F403

# -- Common
from app.modules.trace.adapters.db.models import *  # noqa: F401, F403

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _next_rev_id() -> str:
    """Generate next timestamp-based revision ID: YYYYMMDD_NNNN."""
    today = datetime.now().strftime("%Y%m%d")
    versions_dir = os.path.join(os.path.dirname(__file__), "versions")
    pattern = re.compile(rf"^{today}_(\d{{4}})_")
    max_seq = 0
    if os.path.exists(versions_dir):
        for fname in os.listdir(versions_dir):
            m = pattern.match(fname)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    return f"{today}_{max_seq + 1:04d}"


def process_revision_directives(context, revision, directives):  # type: ignore[no-untyped-def, unused-ignore]
    if directives:
        directives[0].rev_id = _next_rev_id()


def run_migrations_offline() -> None:
    url = settings.database.sync_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.database.sync_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
