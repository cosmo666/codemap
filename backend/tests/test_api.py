import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from codemap.api.app import AnalysisRun, create_app
from codemap.api.recents import load_recents, upsert_recent
from codemap.pipeline import Pipeline
from tests.test_index import fake_embed
from tests.test_pipeline import FakeLLM, make_settings
from tests.test_recents import make_entry

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


@pytest.fixture(autouse=True)
def _isolated_recents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every API test's recents registry inside tmp_path, never ~/.codemap."""
    monkeypatch.setenv("RECENTS_PATH", str(tmp_path / "recents.json"))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns(".codemap"))
    return dest


async def wait_done(app: Any, analysis_id: str) -> None:
    for _ in range(100):
        if app.state.analyses[analysis_id].done:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("analysis did not finish")


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


async def test_warm_start_serves_persisted_graph_immediately(repo: Path) -> None:
    client1, app1 = make_client()
    async with client1:
        analysis_id = (
            await client1.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]
        for _ in range(100):
            if app1.state.analyses[analysis_id].done:
                break
            await asyncio.sleep(0.05)
        assert app1.state.analyses[analysis_id].done

    # Second app instance, same repo (now has .codemap/ artifacts on disk from the run above).
    client2, app2 = make_client()
    async with client2:
        response = await client2.post("/analyze", json={"repo_path": str(repo)})
        assert response.status_code == 200

        # Immediately (before the background pipeline task finishes) the persisted
        # graph should already be visible via warm-start.
        graph = (await client2.get("/graph")).json()
        assert len(graph["nodes"]) == 10


async def test_warm_start_survives_corrupt_artifacts(repo: Path) -> None:
    # A corrupted graph.json must not 500 the POST; analysis proceeds fresh.
    codemap_dir = repo / ".codemap"
    codemap_dir.mkdir()
    (codemap_dir / "graph.json").write_bytes(b"\x00 not json at all {{{")
    client, app = make_client()
    async with client:
        response = await client.post("/analyze", json={"repo_path": str(repo)})
        assert response.status_code == 200
        analysis_id = response.json()["analysis_id"]

        for _ in range(100):
            if app.state.analyses[analysis_id].done:
                break
            await asyncio.sleep(0.05)
        assert app.state.analyses[analysis_id].done

        graph = await client.get("/graph")
        assert graph.status_code == 200
        assert len(graph.json()["nodes"]) == 10


async def test_analyze_relative_repo_path_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The UI posts free-text paths verbatim; a relative repo path must not
    # degrade analysis (unresolved repo vs resolved import targets used to flip
    # syntactically valid files to parse_error).
    rel = tmp_path / "rel_repo"
    rel.mkdir()
    (rel / "util.ts").write_text("export const x = 1;\n")
    (rel / "api.ts").write_text("import { x } from './util';\nexport const y = x;\n")
    monkeypatch.chdir(tmp_path)
    client, app = make_client()
    async with client:
        response = await client.post("/analyze", json={"repo_path": "rel_repo"})
        assert response.status_code == 200
        analysis_id = response.json()["analysis_id"]
        for _ in range(100):
            if app.state.analyses[analysis_id].done:
                break
            await asyncio.sleep(0.05)
        assert app.state.analyses[analysis_id].done
        graph = (await client.get("/graph")).json()
        assert {n["id"]: n["status"] for n in graph["nodes"]} == {
            "api.ts": "ok",
            "util.ts": "ok",
        }
    # artifacts land under the canonical repo directory
    assert (rel / ".codemap" / "graph.json").exists()


async def test_analyze_missing_path() -> None:
    client, _ = make_client()
    async with client:
        response = await client.post("/analyze", json={"repo_path": "C:/nope/nothing"})
        assert response.status_code == 404


async def test_graph_before_analyze_is_404() -> None:
    client, _ = make_client()
    async with client:
        assert (await client.get("/graph")).status_code == 404


async def test_chat_history_rejects_invalid_role() -> None:
    client, _ = make_client()
    async with client:
        response = await client.post(
            "/chat",
            json={
                "question": "hi",
                "history": [{"role": "system", "content": "not allowed"}],
            },
        )
        assert response.status_code == 422


async def test_evicts_old_done_analyses(repo: Path) -> None:
    client, app = make_client()
    async with client:
        for i in range(8):
            app.state.analyses[f"fake-{i}"] = AnalysisRun(done=True)

        response = await client.post("/analyze", json={"repo_path": str(repo)})
        assert response.status_code == 200
        analysis_id = response.json()["analysis_id"]

        # 5 most-recent DONE fake runs survive, plus the freshly registered (unfinished) run
        assert len(app.state.analyses) == 6
        fake_ids = [aid for aid in app.state.analyses if aid.startswith("fake-")]
        assert fake_ids == [f"fake-{i}" for i in range(3, 8)]
        assert analysis_id in app.state.analyses

        for _ in range(100):
            if app.state.analyses[analysis_id].done:
                break
            await asyncio.sleep(0.05)
        assert app.state.analyses[analysis_id].done


async def test_no_eviction_below_done_cap(repo: Path) -> None:
    # Under the cap (5), pruning must evict NOTHING — guards against a negative-slice
    # bug where done_ids[:-excess] with negative excess evicts from the front.
    client, app = make_client()
    async with client:
        for i in range(3):
            app.state.analyses[f"fake-{i}"] = AnalysisRun(done=True)

        first_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]
        fake_ids = [aid for aid in app.state.analyses if aid.startswith("fake-")]
        assert fake_ids == ["fake-0", "fake-1", "fake-2"]  # 3 done < cap: none evicted

        for _ in range(100):
            if app.state.analyses[first_id].done:
                break
            await asyncio.sleep(0.05)
        assert app.state.analyses[first_id].done

        # Now 4 done runs (3 fakes + the finished real one) — still under the cap.
        await client.post("/analyze", json={"repo_path": str(repo)})
        fake_ids = [aid for aid in app.state.analyses if aid.startswith("fake-")]
        assert fake_ids == ["fake-0", "fake-1", "fake-2"]  # 4 done < cap: none evicted
        assert first_id in app.state.analyses


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


