from pathlib import Path

from codemap.analyzer.parser import discover_python_files, parse_repo

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def test_discover_skips_junk(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("x = 1")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "skip.py").write_text("x = 1")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "skip.py").write_text("x = 1")
    files = discover_python_files(tmp_path)
    assert [f.name for f in files] == ["keep.py"]


def test_parse_repo_fixture() -> None:
    parsed = parse_repo(FIXTURE)
    by_path = {p.info.path: p for p in parsed}
    assert len(parsed) == 10
    engine = by_path["app/core/engine.py"].info
    assert engine.module == "app.core.engine"
    assert engine.package == "app"
    assert engine.status == "ok"
    assert "app.auth.session" in engine.imports
    assert "app.core.models" in engine.imports
    assert [c.name for c in engine.classes] == ["Engine"]
    assert [m.name for m in engine.classes[0].methods] == ["__init__", "start", "stop"]
    assert engine.classes[0].docstring == "Runs jobs for authenticated sessions."
    broken = by_path["app/broken.py"].info
    assert broken.status == "parse_error"
    assert broken.classes == [] and broken.functions == []
    init = by_path["app/__init__.py"].info
    assert init.module == "app"
