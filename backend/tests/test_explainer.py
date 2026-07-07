from pathlib import Path
from typing import Any

from codemap.analyzer.parser import parse_repo
from codemap.explainer.cache import ExplanationCache
from codemap.explainer.explainer import Explainer

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


class FakeLLM:
    def __init__(self, fail_paths: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on: set[str] = fail_paths or set()

    async def complete(self, system: str, user: str) -> str:
        self.calls.append(user)
        for path in self.fail_on:
            if path in user:
                raise RuntimeError("llm exploded")
        return f"EXPLANATION[{len(self.calls)}]"


async def test_explain_all_maps_and_caches(tmp_path: Path) -> None:
    parsed = parse_repo(FIXTURE)
    cache = ExplanationCache(tmp_path / "hash_cache.json")
    llm: Any = FakeLLM()
    explainer = Explainer(llm, cache)
    progress: list[tuple[int, int]] = []
    result = await explainer.explain_all(parsed, lambda c, t, d: progress.append((c, t)))
    ok_count = sum(1 for p in parsed if p.info.status == "ok")
    assert len(result) == ok_count  # parse_error module skipped
    assert "app/broken.py" not in result
    assert progress[-1][0] == ok_count

    # second run: fully cached, no new LLM calls
    calls_before = len(llm.calls)
    result2 = await explainer.explain_all(parsed, lambda c, t, d: None)
    assert result2 == result
    assert len(llm.calls) == calls_before


async def test_explain_all_survives_single_failure(tmp_path: Path) -> None:
    parsed = parse_repo(FIXTURE)
    llm: Any = FakeLLM(fail_paths={"app/core/engine.py"})
    explainer = Explainer(llm, ExplanationCache(tmp_path / "c.json"))
    result = await explainer.explain_all(parsed, lambda c, t, d: None)
    assert "app/core/engine.py" not in result  # unexplained, not fatal
    assert "app/auth/session.py" in result


async def test_reduce_stages(tmp_path: Path) -> None:
    parsed = parse_repo(FIXTURE)
    llm: Any = FakeLLM()
    explainer = Explainer(llm, ExplanationCache(tmp_path / "c.json"))
    explanations = await explainer.explain_all(parsed, lambda c, t, d: None)
    packages = await explainer.summarize_packages(explanations, parsed)
    assert set(packages) == {"app"}
    overview = await explainer.overview(packages)
    assert overview.startswith("EXPLANATION[")
