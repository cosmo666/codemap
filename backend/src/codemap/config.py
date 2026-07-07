from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment / backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_base_url: str
    llm_api_key: str
    llm_model: str = "gpt-4.1-mini"
    max_concurrency: int = 5
    similarity_threshold: float = 0.35
    retry_delay: float = 2.0
    # Recents registry location; None -> ~/.codemap/recents.json (Docker sets
    # RECENTS_PATH to a volume path, tests point it at tmp_path).
    recents_path: Path | None = None
