"""Connectors — contrato de ingestão (interfaces, sem integração real)."""
from __future__ import annotations

from .base import BaseConnector, ConnectorResult
from .github_connector import GitHubConnector
from .moodle import MoodleConnector
from .openalex import OpenAlexConnector
from .registry import ConnectorRegistry
from .ufc import UFCConnector

__all__ = [
    "BaseConnector",
    "ConnectorRegistry",
    "ConnectorResult",
    "GitHubConnector",
    "MoodleConnector",
    "OpenAlexConnector",
    "UFCConnector",
]
