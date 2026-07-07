import re

from codemap.indexer.chunker import Chunk

CHAT_SYSTEM_PROMPT = (
    "You are CodeMap, an assistant that answers questions about a codebase using the "
    "provided context. Every claim about specific code MUST cite its module using the "
    "exact format [cite: <path>] with the path shown in the context, e.g. "
    "[cite: app/auth/session.py]. If the context is marked WEAK or does not contain "
    "the answer, say you could not find relevant code — do not guess."
)

_CITE_RE = re.compile(r"\[cite:\s*([^\]]+?)\s*\]")


def build_context(hits: list[tuple[Chunk, float]], threshold: float) -> tuple[str, bool]:
    weak = not any(score >= threshold for _, score in hits)
    parts = [f"--- {chunk.path} (score {score:.2f})\n{chunk.text}" for chunk, score in hits]
    header = "CONTEXT (WEAK MATCHES)" if weak else "CONTEXT"
    return f"{header}:\n" + "\n\n".join(parts), weak


def extract_new_citations(text: str, seen: set[str]) -> list[str]:
    new: list[str] = []
    for match in _CITE_RE.finditer(text):
        path = match.group(1)
        if path not in seen:
            seen.add(path)
            new.append(path)
    return new
