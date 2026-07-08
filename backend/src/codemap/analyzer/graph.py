from pathlib import PurePosixPath
from typing import Literal

import networkx as nx
from pydantic import BaseModel

from codemap.analyzer.models import ParsedModule


class GraphNode(BaseModel):
    id: str
    module: str
    package: str
    loc: int
    status: Literal["ok", "parse_error"]
    centrality: float
    explanation: str | None = None
    # Default keeps previously persisted graph.json valid on warm start.
    language: str = "python"


class GraphEdge(BaseModel):
    source: str
    target: str
    # Default keeps previously persisted graph.json valid on warm start: every
    # edge written before this field existed was a real import dependency.
    kind: Literal["import", "structural"] = "import"


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    packages: list[str]
    overview: str | None = None


def _resolve_target(imported: str, by_module: dict[str, list[str]]) -> str | None:
    """Resolve a dotted import to a known module path, trying longest prefix
    first. A module name claimed by several files (e.g. svc/bar.py and
    svc/bar.rb both mapping to "svc.bar") is ambiguous: skip it and keep
    trying shorter prefixes rather than guessing the wrong target."""
    parts = imported.split(".")
    for end in range(len(parts), 0, -1):
        paths = by_module.get(".".join(parts[:end]))
        if paths is not None and len(paths) == 1:
            return paths[0]
    return None


def _structural_edges(paths: list[str], existing: set[tuple[str, str]]) -> list[GraphEdge]:
    """Chain files that share a parent folder into a spine (alphabetical,
    consecutive pairs) so directory structure stays visible on the map even
    where static analysis finds no import between them. Never duplicates a
    pair an import edge already covers, and never feeds centrality/sizing -
    this is a visual affordance, not a claimed dependency."""
    by_folder: dict[str, list[str]] = {}
    for path in paths:
        by_folder.setdefault(str(PurePosixPath(path).parent), []).append(path)
    edges: list[GraphEdge] = []
    for siblings in by_folder.values():
        siblings.sort()
        for a, b in zip(siblings, siblings[1:], strict=False):  # deliberately unequal length
            if (a, b) in existing or (b, a) in existing:
                continue
            edges.append(GraphEdge(source=a, target=b, kind="structural"))
    return edges


def build_graph(parsed: list[ParsedModule]) -> GraphData:
    by_module: dict[str, list[str]] = {}
    for p in parsed:
        by_module.setdefault(p.info.module, []).append(p.info.path)
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
    edges.extend(_structural_edges([p.info.path for p in parsed], seen_edges))
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
            language=p.info.language,
        )
        for p in parsed
    ]
    packages = sorted({p.info.package for p in parsed if p.info.package != "root"})
    return GraphData(nodes=nodes, edges=edges, packages=packages)
