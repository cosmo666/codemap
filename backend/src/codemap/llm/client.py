import asyncio
from collections.abc import AsyncIterator
from typing import Any

import openai
import structlog
from openai import AsyncOpenAI

from codemap.config import Settings

log = structlog.get_logger()

ChatMessage = dict[str, str]

_RETRYABLE = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)
_MAX_RETRIES = 3


class LLMClient:
    """Sole gateway to the LLM endpoint: retry, backoff, concurrency cap."""

    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self._client = client or AsyncOpenAI(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key
        )
        self._model = settings.llm_model
        self._retry_delay = settings.retry_delay
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def _create_with_retry(self, messages: list[ChatMessage], *, stream: bool) -> Any:
        """Retry the INITIAL request only - once a stream starts yielding tokens,
        retrying would duplicate or corrupt output already sent to the caller."""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await self._client.chat.completions.create(
                    model=self._model, messages=messages, stream=stream  # type: ignore[arg-type]
                )
            except _RETRYABLE as exc:
                if attempt == _MAX_RETRIES:
                    raise
                delay = self._retry_delay * 2**attempt
                log.warning("llm_retry", attempt=attempt, delay=delay, error=str(exc))
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def complete(self, system: str, user: str) -> str:
        messages: list[ChatMessage] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        async with self._semaphore:
            response = await self._create_with_retry(messages, stream=False)
            return response.choices[0].message.content or ""

    async def stream(
        self, system: str, user: str, history: list[ChatMessage] | None = None
    ) -> AsyncIterator[str]:
        messages: list[ChatMessage] = [{"role": "system", "content": system}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user})
        async with self._semaphore:
            response = await self._create_with_retry(messages, stream=True)
            async for chunk in response:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
