"""Context engine — interface, sem chamada real a modelos."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ContextEngine(ABC):
    """Monta e resume contexto para os agentes."""

    @abstractmethod
    def build_context(self, items: list[dict], query: str = "") -> str:
        """Compõe um contexto textual a partir de itens."""

    @abstractmethod
    def summarize(self, text: str, max_chars: int = 500) -> str:
        """Resume o texto (contrato; sem modelo real aqui)."""
