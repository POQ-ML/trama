"""Source model — integration instance (GitHub, Moodle, OpenAlex, …).

A Source represents one configured connection to an external data provider.
It is intentionally distinct from the Entity type 'source' (a map node);
the naming follows the domain model note in the vault.

User association is prepared (nullable FK) but the full auth system is
a separate concern — see open item in the delivery summary.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Closed set of providers for MVP. Extend only via product decision.
VALID_PROVIDERS: frozenset[str] = frozenset({"github", "moodle", "openalex"})


class Source(Base):
    """Registro de uma origem de dados (instância de integração)."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("provider", "canonical_id", name="uq_source_provider_canonical"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Closed enum enforced via CHECK constraint in the migration.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Canonical URL or unique identifier within the provider (e.g. repo slug,
    # course id, openalex institution id). Immutable after creation.
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)

    # Optional human-readable URL for display.
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Arbitrary provider-specific config (rate limits, field mappings, etc.).
    # Never store credentials here — use environment secrets.
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
    )

    # Nullable FK to users — prepared for future auth association.
    # Not enforced as NOT NULL until the auth system is implemented.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    academic_items: Mapped[list["AcademicItem"]] = relationship(  # noqa: F821
        "AcademicItem", back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source id={self.id} provider={self.provider!r} name={self.name!r}>"
