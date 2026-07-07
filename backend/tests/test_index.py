import hashlib
from pathlib import Path

import numpy as np

from codemap.indexer.chunker import Chunk
from codemap.indexer.index import VectorIndex


def fake_embed(texts: list[str]) -> np.ndarray:
    """Deterministic embedding: seeded by text hash; similar only when identical."""
    out = np.zeros((len(texts), 32), dtype=np.float32)
    for i, text in enumerate(texts):
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        out[i] = rng.random(32, dtype=np.float32)
    return out


def make_chunk(name: str, text: str) -> Chunk:
    return Chunk(id=f"x/{name}", path=f"x/{name}.py", kind="function", name=name, text=text)


def test_search_finds_exact_text_first(tmp_path: Path) -> None:
    chunks = [make_chunk("auth", "def login(): ..."), make_chunk("db", "def query(): ...")]
    index = VectorIndex(embed_fn=fake_embed)
    index.build(chunks)
    results = index.search("def login(): ...", k=2)
    assert results[0][0].name == "auth"
    assert results[0][1] > results[1][1]

    index.save(tmp_path)
    loaded = VectorIndex.load(tmp_path, embed_fn=fake_embed)
    results2 = loaded.search("def login(): ...", k=2)
    assert results2[0][0].name == "auth"


def test_build_truncates_embed_input_but_keeps_full_chunk_text() -> None:
    seen_lengths: list[int] = []

    def spy_embed(texts: list[str]) -> np.ndarray:
        seen_lengths.extend(len(t) for t in texts)
        return fake_embed(texts)

    big = make_chunk("big", "x" * 10_000)
    index = VectorIndex(embed_fn=spy_embed)
    index.build([big])
    assert max(seen_lengths) <= 4000
    assert len(index._chunks[0].text) == 10_000  # stored chunk untouched


def test_build_empty_chunks_is_safe() -> None:
    index = VectorIndex(embed_fn=fake_embed)
    index.build([])
    assert index.search("anything") == []
