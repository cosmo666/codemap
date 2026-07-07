from typing import Literal

from pydantic import BaseModel

from codemap.analyzer.models import ParsedModule


class Chunk(BaseModel):
    id: str
    path: str
    kind: Literal["module", "class", "function", "summary"]
    name: str
    text: str


def chunk_module(pm: ParsedModule) -> list[Chunk]:
    """Chunk at AST boundaries: each class/function, plus leftover module-level code."""
    lines = pm.source.splitlines()
    chunks: list[Chunk] = []
    covered: set[int] = set()
    spans: list[tuple[str, str, int, int]] = [
        ("class", c.name, c.lineno, c.end_lineno) for c in pm.info.classes
    ] + [("function", f.name, f.lineno, f.end_lineno) for f in pm.info.functions]
    for kind, name, start, end in spans:
        covered.update(range(start, end + 1))
        text = "\n".join(lines[start - 1 : end])
        chunks.append(
            Chunk(
                id=f"{pm.info.path}::{kind}::{name}",
                path=pm.info.path,
                kind=kind,  # type: ignore[arg-type]
                name=name,
                text=f"# {pm.info.path}\n{text}",
            )
        )
    leftover = [
        line for i, line in enumerate(lines, start=1) if i not in covered and line.strip()
    ]
    if leftover:
        chunks.append(
            Chunk(
                id=f"{pm.info.path}::module",
                path=pm.info.path,
                kind="module",
                name=pm.info.path,
                text=f"# {pm.info.path}\n" + "\n".join(leftover),
            )
        )
    return chunks


def chunk_summaries(explanations: dict[str, str]) -> list[Chunk]:
    return [
        Chunk(
            id=f"{path}::summary",
            path=path,
            kind="summary",
            name=path,
            text=f"Summary of {path}: {text}",
        )
        for path, text in explanations.items()
    ]
