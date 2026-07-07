from types import SimpleNamespace
from typing import Any

import openai
import pytest

from codemap.config import Settings
from codemap.llm.client import LLMClient


class FakeRateLimit(openai.RateLimitError):
    """Fallback for testing when openai.RateLimitError constructor signature differs."""

    def __init__(self) -> None:
        Exception.__init__(self, "rate limited")


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://example.com/v1",
        llm_api_key="sk-test",
        retry_delay=0.0,
    )


class FakeCompletions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls = 0

    async def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result))]
        )


def make_client(responses: list[Any]) -> tuple[LLMClient, FakeCompletions]:
    fake = FakeCompletions(responses)
    inner = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return LLMClient(make_settings(), client=inner), fake  # type: ignore[arg-type]


async def test_complete_returns_content() -> None:
    client, fake = make_client(["hello"])
    assert await client.complete("sys", "user") == "hello"
    assert fake.calls == 1


async def test_complete_retries_on_rate_limit() -> None:
    err = FakeRateLimit()
    client, fake = make_client([err, err, "ok"])
    assert await client.complete("sys", "user") == "ok"
    assert fake.calls == 3


async def test_complete_gives_up_after_retries() -> None:
    err = FakeRateLimit()
    client, fake = make_client([err, err, err, err])
    with pytest.raises(openai.RateLimitError):
        await client.complete("sys", "user")
    assert fake.calls == 4


class FakeStreamCompletions:
    def __init__(self, deltas: list[str | None]) -> None:
        self.deltas = deltas
        self.calls = 0
        self.last_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        self.last_kwargs = kwargs
        deltas = self.deltas

        async def gen() -> Any:
            for delta in deltas:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=delta))]
                )

        return gen()


def make_stream_client(deltas: list[str | None]) -> tuple[LLMClient, FakeStreamCompletions]:
    fake = FakeStreamCompletions(deltas)
    inner = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return LLMClient(make_settings(), client=inner), fake  # type: ignore[arg-type]


async def test_stream_yields_only_non_empty_deltas() -> None:
    client, fake = make_stream_client(["hel", None, "", "lo"])
    chunks = [chunk async for chunk in client.stream("sys", "user")]
    assert chunks == ["hel", "lo"]
    assert fake.calls == 1


async def test_stream_includes_history_in_request() -> None:
    client, fake = make_stream_client(["ok"])
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
    chunks = [chunk async for chunk in client.stream("sys", "user", history=history)]
    assert chunks == ["ok"]
    assert fake.last_kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        *history,
        {"role": "user", "content": "user"},
    ]
    assert fake.last_kwargs["stream"] is True
