from pathlib import Path

from codemap.analyzer.graph import build_graph
from codemap.analyzer.parser import parse_repo

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def test_stdlib_only_imports_produce_no_edges(tmp_path: Path) -> None:
    (tmp_path / "only_stdlib.py").write_text("import os\nimport sys\n\nx = os.getcwd()\n")
    (tmp_path / "other.py").write_text("x = 1\n")
    graph = build_graph(parse_repo(tmp_path))
    assert len(graph.nodes) == 2
    edges_from_stdlib_module = [e for e in graph.edges if e.source == "only_stdlib.py"]
    assert edges_from_stdlib_module == []


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
