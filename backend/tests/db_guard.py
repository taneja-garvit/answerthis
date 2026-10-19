"""Decides which database the test suite may use.

Tests only ever connect to TEST_DATABASE_URL. There is deliberately no fallback
to DATABASE_URL, and a TEST_DATABASE_URL that resolves to the same server,
database and user as DATABASE_URL is refused.
"""

import os

from dotenv import dotenv_values

from app.core.config import ENV_FILE
from app.db.session import normalize_database_url


class UnsafeTestDatabaseError(RuntimeError):
    pass


def _read(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None and ENV_FILE.exists():
        value = dotenv_values(ENV_FILE).get(name)
    return value.strip() if value and value.strip() else None


def _identity(raw_url: str) -> tuple[str | None, int, str | None, str | None]:
    url = normalize_database_url(raw_url)
    return ((url.host or "").lower() or None, url.port or 5432, url.database, url.username)


def resolve_test_database_url(test_url: str | None, dev_url: str | None) -> str:
    if not test_url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is not set. Database tests need an isolated database "
            "(e.g. a dedicated Neon branch) and never fall back to DATABASE_URL. "
            "See README → 'Test database'."
        )
    if dev_url and _identity(test_url) == _identity(dev_url):
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL points at the same database as DATABASE_URL. "
            "Refusing to run tests against the development database."
        )
    return test_url


def database_url_for_tests() -> str:
    return resolve_test_database_url(_read("TEST_DATABASE_URL"), _read("DATABASE_URL"))
