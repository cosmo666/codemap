import shutil
from pathlib import Path
from typing import Any

import pytest

from codemap.analyzer import parser as parser_mod
from codemap.analyzer.graph import GraphNode, build_graph
from codemap.analyzer.models import ModuleInfo
from codemap.analyzer.parser import (
    discover_python_files,
    discover_source_files,
    parse_module,
    parse_repo,
)
from codemap.explainer.skeleton import build_skeleton
from codemap.indexer.chunker import chunk_module
from codemap.pipeline import Pipeline, Store
from tests.test_index import fake_embed
from tests.test_pipeline import FakeLLM, make_settings

POLYGLOT = Path(__file__).parent / "fixtures" / "demo_polyglot"
DEMO = Path(__file__).parent / "fixtures" / "demo_repo"


# --- discovery ---------------------------------------------------------------


def test_discover_source_files_polyglot() -> None:
    rels = [f.relative_to(POLYGLOT).as_posix() for f in discover_source_files(POLYGLOT)]
    # sorted() both sides: Path ordering is case-insensitive only on Windows
    assert sorted(rels) == sorted(
        [
            "c/src/main.c",
            "c/src/util/strings.c",
            "c/src/util/strings.h",
            "cpp/geometry.hpp",
            "cpp/main.cpp",
            "cpp/widget.h",
            "csharp/Acme/App/Program.cs",
            "csharp/Acme/Util/Strings.cs",
            "go/go.mod",  # unregistered-but-texty: raw-fallback node
            "go/main.go",
            "go/util/count.go",
            "go/util/strings.go",
            "java/com/acme/app/Main.java",
            "java/com/acme/util/Strings.java",
            "php/src/Util/Strings.php",
            "php/src/index.php",
            "ruby/app.rb",
            "ruby/lib/greeter.rb",
            "rust/src/helpers.rs",
            "rust/src/main.rs",
            "rust/src/util/geometry.rs",
            "rust/src/util/mod.rs",
            "scripts/tool.lua",
            "web/api.ts",
            "web/broken.ts",
            "web/components/index.ts",
            "web/util.js",
        ]
    )


def test_discover_skips_minified_and_huge(tmp_path: Path) -> None:
    (tmp_path / "keep.ts").write_text("const x = 1;\n")
    (tmp_path / "bundle.min.js").write_text("var a=1;\n")
    (tmp_path / "huge.js").write_text("//" + "x" * 2_000_000)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("var b=2;\n")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "sneaky.py").write_text("x = 1\n")
    files = [f.name for f in discover_source_files(tmp_path)]
    assert files == ["keep.ts"]


def test_discover_python_files_still_python_only() -> None:
    assert discover_python_files(POLYGLOT) == []
    # demo_repo is all-Python: the generalized walk finds the same files
    assert discover_source_files(DEMO) == discover_python_files(DEMO)


def test_unregistered_texty_extensions_become_raw_nodes(tmp_path: Path) -> None:
    # Spec: every source file becomes a node; unknown-but-texty extensions get
    # raw-fallback nodes, binary files stay invisible.
    (tmp_path / "main.py").write_text("x = 1\n")
    (tmp_path / "README.md").write_text("# Demo\n")
    (tmp_path / "config.yaml").write_text("key: value\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x01binary")
    names = sorted(f.name for f in discover_source_files(tmp_path))
    assert names == ["Dockerfile", "README.md", "config.yaml", "main.py"]
    info = {p.info.path: p.info for p in parse_repo(tmp_path)}
    readme = info["README.md"]
    assert readme.status == "ok"
    assert readme.language == "md"
    assert readme.imports == [] and readme.classes == [] and readme.functions == []
    # extension kept in the module name: raw nodes never collide with real modules
    assert readme.module == "README.md"
    assert info["Dockerfile"].language == "text"  # no extension at all


# --- deep JS/TS parsing ------------------------------------------------------


def test_parse_typescript_module() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "web" / "api.ts")
    info = pm.info
    assert info.language == "typescript"
    assert info.module == "web.api"
    assert info.package == "web"
    assert info.status == "ok"
    # relative imports resolved to module names; bare specifier 'fs' dropped
    assert info.imports == ["web.components", "web.util"]
    assert [f.name for f in info.functions] == ["getPanel"]
    fn = info.functions[0]
    assert fn.signature == "export function getPanel(id: string): Panel {"
    assert fn.docstring == "Fetches a panel by id."
    assert fn.lineno == 6  # 1-based
    assert [c.name for c in info.classes] == ["ApiClient"]
    methods = {m.name: m for m in info.classes[0].methods}
    assert set(methods) == {"constructor", "fetchJson"}
    assert methods["fetchJson"].docstring == "Fetch JSON from a path."


