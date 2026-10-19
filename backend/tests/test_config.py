import pytest
from pydantic import ValidationError

from app.db.session import normalize_database_url
from tests.conftest import make_settings
from tests.db_guard import UnsafeTestDatabaseError, resolve_test_database_url

DEV = "postgresql://dev_user:dev_pw@ep-dev-123.eu-central-1.aws.neon.tech/neondb?sslmode=require"
TEST_BRANCH = (
    "postgresql://dev_user:dev_pw@ep-test-456.eu-central-1.aws.neon.tech/neondb?sslmode=require"
)


def test_groq_provider_requires_key_and_model():
    with pytest.raises(ValidationError) as exc:
        make_settings(DEV, llm_provider="groq")
    message = str(exc.value)
    assert "GROQ_API_KEY" in message and "LLM_MODEL" in message


def test_groq_provider_requires_model_even_with_key():
    with pytest.raises(ValidationError, match="LLM_MODEL"):
        make_settings(DEV, llm_provider="groq", groq_api_key="gsk-test")


def test_blank_values_count_as_missing():
    with pytest.raises(ValidationError, match="GROQ_API_KEY"):
        make_settings(DEV, llm_provider="groq", groq_api_key="  ", llm_model="m")


def test_groq_provider_accepts_complete_configuration():
    settings = make_settings(DEV, llm_provider="groq", groq_api_key="gsk-test", llm_model="m-1")
    assert settings.llm_model == "m-1"


def test_unsupported_provider_rejected():
    with pytest.raises(ValidationError):
        make_settings(DEV, llm_provider="anthropic")


def test_deterministic_provider_needs_no_key():
    settings = make_settings(DEV)
    assert settings.llm_provider == "deterministic"
    assert settings.groq_api_key is None


def test_factory_builds_configured_provider():
    from app.ai.factory import build_llm_provider

    assert build_llm_provider(make_settings(DEV)).name == "deterministic"
    groq = build_llm_provider(
        make_settings(DEV, llm_provider="groq", groq_api_key="gsk-test", llm_model="m-1")
    )
    assert (groq.name, groq.model) == ("groq", "m-1")


def test_secrets_are_not_rendered_in_repr():
    settings = make_settings(DEV, llm_provider="groq", groq_api_key="gsk-secret", llm_model="m")
    rendered = repr(settings) + str(settings.model_dump())
    assert "dev_pw" not in rendered
    assert "gsk-secret" not in rendered


def test_cors_origins_parse_from_comma_separated_string():
    settings = make_settings(DEV, cors_origins="http://localhost:5173, http://127.0.0.1:5173")
    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_neon_url_is_normalized_to_async_psycopg_and_keeps_ssl(scheme):
    url = normalize_database_url(
        f"{scheme}://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require"
    )
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"
    assert url.query["channel_binding"] == "require"
    assert "p@" not in str(url)  # password masked when rendered


def test_non_postgres_url_rejected():
    with pytest.raises(ValueError):
        normalize_database_url("mysql://u:p@localhost/db")


def test_missing_test_database_url_fails_explicitly():
    with pytest.raises(UnsafeTestDatabaseError, match="TEST_DATABASE_URL is not set"):
        resolve_test_database_url(None, DEV)


def test_test_database_identical_to_dev_is_refused():
    same_db_other_params = DEV.replace("sslmode=require", "sslmode=verify-full")
    with pytest.raises(UnsafeTestDatabaseError, match="same database"):
        resolve_test_database_url(same_db_other_params, DEV)


def test_separate_neon_branch_is_accepted():
    assert resolve_test_database_url(TEST_BRANCH, DEV) == TEST_BRANCH


def test_separate_database_on_same_host_is_accepted():
    other_db = DEV.replace("/neondb", "/neondb_test")
    assert resolve_test_database_url(other_db, DEV) == other_db
