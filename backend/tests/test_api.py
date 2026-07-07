import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest

from codemap.api.app import create_app
from codemap.pipeline import Pipeline
from tests.test_index import fake_embed
from tests.test_pipeline import FakeLLM, make_settings

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns(".codemap"))
    return dest


def make_client() -> tuple[httpx.AsyncClient, Any]:
    llm: Any = FakeLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    app = create_app(settings=make_settings(), pipeline=pipeline)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), app


async def test_analyze_then_graph_and_module(repo: Path) -> None:
    client, app = make_client()
    async with client:
        response = await client.post("/analyze", json={"repo_path": str(repo)})
        assert response.status_code == 200
        analysis_id = response.json()["analysis_id"]

        # wait for background task to finish
        for _ in range(100):
            if app.state.analyses[analysis_id].done:
                break
            await asyncio.sleep(0.05)
        assert app.state.analyses[analysis_id].done

        graph = (await client.get("/graph")).json()
        assert len(graph["nodes"]) == 10
        assert graph["overview"] == "fake explanation"

        detail = (await client.get("/module/app/core/engine.py")).json()
        assert detail["node"]["id"] == "app/core/engine.py"
        assert "app/core/models.py" in detail["dependencies"]
        assert "app/main.py" in detail["dependents"]


async def test_analyze_missing_path() -> None:
    client, _ = make_client()
    async with client:
        response = await client.post("/analyze", json={"repo_path": "C:/nope/nothing"})
        assert response.status_code == 404


async def test_graph_before_analyze_is_404() -> None:
    client, _ = make_client()
    async with client:
        assert (await client.get("/graph")).status_code == 404


async def test_analyze_events_stream_and_404s(repo: Path) -> None:
    client, app = make_client()
    async with client:
        assert (await client.get("/analyze/nope/events")).status_code == 404

        analysis_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]

        stages: list[str] = []
        async with client.stream("GET", f"/analyze/{analysis_id}/events") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    event = json.loads(line[5:].strip())
                    stages.append(event["stage"])
                    if event["stage"] in ("done", "error"):
                        break
        assert stages[0] == "parsing"
        assert "explaining" in stages and "indexing" in stages
        assert stages[-1] == "done"

        assert (await client.get("/module/not/a/module.py")).status_code == 404