def test_parse_javascript_module() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "web" / "util.js")
    info = pm.info
    assert info.language == "javascript"
    assert info.module == "web.util"
    assert info.imports == ["web.components"]  # require('./components') -> index.ts
    names = [f.name for f in info.functions]
    assert names == ["formatLabel", "slugify"]
    assert info.functions[0].docstring == "Formats a label for display."


def test_index_module_collapses_to_directory() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "web" / "components" / "index.ts")
    assert pm.info.module == "web.components"
    assert pm.info.imports == ["web.util"]


def test_broken_ts_is_parse_error() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "web" / "broken.ts")
    assert pm.info.status == "parse_error"
    assert pm.info.language == "typescript"
    assert pm.info.imports == []
    assert pm.info.classes == [] and pm.info.functions == []


# --- universal tier ----------------------------------------------------------


def test_universal_lua_gets_symbols_no_imports() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "scripts" / "tool.lua")
    info = pm.info
    assert info.language == "lua"
    assert info.status == "ok"
    assert info.imports == []
    greet = next(f for f in info.functions if f.name == "greet")
    assert greet.signature == "function greet(name)"
    assert greet.docstring == "Prints a greeting."
    assert greet.lineno == 2 and greet.end_lineno == 4


def test_grammar_load_failure_raw_fallback_for_universal_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A missing grammar downgrades a universal-tier file to a raw node
    # (status stays ok); a deep-tier file becomes parse_error.
    (tmp_path / "tool.lua").write_text("x = 1\n")
    (tmp_path / "api.ts").write_text("export const y = 1;\n")
    monkeypatch.setattr(parser_mod, "_load_language", lambda _name: None)
    lua = parse_module(tmp_path, tmp_path / "tool.lua").info
    assert lua.status == "ok"
    assert lua.language == "lua"
    assert lua.imports == [] and lua.classes == [] and lua.functions == []
    ts = parse_module(tmp_path, tmp_path / "api.ts").info
    assert ts.status == "parse_error"


# --- graph edges -------------------------------------------------------------


def test_polyglot_graph_edges_exact() -> None:
    graph = build_graph(parse_repo(POLYGLOT))
    by_id = {n.id: n for n in graph.nodes}
    assert len(graph.nodes) == 27
    assert by_id["web/api.ts"].language == "typescript"
    assert by_id["web/util.js"].language == "javascript"
    assert by_id["scripts/tool.lua"].language == "lua"
    assert by_id["web/broken.ts"].status == "parse_error"
    assert by_id["c/src/util/strings.h"].language == "c"
    assert by_id["cpp/geometry.hpp"].language == "cpp"
    assert by_id["cpp/widget.h"].language == "cpp"  # .h retried under the C++ grammar
    assert by_id["cpp/widget.h"].status == "ok"
    assert by_id["go/go.mod"].language == "mod"  # raw-fallback node
    assert by_id["go/go.mod"].status == "ok"
    edge_set = {(e.source, e.target) for e in graph.edges}
    assert edge_set == {
        # JS/TS
        ("web/api.ts", "web/util.js"),  # TS -> JS
        ("web/api.ts", "web/components/index.ts"),  # TS -> TS via index collapse
        ("web/components/index.ts", "web/util.js"),  # TS -> JS
        ("web/util.js", "web/components/index.ts"),  # JS -> TS via require
        # Go: package import fans out to every file in the package dir
        ("go/main.go", "go/util/count.go"),
        ("go/main.go", "go/util/strings.go"),
        # Java
        ("java/com/acme/app/Main.java", "java/com/acme/util/Strings.java"),
        # Rust
        ("rust/src/main.rs", "rust/src/helpers.rs"),
        ("rust/src/main.rs", "rust/src/util/mod.rs"),
        ("rust/src/main.rs", "rust/src/util/geometry.rs"),
        ("rust/src/util/mod.rs", "rust/src/util/geometry.rs"),
        ("rust/src/util/geometry.rs", "rust/src/helpers.rs"),
        # C#
        ("csharp/Acme/App/Program.cs", "csharp/Acme/Util/Strings.cs"),
        # C / C++
        ("c/src/main.c", "c/src/util/strings.h"),
        ("c/src/util/strings.c", "c/src/util/strings.h"),
        ("cpp/main.cpp", "cpp/geometry.hpp"),
        ("cpp/widget.h", "cpp/geometry.hpp"),
        # Ruby / PHP
        ("ruby/app.rb", "ruby/lib/greeter.rb"),
        ("php/src/index.php", "php/src/Util/Strings.php"),
    }
    # universal-tier node has no edges at all
    assert not any("tool.lua" in e.source or "tool.lua" in e.target for e in graph.edges)


