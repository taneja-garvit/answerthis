"""Groq chat-completions provider (OpenAI-compatible HTTP API, JSON mode).

Uses httpx directly so no vendor SDK leaks into the codebase. Retries 429,
5xx, timeouts and network errors with bounded exponential backoff, honouring
Retry-After. The API key is only ever placed in the Authorization header."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import httpx
from pydantic import SecretStr

from app.ai.base import (
    LLMAuthError,
    LLMError,
    LLMInvalidOutputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


def _error_detail(response: httpx.Response) -> tuple[str | None, str]:
    try:
        error = response.json().get("error", {})
        return error.get("code"), str(error.get("message", ""))[:300]
    except Exception:
        return None, ""


class GroqLLMProvider:
    name = "groq"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        max_backoff_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._max_backoff = max_backoff_seconds
        self._client = client or httpx.AsyncClient()
        self._sleep = sleep

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(self, request: LLMRequest) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }

    async def complete_json(self, request: LLMRequest) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        body = self._body(request)
        started = time.perf_counter()
        for attempt in range(1, self._max_retries + 2):
            error: LLMError
            delay: float | None = None
            try:
                response = await self._client.post(
                    self._url, json=body, headers=headers, timeout=self._timeout
                )
            except httpx.TimeoutException:
                error = LLMTimeoutError(f"The AI provider timed out after {self._timeout:.0f}s.")
            except httpx.TransportError as exc:
                error = LLMProviderError(f"Could not reach the AI provider ({type(exc).__name__}).")
                error.retryable = True
            else:
                if response.status_code == 200:
                    return self._parse_success(request, response, started, attempt)
                code, message = _error_detail(response)
                status = response.status_code
                if status in (401, 403):
                    raise LLMAuthError(
                        "The AI provider rejected the credentials (check GROQ_API_KEY)."
                    )
                if status == 400 and code == "json_validate_failed":
                    raise LLMInvalidOutputError("The model produced invalid JSON.")
                if status == 429:
                    delay = _retry_after(response)
                    error = LLMRateLimitError(
                        "The AI provider's rate limit was reached. Wait and retry.", delay
                    )
                elif status >= 500:
                    error = LLMProviderError(f"The AI provider returned an error ({status}).")
                    error.retryable = True
                else:
                    detail = f"{status}: {message}" if message else str(status)
                    raise LLMProviderError(f"The AI provider rejected the request ({detail}).")

            if attempt > self._max_retries:
                raise error
            delay = min(self._max_backoff, delay if delay is not None else 2.0 ** (attempt - 1))
            logger.warning(
                "llm retry",
                extra={
                    "provider": self.name,
                    "task": request.task,
                    "attempt": attempt,
                    "error": error.code,
                    "delay_s": round(delay, 2),
                },
            )
            await self._sleep(delay)
        raise AssertionError("unreachable")

    def _parse_success(
        self, request: LLMRequest, response: httpx.Response, started: float, attempt: int
    ) -> LLMResponse:
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "The AI provider returned an unexpected response shape."
            ) from exc
        if not content:
            raise LLMInvalidOutputError("The model returned an empty response.")
        usage = {
            k: int(v)
            for k, v in (data.get("usage") or {}).items()
            if k in ("prompt_tokens", "completion_tokens", "total_tokens") and isinstance(v, int)
        }
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "llm call",
            extra={
                "provider": self.name,
                "model": data.get("model", self.model),
                "task": request.task,
                "prompt_version": request.prompt_version,
                "latency_ms": latency_ms,
                "attempts": attempt,
                "finish_reason": choice.get("finish_reason"),
                **usage,
            },
        )
        return LLMResponse(
            content=content,
            provider=self.name,
            model=data.get("model", self.model),
            usage=usage,
            latency_ms=latency_ms,
            attempts=attempt,
        )
