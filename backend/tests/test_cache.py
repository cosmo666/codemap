from pathlib import Path

from codemap.explainer.cache import ExplanationCache, digest_of


def test_cache_roundtrip_and_invalidation(tmp_path: Path) -> None:
    cache_file = tmp_path / "hash_cache.json"
    cache = ExplanationCache(cache_file)
    d1 = digest_of("source v1")
    assert cache.get("a.py", d1) is None
    cache.put("a.py", d1, "explains a")
    cache.save()

    reloaded = ExplanationCache(cache_file)
    assert reloaded.get("a.py", d1) == "explains a"
    assert reloaded.get("a.py", digest_of("source v2")) is None  # content changed
