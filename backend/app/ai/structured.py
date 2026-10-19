"""LLM request → JSON → Pydantic validation, with bounded repair retries."""

import json
import logging
import re
from dataclasses import dataclass, replace

from pydantic import BaseModel, ValidationError

from app.ai.base import (
    LLMError,
    LLMInvalidOutputError,
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class StructuredOutputError(LLMError):
    code = "llm_invalid_output"


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    value: T
    response: LLMResponse
    calls: int  # provider calls made, including repair retries


def _parse_json(content: str) -> object:
    match = _FENCE.match(content)
    return json.loads(match.group(1) if match else content)


def _summarize(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        # Location and message only; never the offending input.
        parts = [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()[:8]
        ]
        return "; ".join(parts)
    if isinstance(exc, json.JSONDecodeError):
        return f"invalid JSON ({exc.msg})"
    return type(exc).__name__


async def generate_structured[T: BaseModel](
    provider: LLMProvider, request: LLMRequest, schema: type[T], *, max_retries: int
) -> StructuredResult[T]:
    """Call the provider and validate its JSON against `schema`. On invalid
    output, re-ask with the validation errors, at most `max_retries` times.
    Transport-level errors (rate limits, timeouts) are retried by the provider
    and propagate from here unchanged."""
    messages = list(request.messages)
    last_problem = "no response"
    for attempt in range(1, max_retries + 2):
        try:
            response = await provider.complete_json(replace(request, messages=messages))
        except LLMInvalidOutputError:
            last_problem = "provider reported invalid JSON"
            messages = [
                *request.messages,
                LLMMessage(
                    "user",
                    "Your previous reply was not valid JSON. Reply with one JSON object only.",
                ),
            ]
        else:
            try:
                value = schema.model_validate(_parse_json(response.content))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_problem = _summarize(exc)
                messages = [
                    *request.messages,
                    LLMMessage("assistant", response.content[:6000]),
                    LLMMessage(
                        "user",
                        "Your previous reply did not match the required schema: "
                        f"{last_problem}. Reply again with one JSON object that matches "
                        "the schema exactly. Do not add commentary.",
                    ),
                ]
            else:
                return StructuredResult(value=value, response=response, calls=attempt)
        logger.warning(
            "structured output invalid",
            extra={"task": request.task, "attempt": attempt, "problem": last_problem[:300]},
        )
    raise StructuredOutputError(
        f"The AI provider returned invalid structured output after {max_retries + 1} "
        f"attempt(s): {last_problem[:300]}"
    )
