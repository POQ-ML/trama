"""Conector Moodle — interface, sem integração real."""
from __future__ import annotations

from .base import BaseConnector, ConnectorResult


class MoodleConnector(BaseConnector):
    """FUTURO: cursos, turmas, materiais e participações do Moodle.

    Deverá fornecer: listagem de cursos, eventos e evidências de
    participação. Hoje apenas declara o contrato.
    """

    source_id: str = "moodle"

    async def fetch(self, query: str = "", limit: int = 20) -> ConnectorResult:
        raise NotImplementedError

    async def health_check(self) -> bool:
        raise NotImplementedError
