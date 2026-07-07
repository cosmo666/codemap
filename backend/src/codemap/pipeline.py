import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel

from codemap.analyzer.graph import GraphData, build_graph
from codemap.analyzer.parser import parse_repo
from codemap.config import Settings
from codemap.explainer.cache import ExplanationCache
from codemap.explainer.explainer import Explainer, SupportsComplete
from codemap.indexer.chunker import Chunk, chunk_module, chunk_summaries
from codemap.indexer.index import EmbedFn, VectorIndex
from codemap.llm.client import LLMClient

log = structlog.get_logger()


class PipelineEvent(BaseModel):
    stage: Literal["parsing", "explaining", "indexing", "done", "error"]
    current: int | None = None
    total: int | None = None
    detail: str | None = None


class Store:
    """Human-inspectable artifacts under <repo>/.codemap/."""

    def __init__(self, repo: Path) -> None:
        self.dir = repo / ".codemap"

    @property
    def cache_path(self) -> Path:
        return self.dir / "hash_cache.json"

    def save_graph(self, graph: GraphData) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "graph.json").write_text(graph.model_dump_json(indent=2), "utf-8")

    def load_graph(self) -> GraphData | None:
        path = self.dir / "graph.json"
        if not path.exists():
            return None
        return GraphData.model_validate_json(path.read_text("utf-8"))

    def save_explanations(self, modules: dict[str, str], packages: dict[str, str]) -> None:
        import json

        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {"modules": modules, "packages": packages}
        (self.dir / "explanations.json").write_text(json.dumps(payload, indent=2), "utf-8")


class Pipeline:
    """parse -> explain (map-reduce) -> index -> persist."""

    def __init__(
        self,
        settings: Settings,
        llm: SupportsComplete | None = None,
        embed_fn: EmbedFn | None = None,
    ) -> None:
        self._settings = settings
        self._llm = llm or LLMClient(settings)
        self._embed_fn = embed_fn

    async def run(
        self, repo_path: Path, on_event: Callable[[PipelineEvent], None]
    ) -> tuple[GraphData, VectorIndex]:
        store = Store(repo_path)
        on_event(PipelineEvent(stage="parsing"))
        parsed = parse_repo(repo_path)
        graph = build_graph(parsed)

        explainer = Explainer(self._llm, ExplanationCache(store.cache_path))
        ok_total = sum(1 for p in parsed if p.info.status == "ok")
        on_event(PipelineEvent(stage="explaining", current=0, total=ok_total))
        explanations = await explainer.explain_all(
            parsed,
            lambda c, t, d: on_event(
                PipelineEvent(stage="explaining", current=c, total=t, detail=d)
            ),
        )
        packages = await explainer.summarize_packages(explanations, parsed)
        overview = await explainer.overview(packages)
        for node in graph.nodes:
            node.explanation = explanations.get(node.id)
        graph.overview = overview or None

        on_event(PipelineEvent(stage="indexing"))
        chunks: list[Chunk] = []
        for pm in parsed:
            if pm.info.status == "ok":
                chunks.extend(chunk_module(pm))
        chunks.extend(chunk_summaries(explanations))

        def build_index() -> VectorIndex:
            index = VectorIndex(embed_fn=self._embed_fn)
            index.build(chunks)
            return index

        index = await asyncio.to_thread(build_index)

        store.save_graph(graph)
        store.save_explanations(explanations, packages)
        index.save(store.dir)
        on_event(PipelineEvent(stage="done"))
        return graph, index
