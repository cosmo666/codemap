import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from codemap.api.app import create_app
from codemap.api.chat import build_context, extract_new_citations
from codemap.indexer.chunker import Chunk
from codemap.pipeline import Pipeline
from tests.test_index import fake_embed
from tests.test_pipeline import FakeLLM, make_settings

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def make_chunk(path: str) -> Chunk:
    return Chunk(id=path, path=path, kind="function", name="f", text=f"code in {path}")


def test_build_context_weak_flag() -> None:
    strong = [(make_chunk("a.py"), 0.8), (make_chunk("b.py"), 0.2)]
    context, weak = build_context(strong, threshold=0.35)
    assert "a.py" in context and not weak
    _, weak2 = build_context([(make_chunk("a.py"), 0.1)], threshold=0.35)
    assert weak2


def test_extract_new_citations_incremental() -> None:
    seen: set[str] = set()
    assert extract_new_citations("see [cite: app/main.py] and", seen) == ["app/main.py"]
    assert extract_new_citations("see [cite: app/main.py] again", seen) == []
    assert extract_new_citations("[cite: app/core/engine.py]", seen) == ["app/core/engine.py"]


class StreamingFakeLLM(FakeLLM):
    def stream(
        self, system: str, user: str, history: Any = None
    ) -> AsyncIterator[str]:
        async def gen() -> AsyncIterator[str]:
            # Citation split across chunks: detection must work on the buffered text.
            for part in ["Auth lives in ", "[cite: app/auth/", "session.py]", " done."]:
                yield part

        return gen()


async def test_chat_streams_tokens_and_citations(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    llm: Any = StreamingFakeLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    app = create_app(settings=make_settings(), pipeline=pipeline, llm=llm)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        analysis_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]
        for _ in range(100):
            if app.state.analyses[analysis_id].done:
                break
            await asyncio.sleep(0.05)

        async with client.stream(
            "POST", "/chat", json={"question": "where is auth?", "history": []}
        ) as response:
            body = ""
            async for line in response.aiter_lines():
                body += line + "\n"
        events = [
            json.loads(line[5:].strip())
            for line in body.splitlines()
            if line.startswith("data:")
        ]
        types = [e["type"] for e in events]
        assert "token" in types
        citations = [e["path"] for e in events if e["type"] == "citation"]
        assert citations == ["app/auth/session.py"]  # exactly once, via buffered detection
        assert types[-1] == "done"


async def test_chat_before_analysis_is_404() -> None:
    llm: Any = StreamingFakeLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    app = create_app(settings=make_settings(), pipeline=pipeline, llm=llm)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/chat", json={"question": "hi", "history": []})
        assert response.status_code == 404
