from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or inconsistent."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Evidence Review Workspace"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # Secrets are SecretStr so they never appear in reprs, logs or tracebacks.
    database_url: SecretStr | None = None
    db_pool_size: int = Field(default=3, ge=1, le=10)
    db_max_overflow: int = Field(default=2, ge=0, le=10)
    db_pool_timeout_seconds: int = Field(default=10, ge=1)
    db_pool_recycle_seconds: int = Field(default=300, ge=30)
    db_connect_timeout_seconds: int = Field(default=10, ge=1)

    llm_provider: Literal["deterministic", "groq"] = "deterministic"
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    # Applies separately to transport retries (429/5xx/timeouts) and to
    # structured-output retries (invalid JSON / schema). Always bounded.
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_backoff_seconds: float = Field(default=20.0, gt=0, le=120)

    contact_email: str | None = None
    openalex_api_key: SecretStr | None = None
    http_timeout_seconds: float = Field(default=10.0, gt=0)
    http_max_retries: int = Field(default=2, ge=0, le=5)
    paper_cache_ttl_days: int = Field(default=30, ge=1)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    max_draft_chars: int = Field(default=20_000, ge=100, le=200_000)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("groq_api_key", "openalex_api_key", "database_url", mode="before")
    @classmethod
    def _blank_secret_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("llm_model", "contact_email", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _validate_llm_provider(self) -> "Settings":
        if self.llm_provider == "groq":
            missing = [
                name
                for name, value in (
                    ("GROQ_API_KEY", self.groq_api_key),
                    ("LLM_MODEL", self.llm_model),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "LLM_PROVIDER=groq requires "
                    + " and ".join(missing)
                    + " to be set. Set them in .env, or use LLM_PROVIDER=deterministic."
                )
        return self

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise ConfigurationError(
                "DATABASE_URL is not set. Copy .env.example to .env and paste your "
                "Neon connection string."
            )
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
