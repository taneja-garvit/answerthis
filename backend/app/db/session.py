from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

ASYNC_DRIVER = "postgresql+psycopg"


def normalize_database_url(raw_url: str) -> URL:
    """Accept the connection string Neon shows (`postgresql://...` or
    `postgres://...`) and select the async psycopg 3 driver. Query parameters
    such as `sslmode=require` and `channel_binding=require` are passed through
    to libpq untouched."""
    url = make_url(raw_url.strip())
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg2", "postgresql+asyncpg"}:
        url = url.set(drivername=ASYNC_DRIVER)
    if url.drivername != ASYNC_DRIVER:
        raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
    return url


def create_engine_from_url(raw_url: str, settings: Settings) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(raw_url),
        # Neon is remote and serverless: keep the pool small and validate
        # connections, since idle ones may be closed when compute suspends.
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            # Neon's pooled (-pooler) endpoint runs PgBouncer in transaction
            # mode; server-side prepared statements are not safe there.
            "prepare_threshold": None,
        },
    )


class Database:
    """One engine per process, created by the app factory and disposed on shutdown."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request. Services own the commit; anything left
    uncommitted is rolled back when the session closes."""
    database: Database = request.app.state.db
    async with database.sessionmaker() as session:
        yield session
