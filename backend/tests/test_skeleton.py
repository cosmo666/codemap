from pathlib import Path

from codemap.analyzer.parser import parse_repo
from codemap.explainer.skeleton import build_skeleton

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def test_skeleton_contains_signatures_and_docstrings() -> None:
    parsed = {p.info.path: p for p in parse_repo(FIXTURE)}
    skeleton = build_skeleton(parsed["app/core/engine.py"])
    assert "app/core/engine.py" in skeleton
    assert "class Engine" in skeleton
    assert "Runs jobs for authenticated sessions." in skeleton
    assert "def start(self, config: dict)" in skeleton


def test_skeleton_respects_budget() -> None:
    parsed = {p.info.path: p for p in parse_repo(FIXTURE)}
    skeleton = build_skeleton(parsed["app/core/engine.py"], max_chars=50)
    assert len(skeleton) <= 50
