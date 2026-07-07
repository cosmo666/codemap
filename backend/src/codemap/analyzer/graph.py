import networkx as nx
from pydantic import BaseModel

from codemap.analyzer.models import ParsedModule


class GraphNode(BaseModel):
    id: str
    module: str
    package: str
    loc: int
    status: str
    centrality: float
    explanation: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    packages: list[str]
    overview: str | None = None


def _resolve_target(imported: str, by_module: dict[str, str]) -> str | None:
    """Resolve a dotted import to a known module path, trying longest prefix first."""
    parts = imported.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in by_module:
            return by_module[candidate]
    return None


def build_graph(parsed: list[ParsedModule]) -> GraphData:
    by_module = {p.info.module: p.info.path for p in parsed}
    g = nx.DiGraph()
    g.add_nodes_from(p.info.path for p in parsed)
    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str]] = set()
    for p in parsed:
        for imported in p.info.imports:
            target = _resolve_target(imported, by_module)
            if target and target != p.info.path:
                edge_key = (p.info.path, target)
                if edge_key not in seen_edges:
                    g.add_edge(p.info.path, target)
                    edges.append(GraphEdge(source=p.info.path, target=target))
                    seen_edges.add(edge_key)
    centrality: dict[str, float] = (
        nx.in_degree_centrality(g) if g.number_of_nodes() > 1 else {}
    )
    nodes = [
        GraphNode(
            id=p.info.path,
            module=p.info.module,
            package=p.info.package,
            loc=p.info.loc,
            status=p.info.status,
            centrality=round(centrality.get(p.info.path, 0.0), 4),
        )
        for p in parsed
    ]
    packages = sorted({p.info.package for p in parsed if p.info.package != "root"})
    return GraphData(nodes=nodes, edges=edges, packages=packages)
