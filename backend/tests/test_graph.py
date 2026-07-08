from pathlib import Path

from codemap.analyzer.graph import GraphEdge, build_graph
from codemap.analyzer.parser import parse_repo

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def test_stdlib_only_imports_produce_no_edges(tmp_path: Path) -> None:
    (tmp_path / "only_stdlib.py").write_text("import os\nimport sys\n\nx = os.getcwd()\n")
    (tmp_path / "other.py").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    assert len(graph.nodes) == 2
    import_edges_from_stdlib_module = [
        e for e in graph.edges if e.source == "only_stdlib.py" and e.kind == "import"
    ]
    assert import_edges_from_stdlib_module == []


def test_ambiguous_module_name_across_languages_drops_edge(tmp_path: Path) -> None:
    # svc/bar.py and svc/bar.rb both claim module "svc.bar"; guessing would point
    # the Python import at whichever file sorts last, so the edge must drop.
    (tmp_path / "svc").mkdir()
    (tmp_path / "main.py").write_text("import svc.bar\n")
    (tmp_path / "svc" / "bar.py").write_text("x = 1\n")
    (tmp_path / "svc" / "bar.rb").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    assert [e for e in graph.edges if e.source == "main.py"] == []


def test_ambiguous_module_name_falls_back_to_shorter_prefix(tmp_path: Path) -> None:
    # "svc.bar" is ambiguous, but the shorter prefix "svc" (the package
    # __init__) is unique and still resolves.
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "__init__.py").write_text("")
    (tmp_path / "main.py").write_text("import svc.bar\n")
    (tmp_path / "svc" / "bar.py").write_text("x = 1\n")
    (tmp_path / "svc" / "bar.rb").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    import_edges = {(e.source, e.target) for e in graph.edges if e.kind == "import"}
    assert import_edges == {("main.py", "svc/__init__.py")}


def test_structural_edges_chain_files_in_the_same_folder(tmp_path: Path) -> None:
    # Three unrelated files (no imports between them) in one folder still get
    # visually connected via a "structural" spine so the map isn't a point cloud.
    folder = tmp_path / "models"
    folder.mkdir()
    (folder / "a.py").write_text("x = 1\n")
    (folder / "b.py").write_text("x = 1\n")
    (folder / "c.py").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    structural = {(e.source, e.target) for e in graph.edges if e.kind == "structural"}
    # alphabetical spine within the folder: a-b, b-c (not a full a-b-a-c mesh)
    assert structural == {("models/a.py", "models/b.py"), ("models/b.py", "models/c.py")}


def test_structural_edges_do_not_cross_folders(tmp_path: Path) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "one" / "a.py").write_text("x = 1\n")
    (tmp_path / "two" / "b.py").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    assert [e for e in graph.edges if e.kind == "structural"] == []


def test_structural_edge_skipped_when_import_edge_already_connects_the_pair(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "svc"
    folder.mkdir()
    (folder / "a.py").write_text("import svc.b\n")
    (folder / "b.py").write_text("x = 1\n")
    (folder / "c.py").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    kinds = {(e.source, e.target): e.kind for e in graph.edges}
    # a->b is a real import edge; no duplicate structural edge drawn for that pair
    assert kinds[("svc/a.py", "svc/b.py")] == "import"
    assert ("svc/b.py", "svc/a.py") not in kinds
    # b-c still gets its structural spine link (the gap the import edge doesn't fill)
    assert kinds[("svc/b.py", "svc/c.py")] == "structural"


def test_graph_edge_kind_defaults_to_import_for_backward_compat() -> None:
    # Persisted graph.json written before the "kind" field existed must still
    # warm-start-validate cleanly, defaulting every old edge to "import".
    edge = GraphEdge.model_validate({"source": "a.py", "target": "b.py"})
    assert edge.kind == "import"


def test_build_graph_edges_and_centrality() -> None:
    graph = build_graph(parse_repo(FIXTURE))
    assert len(graph.nodes) == 10
    edge_set = {(e.source, e.target) for e in graph.edges}
    assert len(graph.edges) == len(edge_set)  # no duplicate edges
    assert ("app/main.py", "app/auth/session.py") in edge_set
    assert ("app/main.py", "app/core/engine.py") in edge_set
    assert ("app/core/engine.py", "app/core/models.py") in edge_set
    assert ("app/auth/session.py", "app/core/models.py") in edge_set
    # 'app.utils.helpers' import resolves via the package __init__ chain
    assert ("app/main.py", "app/utils/helpers.py") in edge_set
    by_id = {n.id: n for n in graph.nodes}
    # models.py is imported by engine + session -> highest in-degree centrality
    assert by_id["app/core/models.py"].centrality >= by_id["app/main.py"].centrality
    assert by_id["app/broken.py"].status == "parse_error"
    assert graph.packages == ["app"]