# --- backward compat ---------------------------------------------------------


def test_language_defaults_keep_old_artifacts_valid() -> None:
    node = GraphNode.model_validate(
        {"id": "a.py", "module": "a", "package": "root", "loc": 1, "status": "ok", "centrality": 0}
    )
    assert node.language == "python"
    info = ModuleInfo.model_validate(
        {
            "path": "a.py",
            "module": "a",
            "package": "root",
            "imports": [],
            "classes": [],
            "functions": [],
            "docstring": None,
            "loc": 1,
            "status": "ok",
        }
    )
    assert info.language == "python"


def test_python_fixture_language_tagged() -> None:
    parsed = parse_repo(DEMO)
    assert len(parsed) == 10
    assert all(p.info.language == "python" for p in parsed)


def test_parse_repo_accepts_relative_repo_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Import resolvers compare .resolve()d targets against the repo root; an
    # unresolved repo path must not flip valid files to parse_error.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "util.ts").write_text("export const x = 1;\n")
    (repo / "api.ts").write_text("import { x } from './util';\nexport const y = x;\n")
    monkeypatch.chdir(tmp_path)
    info = {p.info.path: p.info for p in parse_repo(Path("repo"))}
    assert info["api.ts"].status == "ok"
    assert info["api.ts"].imports == ["util"]


# --- skeleton ----------------------------------------------------------------


def test_skeleton_typescript_signatures_and_docs() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "web" / "api.ts")
    skeleton = build_skeleton(pm)
    assert "web/api.ts" in skeleton
    assert "typescript" in skeleton
    assert "export function getPanel(id: string): Panel {" in skeleton
    assert "Fetches a panel by id." in skeleton
    assert "ApiClient" in skeleton


def test_skeleton_raw_fallback_for_symbolless_file(tmp_path: Path) -> None:
    file = tmp_path / "plain.lua"
    file.write_text('x = 1\nprint("just statements")\n')
    pm = parse_module(tmp_path, file)
    skeleton = build_skeleton(pm)
    assert "lua" in skeleton
    assert 'print("just statements")' in skeleton
    assert len(build_skeleton(pm, max_chars=50)) <= 50


# --- chunker -----------------------------------------------------------------


def test_chunker_symbol_boundaries_for_lua() -> None:
    pm = parse_module(POLYGLOT, POLYGLOT / "scripts" / "tool.lua")
    chunks = chunk_module(pm)
    fn_chunk = next(c for c in chunks if c.kind == "function" and c.name == "greet")
    assert "function greet(name)" in fn_chunk.text
    assert "end" in fn_chunk.text  # 1-based spans cover the full body


def test_chunker_whole_file_when_no_symbols(tmp_path: Path) -> None:
    file = tmp_path / "plain.lua"
    file.write_text("x = 1\nprint(x)\n")
    pm = parse_module(tmp_path, file)
    chunks = chunk_module(pm)
    assert [c.id for c in chunks] == ["plain.lua::module"]
    assert "print(x)" in chunks[0].text


# --- pipeline integration ----------------------------------------------------


async def test_pipeline_polyglot_end_to_end(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(POLYGLOT, repo, ignore=shutil.ignore_patterns(".codemap"))
    llm: Any = FakeLLM()
    pipeline = Pipeline(make_settings(), llm=llm, embed_fn=fake_embed)
    graph, index = await pipeline.run(repo, lambda e: None)
    by_id = {n.id: n for n in graph.nodes}
    assert by_id["web/broken.ts"].explanation is None
    assert by_id["web/api.ts"].explanation == "fake explanation"
    assert by_id["scripts/tool.lua"].explanation == "fake explanation"
    assert index.search("panel", k=2)
    reloaded = Store(repo).load_graph()
    assert reloaded is not None
    assert {n.language for n in reloaded.nodes} == {
        "typescript",
        "javascript",
        "lua",
        "go",
        "java",
        "rust",
        "csharp",
        "c",
        "cpp",
        "ruby",
        "php",
        "mod",  # go.mod: raw-fallback node
    }
