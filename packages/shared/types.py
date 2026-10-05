"""Tipos compartilhados — aliases + paginação (stdlib)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

EntityId = str
ISODateTime = str

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    """Página genérica de resultados."""

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 20
