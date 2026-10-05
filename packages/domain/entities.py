"""Entidades fundamentais do TRAMA (Initial Build — apenas abstrações)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class User:
    id: UUID = field(default_factory=uuid4)
    email: str = ""


@dataclass
class Source:
    id: UUID = field(default_factory=uuid4)
    kind: str = "unknown"  # moodle | github | ufc | openalex
    name: str = ""


@dataclass
class AcademicEvent:
    id: UUID = field(default_factory=uuid4)
    title: str = ""
    occurred_at: datetime | None = None


@dataclass
class Project:
    id: UUID = field(default_factory=uuid4)
    name: str = ""


@dataclass
class Course:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    code: str = ""


@dataclass
class Relationship:
    id: UUID = field(default_factory=uuid4)
    source_id: UUID | None = None
    target_id: UUID | None = None
    kind: str = "related"


@dataclass
class Evidence:
    id: UUID = field(default_factory=uuid4)
    url: str = ""
    excerpt: str = ""
