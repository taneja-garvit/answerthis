import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.papers.base import PaperProviderError

logger = logging.getLogger(__name__)
Sleep = Callable[[float], Awaitable[None]]


async def get_json(
    client: httpx.AsyncClient,
    provider: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    request_timeout: float,
    max_retries: int,
    max_backoff: float = 10.0,
    sleep: Sleep = asyncio.sleep,
) -> dict[str, Any] | None:
    """GET JSON with bounded retries on 429/5xx/timeouts (honouring Retry-After).
    Returns None on 404."""
    for attempt in range(1, max_retries + 2):
        started = time.perf_counter()
        kind = "unavailable"
        delay: float | None = None
        try:
            response = await client.get(url, params=params, timeout=request_timeout)
        except httpx.TimeoutException:
            kind = "timeout"
        except httpx.TransportError:
            kind = "unavailable"
        else:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "paper provider call",
                extra={
                    "provider": provider,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                },
            )
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise PaperProviderError(provider, "bad_response") from exc
            if response.status_code == 404:
                return None
            if response.status_code == 429:
                kind = "rate_limited"
                try:
                    delay = float(response.headers.get("retry-after", ""))
                except ValueError:
                    delay = None
            elif response.status_code < 500:
                raise PaperProviderError(provider, "bad_response")
        if attempt > max_retries:
            logger.warning("paper provider failed", extra={"provider": provider, "kind": kind})
            raise PaperProviderError(provider, kind)  # type: ignore[arg-type]
        await sleep(min(max_backoff, delay if delay is not None else 0.5 * 2 ** (attempt - 1)))
    raise AssertionError("unreachable")
