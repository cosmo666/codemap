import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from codemap.api.chat import CHAT_SYSTEM_PROMPT, build_context, extract_new_citations
from codemap.config import Settings
from codemap.llm.client import LLMClient
from codemap.logging import configure_logging
from codemap.pipeline import Pipeline, PipelineEvent

log = structlog.get_logger()


class AnalyzeRequest(BaseModel):
    repo_path: str


class ChatRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = []


@dataclass
class AnalysisRun:
    queue: asyncio.Queue[PipelineEvent] = field(default_factory=asyncio.Queue)
    done: bool = False
    task: asyncio.Task[None] | None = None


def create_app(
    settings: Settings | None = None,
    pipeline: Pipeline | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    configure_logging()
    settings = settings or Settings()  # type: ignore[call-arg]  # fields sourced from env/.env
    app = FastAPI(title="CodeMap", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.state.settings = settings
    app.state.pipeline = pipeline or Pipeline(settings)
    app.state.llm = llm or LLMClient(settings)
    app.state.analyses = {}
    app.state.graph = None
    app.state.index = None

    @app.post("/analyze")
    async def analyze(request: AnalyzeRequest) -> dict[str, str]:
        repo = Path(request.repo_path)
        if not repo.is_dir():
            raise HTTPException(status_code=404, detail=f"Not a directory: {repo}")
        analysis_id = uuid.uuid4().hex[:12]
        run = AnalysisRun()
        app.state.analyses[analysis_id] = run
        loop = asyncio.get_running_loop()

        def on_event(event: PipelineEvent) -> None:
            loop.call_soon_threadsafe(run.queue.put_nowait, event)

        async def execute() -> None:
            try:
                graph, index = await app.state.pipeline.run(repo, on_event)
                app.state.graph = graph
                app.state.index = index
            except Exception as exc:  # noqa: BLE001 - report, don't crash the server
                log.error("analysis_failed", error=str(exc))
                run.queue.put_nowait(PipelineEvent(stage="error", detail=str(exc)))
            finally:
                run.done = True

        run.task = asyncio.create_task(execute())
        return {"analysis_id": analysis_id}

    @app.get("/analyze/{analysis_id}/events")
    async def analyze_events(analysis_id: str) -> EventSourceResponse:
        run = app.state.analyses.get(analysis_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Unknown analysis")

        async def stream() -> AsyncIterator[dict[str, str]]:
            while True:
                try:
                    event = await asyncio.wait_for(run.queue.get(), timeout=1.0)
                except TimeoutError:
                    if run.done:
                        break
                    continue
                yield {"data": event.model_dump_json()}
                if event.stage in ("done", "error"):
                    break

        return EventSourceResponse(stream())

    @app.get("/graph")
    async def get_graph() -> dict:  # type: ignore[type-arg]
        if app.state.graph is None:
            raise HTTPException(status_code=404, detail="No analysis yet")
        return json.loads(app.state.graph.model_dump_json())  # type: ignore[no-any-return]

    @app.get("/module/{path:path}")
    async def get_module(path: str) -> dict:  # type: ignore[type-arg]
        if app.state.graph is None:
            raise HTTPException(status_code=404, detail="No analysis yet")
        node = next((n for n in app.state.graph.nodes if n.id == path), None)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Unknown module: {path}")
        dependencies = [e.target for e in app.state.graph.edges if e.source == path]
        dependents = [e.source for e in app.state.graph.edges if e.target == path]
        return {
            "node": json.loads(node.model_dump_json()),
            "dependencies": dependencies,
            "dependents": dependents,
        }

    @app.post("/chat")
    async def chat(request: ChatRequest) -> EventSourceResponse:
        if app.state.index is None:
            raise HTTPException(status_code=404, detail="No analysis yet")
        hits = app.state.index.search(request.question, k=8)
        context, _weak = build_context(hits, settings.similarity_threshold)

        async def stream() -> AsyncIterator[dict[str, str]]:
            seen: set[str] = set()
            buffer = ""
            user = f"{context}\n\nQUESTION: {request.question}"
            async for token in app.state.llm.stream(
                CHAT_SYSTEM_PROMPT, user, history=request.history
            ):
                buffer += token
                yield {"data": json.dumps({"type": "token", "content": token})}
                for path in extract_new_citations(buffer, seen):
                    yield {"data": json.dumps({"type": "citation", "path": path})}
            yield {"data": json.dumps({"type": "done"})}

        return EventSourceResponse(stream())

    return app
