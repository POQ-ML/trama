"""Base agent — interface, sem chamada real a modelos."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Contrato mínimo de um agente."""

    name: str = "base"

    @abstractmethod
    async def run(self, task: str, context: dict | None = None) -> str:
        """Executa a tarefa e retorna texto resultante."""
