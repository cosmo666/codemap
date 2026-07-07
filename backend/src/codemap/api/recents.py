"""Server-local registry of recently analyzed repos (~/.codemap/recents.json)."""

import json
from pathlib import Path

from pydantic import BaseModel

MAX_RECENTS = 12


class RecentEntry(BaseModel):
    repo_path: str
    name: str
    analyzed_at: str  # ISO 8601, UTC
    modules: int
    packages: int
    languages: list[str]


def default_recents_path() -> Path:
    return Path.home() / ".codemap" / "recents.json"


def load_recents(path: Path) -> list[RecentEntry]:
    """Read the registry; a missing or corrupt file simply means no recents."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [RecentEntry.model_validate(item) for item in raw]
    except Exception:  # noqa: BLE001 - registry is best-effort, never fatal
        return []


def upsert_recent(path: Path, entry: RecentEntry) -> None:
    """Insert `entry` at the front, deduped by repo_path, capped at MAX_RECENTS."""
    entries = [e for e in load_recents(path) if e.repo_path != entry.repo_path]
    entries.insert(0, entry)
    del entries[MAX_RECENTS:]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([e.model_dump() for e in entries], indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
