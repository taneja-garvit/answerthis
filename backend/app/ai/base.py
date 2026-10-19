"""Provider-neutral LLM interface. Domain services depend on this module only;
concrete providers live in app.ai.providers."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class LLMMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMRequest:
    task: str  # e.g. "claim_extraction", "claim_assessment"
    prompt_version: str
    messages: list[LLMMessage]
    # The structured inputs the prompt was rendered from. Used by the
    # deterministic provider instead of parsing prompt text. Never logged.
    payload: dict[str, Any] = field(default_factory=dict)
    max_output_tokens: int = 2048
    temperature: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    content: str  # raw JSON text, validated by app.ai.structured
    provider: str
    model: str | None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    attempts: int = 1


class LLMProvider(Protocol):
    name: str
    model: str | None

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        """Return a single JSON object as text. Raise an LLMError subclass on failure."""
        ...

    async def aclose(self) -> None: ...


class LLMError(Exception):
    """Base class. `str(exc)` is safe to show users: it never contains keys or prompts."""

    code = "llm_error"
    retryable = False


class LLMAuthError(LLMError):
    code = "llm_auth_failed"


class LLMRateLimitError(LLMError):
    code = "llm_rate_limited"
    retryable = True

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    retryable = True


class LLMProviderError(LLMError):
    code = "llm_provider_error"


class LLMInvalidOutputError(LLMError):
    """The provider itself reported that the model produced invalid JSON."""

    code = "llm_invalid_output"
