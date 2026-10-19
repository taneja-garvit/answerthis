import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from app.ai.base import (
    LLMAuthError,
    LLMInvalidOutputError,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMTimeoutError,
)
from app.ai.providers.groq import GroqLLMProvider
from app.ai.schemas import ExtractionOutput
from app.ai.structured import generate_structured

KEY = "gsk_test_secret_value"


def _completion(content: str, model: str = "test-model") -> dict:
    return {
        "model": model,
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _provider(
    recorder: Recorder, max_retries: int = 2, sleeps: list | None = None
) -> GroqLLMProvider:
    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return GroqLLMProvider(
        api_key=SecretStr(KEY),
        model="test-model",
        base_url="https://groq.test/openai/v1",
        timeout_seconds=5,
        max_retries=max_retries,
        client=httpx.AsyncClient(transport=httpx.MockTransport(recorder)),
        sleep=fake_sleep,
    )


def _request() -> LLMRequest:
    return LLMRequest(
        task="claim_extraction",
        prompt_version="claim_extraction.v1",
        messages=[LLMMessage("system", "Return JSON."), LLMMessage("user", "PRIVATE DRAFT")],
    )


async def test_success_sends_json_mode_request_and_parses_usage():
    recorder = Recorder(httpx.Response(200, json=_completion('{"claims": []}')))
    response = await _provider(recorder).complete_json(_request())
    sent = recorder.requests[0]
    body = json.loads(sent.content)
    assert sent.url == "https://groq.test/openai/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "test-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert response.content == '{"claims": []}'
    assert response.usage == {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    assert (response.provider, response.model, response.attempts) == ("groq", "test-model", 1)


async def test_rate_limit_honours_retry_after_then_succeeds():
    sleeps: list[float] = []
    recorder = Recorder(
        httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"message": "rate"}}),
        httpx.Response(200, json=_completion("{}")),
    )
    response = await _provider(recorder, sleeps=sleeps).complete_json(_request())
    assert sleeps == [3.0]
    assert response.attempts == 2


async def test_persistent_rate_limit_is_bounded():
    sleeps: list[float] = []
    recorder = Recorder(*[httpx.Response(429, json={}) for _ in range(5)])
    with pytest.raises(LLMRateLimitError):
        await _provider(recorder, max_retries=2, sleeps=sleeps).complete_json(_request())
    assert len(recorder.requests) == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff without Retry-After


async def test_backoff_is_capped():
    sleeps: list[float] = []
    recorder = Recorder(
        httpx.Response(429, headers={"retry-after": "999"}, json={}),
        httpx.Response(200, json=_completion("{}")),
    )
    await _provider(recorder, sleeps=sleeps).complete_json(_request())
    assert sleeps == [20.0]


async def test_server_error_is_retried():
    recorder = Recorder(httpx.Response(503, json={}), httpx.Response(200, json=_completion("{}")))
    assert (await _provider(recorder).complete_json(_request())).attempts == 2


async def test_timeout_is_retried_then_raised():
    recorder = Recorder(*[httpx.ReadTimeout("slow") for _ in range(3)])
    with pytest.raises(LLMTimeoutError):
        await _provider(recorder).complete_json(_request())
    assert len(recorder.requests) == 3


async def test_auth_error_is_not_retried_and_never_reveals_key(caplog):
    caplog.set_level(logging.DEBUG)
    recorder = Recorder(httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    with pytest.raises(LLMAuthError) as exc:
        await _provider(recorder).complete_json(_request())
    assert len(recorder.requests) == 1
    assert KEY not in str(exc.value)
    assert KEY not in caplog.text
    assert "PRIVATE DRAFT" not in caplog.text


async def test_json_validate_failed_maps_to_invalid_output():
    recorder = Recorder(
        httpx.Response(400, json={"error": {"code": "json_validate_failed", "message": "bad"}})
    )
    with pytest.raises(LLMInvalidOutputError):
        await _provider(recorder).complete_json(_request())


async def test_other_client_error_is_not_retried():
    recorder = Recorder(
        httpx.Response(404, json={"error": {"code": "model_not_found", "message": "no such model"}})
    )
    with pytest.raises(LLMProviderError, match="no such model"):
        await _provider(recorder).complete_json(_request())
    assert len(recorder.requests) == 1


async def test_empty_content_is_invalid_output():
    recorder = Recorder(httpx.Response(200, json=_completion("")))
    with pytest.raises(LLMInvalidOutputError):
        await _provider(recorder).complete_json(_request())


async def test_structured_layer_repairs_groq_output():
    recorder = Recorder(
        httpx.Response(200, json=_completion('{"claims": [{"sentence_id": 1}]}')),
        httpx.Response(
            200, json=_completion('{"claims": [{"sentence_id": "S1", "claim_text": "X is Y."}]}')
        ),
    )
    result = await generate_structured(
        _provider(recorder), _request(), ExtractionOutput, max_retries=2
    )
    assert result.value.claims[0].claim_text == "X is Y."
    assert result.calls == 2
