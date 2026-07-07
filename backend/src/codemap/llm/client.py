import asyncio
from collections.abc import AsyncIterator

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

    async def complete(self, system: str, user: str) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        async with self._semaphore:
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    response = await self._client.chat.completions.create(
                        model=self._model, messages=messages  # type: ignore[arg-type]
                    )
                    return response.choices[0].message.content or ""
                except _RETRYABLE as exc:
                    if attempt == _MAX_RETRIES:
                        raise
                    delay = self._retry_delay * 2**attempt
                    log.warning("llm_retry", attempt=attempt, delay=delay, error=str(exc))
                    await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def stream(
        self, system: str, user: str, history: list[ChatMessage] | None = None
    ) -> AsyncIterator[str]:
        messages: list[ChatMessage] = [{"role": "system", "content": system}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user})
        async with self._semaphore:
            response = await self._client.chat.completions.create(
                model=self._model, messages=messages, stream=True  # type: ignore[arg-type]
            )
            async for chunk in response:  # type: ignore[union-attr]
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
