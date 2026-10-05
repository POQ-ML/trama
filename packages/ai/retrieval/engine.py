"""Retrieval engine — interface, sem chamada real a modelos."""
from __future__ import annotations

from abc import ABC, abstractmethod


class RetrievalEngine(ABC):
    """Contrato de recuperação de trechos relevantes."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retorna até `top_k` itens relevantes para `query`."""
