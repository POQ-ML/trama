"""Conector UFC — interface, sem integração real."""
from __future__ import annotations

from .base import BaseConnector, ConnectorResult


class UFCConnector(BaseConnector):
    """FUTURO: dados institucionais da UFC (SIGAA/cursos/eventos).

    Deverá fornecer: cursos, projetos e eventos acadêmicos oficiais.
    Hoje apenas declara o contrato.
    """

    source_id: str = "ufc"

    async def fetch(self, query: str = "", limit: int = 20) -> ConnectorResult:
        raise NotImplementedError

    async def health_check(self) -> bool:
        raise NotImplementedError
