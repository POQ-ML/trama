"""Eventos de domínio — abstrações iniciais, sem dispatch real."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4


def _default_occurred_at() -> str:
    return ""


@dataclass(frozen=True)
class DomainEvent:
    """Evento base de domínio. Subclassifique para casos concretos."""

    event_id: str = field(default_factory=lambda: uuid4().hex)
    occurred_at: str = field(default_factory=_default_occurred_at)
    entity_id: str = ""


@dataclass(frozen=True)
class EntityCreated(DomainEvent):
    """Entidade criada."""

    entity_type: str = ""


@dataclass(frozen=True)
class EntityUpdated(DomainEvent):
    """Entidade atualizada."""

    entity_type: str = ""
