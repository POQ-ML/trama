"""Registro simples de conectores — sem I/O, sem singletons globais."""
from __future__ import annotations

from .base import BaseConnector


class ConnectorRegistry:
    """Registra e recupera conectores por `source_id`."""

    def __init__(self) -> None:
        self._items: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        """Registra um conector (sobrescreve mesmo `source_id`)."""
        key = connector.source_id or type(connector).__name__
        self._items[key] = connector

    def get(self, source_id: str) -> BaseConnector | None:
        """Retorna o conector ou None se ausente."""
        return self._items.get(source_id)

    def list(self) -> list[str]:
        """Lista os `source_id`s registrados."""
        return sorted(self._items.keys())
