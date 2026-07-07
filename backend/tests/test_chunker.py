from pathlib import Path

from codemap.analyzer.parser import parse_repo
from codemap.indexer.chunker import chunk_module, chunk_summaries

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def test_chunk_module_boundaries() -> None:
    parsed = {p.info.path: p for p in parse_repo(FIXTURE)}
    chunks = chunk_module(parsed["app/core/engine.py"])
    kinds = {(c.kind, c.name) for c in chunks}
    assert ("class", "Engine") in kinds
    assert ("module", "app/core/engine.py") in kinds
    class_chunk = next(c for c in chunks if c.kind == "class")
    assert "def start" in class_chunk.text
    module_chunk = next(c for c in chunks if c.kind == "module")
    assert "class Engine" not in module_chunk.text  # class body not duplicated
    assert "from app.core.models import Job" in module_chunk.text


def test_chunk_summaries() -> None:
    chunks = chunk_summaries({"a.py": "does things"})
    assert chunks[0].kind == "summary" and chunks[0].path == "a.py"


def test_chunk_module_empty_init_pins_single_whole_file_chunk() -> None:
    # v1.1 behavior change, pinned deliberately: a zero-symbol file always
    # yields exactly one raw whole-file chunk — including fully empty
    # __init__.py files, which produced zero chunks before v1.1.
    parsed = {p.info.path: p for p in parse_repo(FIXTURE)}
    chunks = chunk_module(parsed["app/auth/__init__.py"])
    assert [(c.id, c.kind) for c in chunks] == [("app/auth/__init__.py::module", "module")]
    assert chunks[0].text == "# app/auth/__init__.py\n"
