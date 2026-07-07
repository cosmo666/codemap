"""Session management and authentication."""
from app.core.models import Job


class SessionManager:
    """Tracks active user sessions."""

    def __init__(self) -> None:
        self.active: dict[str, str] = {}

    def login(self, user: str, token: str) -> None:
        """Authenticate a user."""
        self.active[user] = token

    def logout(self, user: str) -> None:
        self.active.pop(user, None)

    def audit_job(self, job: Job) -> str:
        return f"{job.name}:{len(self.active)}"
