"""Entry point wiring everything together."""
from app.auth.session import SessionManager
from app.core.engine import Engine
from app.utils import helpers


def run() -> None:
    """Start the demo app."""
    engine = Engine(SessionManager())
    engine.start(helpers.default_config())
