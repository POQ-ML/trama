"""Conector GitHub — interface, sem integração real."""
from __future__ import annotations

from .base import BaseConnector, ConnectorResult


class GitHubConnector(BaseConnector):
    """FUTURO: repositórios, commits, PRs e issues como evidências.

    Deverá fornecer: metadados de repos e atividade de código ligada
    a projetos/usuários. Hoje apenas declara o contrato.
    """

    source_id: str = "github"

    async def fetch(self, query: str = "", limit: int = 20) -> ConnectorResult:
        raise NotImplementedError

    async def health_check(self) -> bool:
        raise NotImplementedError
