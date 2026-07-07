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


def test_relative_imports_in_init_files(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    sub = pkg / "sub"
    sub.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from .sub import thing\nfrom . import util\n")
    (pkg / "util.py").write_text("x = 1\n")
    (sub / "__init__.py").write_text("from ..util import x\nfrom .thing import T\n")
    (sub / "thing.py").write_text("class T:\n    pass\n")
    (sub / "use.py").write_text("from ..util import x\n")
    info = {p.info.path: p.info for p in parse_repo(tmp_path)}
    assert "pkg.sub" in info["pkg/__init__.py"].imports
    assert "pkg.util" in info["pkg/__init__.py"].imports
    assert "pkg.util" in info["pkg/sub/__init__.py"].imports
    assert "pkg.sub.thing" in info["pkg/sub/__init__.py"].imports
    assert "pkg.util" in info["pkg/sub/use.py"].imports


def test_null_bytes_file_is_parse_error(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_bytes(b"x = 1\x00")
    parsed = parse_repo(tmp_path)
    assert parsed[0].info.status == "parse_error"
