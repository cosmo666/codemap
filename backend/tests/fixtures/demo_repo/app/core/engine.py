"""Core processing engine."""
from app.auth.session import SessionManager
from app.core.models import Job


class Engine:
    """Runs jobs for authenticated sessions."""

    def __init__(self, sessions: SessionManager) -> None:
        self.sessions = sessions
        self.jobs: list[Job] = []

    def start(self, config: dict) -> None:
        """Boot the engine."""
        self.jobs.append(Job(name=config.get("name", "default")))

    def stop(self) -> None:
        self.jobs.clear()
