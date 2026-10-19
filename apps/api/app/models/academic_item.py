"""AcademicItem model — normalised record imported from a Source.

Immutable after initial write: corrections produce a new version (bumped
content_hash). Raw payloads are NOT stored here; only the normalised fields
needed for entity/relation detection are persisted.

Item types (article, course, opportunity, activity) describe the kind of
imported object and are deliberately separate from Entity types (person,
project, topic, event, source), which describe map nodes.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.types import TsVector

# Closed set of item types for MVP.  Extend only via product decision.
# 'repository' added in migration 004 to support GitHub ingestion.
VALID_ITEM_TYPES: frozenset[str] = frozenset(
    {"article", "course", "opportunity", "activity", "repository"}
)


class AcademicItem(Base):
    """Registro normalizado de um item importado de uma fonte externa."""

    __tablename__ = "academic_items"
    __table_args__ = (
        # Each (source, external_id) pair is unique — same external object
        # from the same provider must not be duplicated.
        UniqueConstraint("source_id", "external_id", name="uq_academic_item_source_external"),
        # Full-text search index on normalised content (tsvector fallback per ADR-0004).
        Index(
            "ix_academic_items_fts",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Identifier assigned by the external provider (e.g. DOI, Moodle course id).
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)

    # Closed enum enforced via CHECK constraint in the migration.
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Normalised description / abstract / content. Not the raw payload.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Canonical URL at the original provider.
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Publication / creation date as reported by the provider (may be None).
    original_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # When this record was captured from the provider.
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # SHA-256 hash of (source_id + external_id + normalised content).
    # Changing this implies a new version — immutability is enforced at the
    # service layer, not here, to allow the migration path.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Structured provenance and provider-specific fields that don't fit the
    # normalised columns above. No credentials stored here.
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
    )

    # tsvector column for full-text search fallback (ADR-0004).
    # Degrades gracefully to TEXT on SQLite for unit tests (see models/types.py).
    # Populated by the service layer or a DB trigger.
    search_vector: Mapped[object | None] = mapped_column(TsVector, nullable=True)

    # Relationships
    source: Mapped["Source"] = relationship(  # noqa: F821
        "Source", back_populates="academic_items"
    )
    entities: Mapped[list["Entity"]] = relationship(  # noqa: F821
        "Entity",
        back_populates="origin_item",
        foreign_keys="Entity.origin_item_id",
    )
    evidences: Mapped[list["Evidence"]] = relationship(  # noqa: F821
        "Evidence", back_populates="origin_item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AcademicItem id={self.id} type={self.item_type!r} "
            f"title={self.title[:40]!r}>"
        )
