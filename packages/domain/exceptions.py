"""Exceções de domínio — abstrações iniciais."""
from __future__ import annotations


class DomainError(Exception):
    """Erro base de domínio."""


class EntityNotFoundError(DomainError):
    """Entidade não encontrada."""


class ValidationError(DomainError):
    """Dados inválidos para uma entidade."""


class InvalidRelationError(DomainError):
    """Relação entre entidades inválida."""
