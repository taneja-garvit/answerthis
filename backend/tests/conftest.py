import socket
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

from app.ai.base import LLMProvider
from app.ai.providers.deterministic import DeterministicLLMProvider
from app.core.config import Settings
from app.db.session import Database, create_engine_from_url, get_session, normalize_database_url
from app.main import create_app
from app.papers.base import PaperProvider
from tests.db_guard import UnsafeTestDatabaseError, database_url_for_tests
from tests.fakes import FakePaperProvider


@pytest.fixture(autouse=True, scope="session")
def _no_python_sockets() -> Iterator[None]:
    """Belt and braces: any Python-level outbound connection or DNS lookup fails
    the test. The database is unaffected: libpq opens its own sockets in C, and
    psycopg's async driver may only resolve the test database host (or localhost)."""
    original_connect, original_getaddrinfo = socket.socket.connect, socket.getaddrinfo
    allowed_hosts = {"localhost", "127.0.0.1", "::1"}
    try:
        allowed_hosts.add(normalize_database_url(database_url_for_tests()).host or "localhost")
    except UnsafeTestDatabaseError:
        pass  # database tests will fail with their own explicit message

    def guarded_connect(self, address):
        if self.family == getattr(socket, "AF_UNIX", None):
            return original_connect(self, address)
        raise RuntimeError(f"Network access attempted in tests: {address!r}")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host in allowed_hosts:
            return original_getaddrinfo(host, *args, **kwargs)
        raise RuntimeError(f"DNS lookup attempted in tests: {host!r}")

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.getaddrinfo = original_getaddrinfo


@pytest.fixture(autouse=True)
def _no_external_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach Crossref, OpenAlex, Groq or the internet. Real httpx
    transports are disabled; in-process ASGI requests still work."""

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("External HTTP is disabled in tests; mock the provider instead.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    try:
        url = database_url_for_tests()
    except UnsafeTestDatabaseError as exc:
        pytest.fail(str(exc), pytrace=False)

    # Bring the isolated test database to the current schema. Upgrades are
    # additive; tests never drop or truncate tables.
    from alembic.config import Config

    from alembic import command
    from app.core.config import REPO_ROOT

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return url


def make_settings(database_url: str, **overrides) -> Settings:
    values = {
        "database_url": database_url,
        "environment": "test",
        "llm_provider": "deterministic",
        "groq_api_key": None,
        "llm_model": None,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
async def test_engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    """One engine for the whole run: a remote database makes a fresh connection
    per test (TLS + auth) the dominant cost."""
    engine = create_async_engine(
        normalize_database_url(test_database_url),
        poolclass=pool.AsyncAdaptedQueuePool,
        pool_size=1,
        max_overflow=0,
        connect_args={"prepare_threshold": None},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def connection(test_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Each test runs inside an outer transaction that is always rolled back,
    so tests leave no rows behind."""
    conn = await test_engine.connect()
    transaction = await conn.begin()
    try:
        yield conn
    finally:
        await transaction.rollback()
        await conn.close()


def _session(conn: AsyncConnection) -> AsyncSession:
    # Service-level commits become savepoint releases inside the outer transaction.
    return AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")


@pytest.fixture
async def db_session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    session = _session(connection)
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
def settings(test_database_url: str) -> Settings:
    return make_settings(test_database_url)


@pytest.fixture
def llm() -> LLMProvider:
    """Override in a test module to use a scripted or mocked provider."""
    return DeterministicLLMProvider()


@pytest.fixture
def paper_providers() -> list[PaperProvider]:
    """Offline providers serving the heart-failure paper from recorded responses."""
    return [FakePaperProvider.crossref_heart_failure(), FakePaperProvider.openalex_heart_failure()]


@pytest.fixture
async def client(
    settings: Settings,
    connection: AsyncConnection,
    llm: LLMProvider,
    paper_providers: list[PaperProvider],
) -> AsyncIterator[httpx.AsyncClient]:
    database = Database(create_engine_from_url(settings.require_database_url(), settings))
    app = create_app(settings, database, llm=llm, paper_providers=paper_providers)

    async def _request_session() -> AsyncIterator[AsyncSession]:
        # A fresh session per request (as in production) on the test connection.
        session = _session(connection)
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_session] = _request_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await database.dispose()
