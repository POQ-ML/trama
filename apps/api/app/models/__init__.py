"""Model registry.

Import order matters for Alembic autogenerate: Base must be imported first,
then every model that contributes tables so they register on Base.metadata.
"""

from app.models.base import Base
from app.models.user import User
from app.models.source import Source
from app.models.academic_item import AcademicItem
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.models.evidence import Evidence

__all__ = [
    "Base",
    "User",
    "Source",
    "AcademicItem",
    "Entity",
    "Relationship",
    "Evidence",
]
