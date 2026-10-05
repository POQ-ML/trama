"""Relationship engine — interface, sem chamada real a modelos."""
from __future__ import annotations

from abc import ABC, abstractmethod


class RelationshipEngine(ABC):
    """Contrato de inferência de relações entre entidades."""

    @abstractmethod
    def infer_relationships(self, entities: list[dict]) -> list[dict]:
        """Retorna relações inferidas como dicts {source_id, target_id, type}."""
