"""Entity model — canonical map node (vertex in the knowledge graph).

Entity types are restricted to the 5 approved by the domain model and
PD-0002 scope: person, project, topic, event, source.

'source' as an entity type represents a data-source node *on the map*
(e.g. "OpenAlex" as a concept node). It is distinct from the Source model,
which is an integration record.  No new types may be added without an
approved product decision.

A self-referential constraint and a compound unique index on (type, label)
are enforced at the DB layer. Self-relationships are blocked on the
Relationship model, not here.
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

# Closed set — no new types without approved product decision (PD-0002 scope).
VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {"person", "project", "topic", "event", "source"}
)


class Entity(Base):
    """Nó canônico do mapa de conhecimento do TRAMA."""

    __tablename__ = "entities"
    __table_args__ = (
        # (type, label) should be unique to prevent duplicated canonical nodes.
        UniqueConstraint("entity_type", "label", name="uq_entity_type_label"),
        # Partial index for fast lookup of entities by type.
        Index("ix_entities_entity_type", "entity_type"),
        # Index on origin_item_id for provenance queries.
        Index("ix_entities_origin_item_id", "origin_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Closed enum enforced via CHECK constraint in the migration.
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Human-readable canonical label (e.g. "Rodrigo Oliveira", "Graph Theory").
    label: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional back-reference to the AcademicItem that originated this entity.
    # Nullable: entities can be created manually or via inference.
    origin_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("academic_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Arbitrary structured metadata (e.g. ORCID, GitHub login, DOI).
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
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
    origin_item: Mapped["AcademicItem | None"] = relationship(  # noqa: F821
        "AcademicItem",
        back_populates="entities",
        foreign_keys=[origin_item_id],
    )
    # Outgoing edges (this entity as source).
    outgoing_relationships: Mapped[list["Relationship"]] = relationship(  # noqa: F821
        "Relationship",
        back_populates="source_entity",
        foreign_keys="Relationship.source_id",
        cascade="all, delete-orphan",
    )
    # Incoming edges (this entity as target).
    incoming_relationships: Mapped[list["Relationship"]] = relationship(  # noqa: F821
        "Relationship",
        back_populates="target_entity",
        foreign_keys="Relationship.target_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Entity id={self.id} type={self.entity_type!r} label={self.label!r}>"
