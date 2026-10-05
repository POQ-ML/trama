"""Contrato base dos conectores — interface, sem I/O real."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConnectorResult:
    """Resultado padronizado de um fetch (tipos mínimos locais)."""

    items: list[dict]
    fetched_at: str = ""
    source_id: str = ""


class BaseConnector(ABC):
    """Contrato que todo conector deve implementar."""

    source_id: str = ""

    @abstractmethod
    async def fetch(self, query: str = "", limit: int = 20) -> ConnectorResult:
        """Busca itens na fonte. Retorna `ConnectorResult`."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Retorna True se a fonte está acessível."""
