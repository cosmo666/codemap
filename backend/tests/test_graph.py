from pathlib import Path

from codemap.analyzer.graph import build_graph
from codemap.analyzer.parser import parse_repo

FIXTURE = Path(__file__).parent / "fixtures" / "demo_repo"


def test_build_graph_edges_and_centrality() -> None:
    graph = build_graph(parse_repo(FIXTURE))
    assert len(graph.nodes) == 10
    edge_set = {(e.source, e.target) for e in graph.edges}
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
