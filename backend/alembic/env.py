import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import normalize_database_url

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests pass the isolated test database URL explicitly via
    # config.attributes; everything else uses DATABASE_URL. The URL is kept out
    # of config options so it is never interpolated or echoed.
    explicit = config.attributes.get("database_url")
    if explicit:
        return explicit
    return get_settings().require_database_url()


def run_migrations_offline() -> None:
    # Offline mode only emits SQL, so it needs the dialect, not credentials.
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(
        normalize_database_url(_database_url()),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 15, "prepare_threshold": None},
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
