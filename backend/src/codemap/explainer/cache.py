import hashlib
import json
from pathlib import Path


def digest_of(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class ExplanationCache:
    """Persists explanations keyed by (path, content digest) in hash_cache.json."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, str]] = {}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def get(self, file_path: str, digest: str) -> str | None:
        entry = self._data.get(file_path)
        if entry and entry.get("digest") == digest:
            return entry["explanation"]
        return None

    def put(self, file_path: str, digest: str, explanation: str) -> None:
        self._data[file_path] = {"digest": digest, "explanation": explanation}

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
