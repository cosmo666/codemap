"""Core data models."""
from dataclasses import dataclass


@dataclass
class Job:
    """A unit of work."""

    name: str
