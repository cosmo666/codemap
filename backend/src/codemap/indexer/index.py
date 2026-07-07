import json
from collections.abc import Callable
from pathlib import Path

import faiss
import numpy as np

from codemap.indexer.chunker import Chunk

EmbedFn = Callable[[list[str]], np.ndarray]

_INDEX_FILE = "index.faiss"
_CHUNKS_FILE = "chunks.json"


def _default_embed_fn() -> EmbedFn:
    from fastembed import TextEmbedding

    model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(texts: list[str]) -> np.ndarray:
        return np.array(list(model.embed(texts)), dtype=np.float32)

    return embed


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized: np.ndarray = vectors / np.maximum(norms, 1e-10)
    return normalized


class VectorIndex:
    """FAISS inner-product index over normalized vectors (= cosine similarity)."""

    def __init__(self, embed_fn: EmbedFn | None = None) -> None:
        self._embed_fn = embed_fn or _default_embed_fn()
        self._chunks: list[Chunk] = []
        self._index: faiss.Index | None = None

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        vectors = _normalize(self._embed_fn([c.text for c in chunks]))
        self._index = faiss.IndexFlatIP(vectors.shape[1])
        self._index.add(vectors)

    def search(self, query: str, k: int = 8) -> list[tuple[Chunk, float]]:
        if self._index is None or not self._chunks:
            return []
        vector = _normalize(self._embed_fn([query]))
        scores, ids = self._index.search(vector, min(k, len(self._chunks)))
        return [
            (self._chunks[i], float(s))
            for i, s in zip(ids[0], scores[0], strict=True)
            if i >= 0
        ]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        assert self._index is not None
        faiss.write_index(self._index, str(directory / _INDEX_FILE))
        (directory / _CHUNKS_FILE).write_text(
            json.dumps([c.model_dump() for c in self._chunks]), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path, embed_fn: EmbedFn | None = None) -> "VectorIndex":
        instance = cls(embed_fn=embed_fn)
        instance._index = faiss.read_index(str(directory / _INDEX_FILE))
        raw = json.loads((directory / _CHUNKS_FILE).read_text(encoding="utf-8"))
        instance._chunks = [Chunk.model_validate(c) for c in raw]
        return instance