async def test_analyze_events_stream_sends_heartbeat_during_slow_explain(
    repo: Path,
) -> None:
    # A rate-limited/slow LLM call must not leave the SSE stream silent long
    # enough for a proxy's idle-read timeout to kill it (observed in Docker
    # behind nginx as a spurious "connection lost").
    class SlowLLM(FakeLLM):
        async def complete(self, system: str, user: str) -> str:
            await asyncio.sleep(1.5)
            return await super().complete(system, user)

    llm: Any = SlowLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    app = create_app(settings=make_settings(), pipeline=pipeline)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        analysis_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]

        saw_heartbeat = False
        stages: list[str] = []
        async with client.stream("GET", f"/analyze/{analysis_id}/events") as response:
            async for line in response.aiter_lines():
                if line.startswith(":"):
                    saw_heartbeat = True
                elif line.startswith("data:"):
                    event = json.loads(line[5:].strip())
                    stages.append(event["stage"])
                    if event["stage"] in ("done", "error"):
                        break
        assert saw_heartbeat, "expected a keep-alive comment during the slow explain gap"
        assert stages[-1] == "done"


async def test_analyze_events_stream_closes_after_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = make_client()

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(app.state.pipeline, "run", boom)
    async with client:
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

        # exactly one error event, and the stream ended on its own (loop above returned)
        assert stages == ["error"]
        assert app.state.analyses[analysis_id].done


async def test_recent_lists_analyzed_repo(repo: Path) -> None:
    client, app = make_client()
    async with client:
        analysis_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]
        await wait_done(app, analysis_id)

        graph = (await client.get("/graph")).json()
        response = await client.get("/recent")
        assert response.status_code == 200
        recents = response.json()["recents"]
        assert len(recents) == 1
        entry = recents[0]
        assert entry["repo_path"] == str(repo.resolve())
        assert entry["name"] == repo.name
        assert entry["modules"] == len(graph["nodes"]) == 10
        assert entry["packages"] == len(graph["packages"])
        assert entry["languages"] == ["python"]
        analyzed_at = datetime.fromisoformat(entry["analyzed_at"])
        assert analyzed_at.tzinfo is not None
        assert analyzed_at.utcoffset() == datetime.now(UTC).utcoffset()


async def test_recent_filters_missing_paths_without_deleting(
    repo: Path, tmp_path: Path
) -> None:
    client, app = make_client()
    registry: Path = app.state.settings.recents_path
    ghost = make_entry(str(tmp_path / "gone"), name="gone")
    upsert_recent(registry, ghost)
    async with client:
        analysis_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]
        await wait_done(app, analysis_id)

        recents = (await client.get("/recent")).json()["recents"]
        assert [e["repo_path"] for e in recents] == [str(repo.resolve())]

    # the ghost entry is filtered from the response but never deleted from disk
    on_disk = {e.repo_path for e in load_recents(registry)}
    assert on_disk == {str(repo.resolve()), ghost.repo_path}


async def test_recents_write_failure_never_breaks_analysis(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("codemap.api.app.upsert_recent", boom)
    client, app = make_client()
    async with client:
        analysis_id = (
            await client.post("/analyze", json={"repo_path": str(repo)})
        ).json()["analysis_id"]
        await wait_done(app, analysis_id)

        graph = await client.get("/graph")
        assert graph.status_code == 200
        assert len(graph.json()["nodes"]) == 10
        assert (await client.get("/recent")).json()["recents"] == []


async def test_fs_lists_directories_only_sorted(tmp_path: Path) -> None:
    (tmp_path / "beta").mkdir()
    (tmp_path / "Alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "notes.txt").write_text("not a directory")
    client, _ = make_client()
    async with client:
        response = await client.get("/fs", params={"path": str(tmp_path)})
        assert response.status_code == 200
        body = response.json()
        assert body["path"] == str(tmp_path)
        assert body["parent"] == str(tmp_path.parent)
        assert [d["name"] for d in body["dirs"]] == ["Alpha", "beta"]  # case-insensitive sort
        assert body["dirs"][0]["path"] == str(tmp_path / "Alpha")


async def test_fs_404_on_file_or_missing_path(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("not a directory")
    client, _ = make_client()
    async with client:
        assert (await client.get("/fs", params={"path": str(file_path)})).status_code == 404
        missing = tmp_path / "nope"
        assert (await client.get("/fs", params={"path": str(missing)})).status_code == 404


async def test_fs_parent_is_none_at_filesystem_root(tmp_path: Path) -> None:
    root = Path(tmp_path.anchor)  # e.g. C:\ on Windows, / on POSIX
    client, _ = make_client()
    async with client:
        response = await client.get("/fs", params={"path": str(root)})
        assert response.status_code == 200
        assert response.json()["parent"] is None


async def test_fs_rejects_null_bytes() -> None:
    client, _ = make_client()
    async with client:
        response = await client.get("/fs", params={"path": "C:/x\x00y"})
        assert response.status_code == 404


async def test_fs_empty_path_defaults_to_repos_or_home() -> None:
    repos = Path("/repos")
    expected = repos.resolve() if repos.is_dir() else Path.home()
    client, _ = make_client()
    async with client:
        response = await client.get("/fs")
        assert response.status_code == 200
        assert response.json()["path"] == str(expected)
