import shutil
from pathlib import Path
from typing import Any

from codemap.config import Settings
from codemap.pipeline import Pipeline, PipelineEvent, Store
from tests.test_index import fake_embed

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


class FakeLLM:
    async def complete(self, system: str, user: str) -> str:
        return "fake explanation"


def make_settings() -> Settings:
    return Settings(
        _env_file=None, llm_base_url="https://x.example/v1", llm_api_key="sk-t"
    )


async def test_pipeline_end_to_end(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    events: list[PipelineEvent] = []
    llm: Any = FakeLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    graph, index = await pipeline.run(repo, events.append)

    stages = [e.stage for e in events]
    assert stages[0] == "parsing"
    assert "explaining" in stages and "indexing" in stages
    assert stages[-1] == "done"

    explaining = [e for e in events if e.stage == "explaining"]
    assert len({e.total for e in explaining}) == 1  # total never jumps
    broken = next(n for n in graph.nodes if n.id == "app/broken.py")
    assert broken.explanation is None

    ok_nodes = [n for n in graph.nodes if n.status == "ok"]
    assert all(n.explanation == "fake explanation" for n in ok_nodes)
    assert graph.overview == "fake explanation"
    assert index.search("session", k=3)

    store = Store(repo)
    assert (store.dir / "graph.json").exists()
    assert (store.dir / "explanations.json").exists()
    assert (store.dir / "hash_cache.json").exists()
    assert (store.dir / "index.faiss").exists()
    reloaded = store.load_graph()
    assert reloaded is not None and len(reloaded.nodes) == len(graph.nodes)


class FailingOverviewLLM(FakeLLM):
    async def complete(self, system: str, user: str) -> str:
        if "architectural overview" in system:
            raise RuntimeError("overview boom")
        return await super().complete(system, user)


async def test_pipeline_overview_failure_yields_none(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    llm: Any = FailingOverviewLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    graph, _index = await pipeline.run(repo, lambda e: None)
    assert graph.overview is None
