"""Conector OpenAlex — interface, sem integração real."""
from __future__ import annotations

from .base import BaseConnector, ConnectorResult


class OpenAlexConnector(BaseConnector):
    """FUTURO: trabalhos, autores e citações da API OpenAlex.

    Deverá fornecer: publicações e vínculos autor/instituição como
    evidências de produção científica. Hoje apenas declara o contrato.
    """

    source_id: str = "openalex"

    async def fetch(self, query: str = "", limit: int = 20) -> ConnectorResult:
        raise NotImplementedError

    async def health_check(self) -> bool:
        raise NotImplementedError
