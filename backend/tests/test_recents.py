import json
from pathlib import Path

from codemap.api.recents import (
    RecentEntry,
    default_recents_path,
    load_recents,
    upsert_recent,
)


def make_entry(repo_path: str = "C:/repos/alpha", *, name: str = "alpha") -> RecentEntry:
    return RecentEntry(
        repo_path=repo_path,
        name=name,
        analyzed_at="2026-07-07T12:00:00+00:00",
        modules=10,
        packages=3,
        languages=["python"],
    )


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_recents(tmp_path / "recents.json") == []


def test_load_corrupt_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    path.write_bytes(b"\x00 not json at all {{{")
    assert load_recents(path) == []


def test_load_wrong_shape_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    path.write_text(json.dumps({"recents": "nope"}), encoding="utf-8")
    assert load_recents(path) == []


def test_upsert_roundtrip_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "recents.json"
    entry = make_entry()
    upsert_recent(path, entry)
    assert load_recents(path) == [entry]


def test_upsert_writes_pretty_json(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    upsert_recent(path, make_entry())
    text = path.read_text(encoding="utf-8")
    assert text.count("\n") > 3  # indented: one field per line, not a single blob


def test_upsert_dedupes_by_repo_path_most_recent_first(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    upsert_recent(path, make_entry("C:/repos/a", name="a"))
    upsert_recent(path, make_entry("C:/repos/b", name="b"))
    upsert_recent(path, make_entry("C:/repos/a", name="a-updated"))
    entries = load_recents(path)
    assert [e.repo_path for e in entries] == ["C:/repos/a", "C:/repos/b"]
    assert entries[0].name == "a-updated"


def test_upsert_caps_at_twelve(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    for i in range(15):
        upsert_recent(path, make_entry(f"C:/repos/r{i}", name=f"r{i}"))
    entries = load_recents(path)
    assert len(entries) == 12
    assert entries[0].repo_path == "C:/repos/r14"
    assert entries[-1].repo_path == "C:/repos/r3"


def test_default_recents_path_is_under_home() -> None:
    assert default_recents_path() == Path.home() / ".codemap" / "recents.json"
