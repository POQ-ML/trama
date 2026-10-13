"""Evidence model — material that supports a Relationship claim.

Each Relationship may have multiple Evidence records. A relationship
without at least one confirmed evidence record should not be displayed
(enforced at the service layer per PD-0002 rule 4).

LLM-generated explanations are NOT evidence. Evidence must trace back
to an AcademicItem (origin_item) with a concrete reference (URL or locator).

Provenance fields are immutable after creation: if the source content
changes, a new Evidence record should be created with updated capture info.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as sa_relationship

from app.models.base import Base


class Evidence(Base):
    """Material rastreável que sustenta uma relação no grafo."""

    __tablename__ = "evidences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("relationships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The AcademicItem that contains the evidence.
    origin_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("academic_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Direct URL to the evidence within the original source.
    reference_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Locator within the item (e.g. section, paragraph, page number, byte range).
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Short excerpt from the original content (for display; not the full text).
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Version or snapshot date of the content at capture time.
    # Preserves provenance if the source is mutable (e.g. a wiki page).
    capture_version: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # When this evidence record was captured.
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Additional structured metadata (e.g. confidence score, extraction method).
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=None
    )

    # ORM back-references
    relationship: Mapped["Relationship"] = sa_relationship(  # noqa: F821
        "Relationship", back_populates="evidences"
    )
    origin_item: Mapped["AcademicItem"] = sa_relationship(  # noqa: F821
        "AcademicItem", back_populates="evidences"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Evidence id={self.id} "
            f"relationship_id={self.relationship_id} "
            f"origin_item_id={self.origin_item_id}>"
        )
