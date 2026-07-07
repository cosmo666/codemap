from pathlib import Path

from pytest import MonkeyPatch

from codemap.config import Settings


def test_settings_load_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://example.com/v1"
    assert s.llm_model == "gpt-4.1-mini"
    assert s.max_concurrency == 5
    assert s.similarity_threshold == 0.35
    assert s.recents_path is None


def test_settings_recents_path_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("RECENTS_PATH", str(Path("C:/data") / "recents.json"))
    s = Settings(_env_file=None)
    assert s.recents_path == Path("C:/data") / "recents.json"
