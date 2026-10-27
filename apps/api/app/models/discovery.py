"""Small durable discovery run and its exact evidence-backed result membership."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Float,
    String,
    Text,
    Index,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    __table_args__ = (
        Index(
            "ix_discovery_queue", "created_at", postgresql_where=text("status='queued'")
        ),
        Index(
            "uq_discovery_active_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text(
                "monitor_id IS NOT NULL AND status IN ('queued','running')"
            ),
            sqlite_where=text(
                "monitor_id IS NOT NULL AND status IN ('queued','running')"
            ),
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','partial','failed')",
            name="ck_discovery_status",
        ),
        CheckConstraint("deadline_at > created_at", name="ck_discovery_deadline"),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ('source_unavailable','timeout','invalid_evidence','internal_error','insufficient_context','analysis_warning')",
            name="ck_discovery_error_code",
        ),
        CheckConstraint(
            "(status IN ('partial','failed')) = (error_code IS NOT NULL)",
            name="ck_discovery_error_state",
        ),
        CheckConstraint(
            "(status IN ('completed','partial','failed')) = (finished_at IS NOT NULL)",
            name="ck_discovery_finished",
        ),
    )
    monitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_monitors.id", ondelete="RESTRICT", use_alter=True),
    )
    warnings: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    context_hash: Mapped[str | None] = mapped_column(String(64))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(32))


class DiscoverySuggestion(Base):
    __tablename__ = "discovery_suggestions"
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("relationships.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    repo_evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidences.id", ondelete="RESTRICT"),
        nullable=False,
    )
    article_evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidences.id", ondelete="RESTRICT"),
        nullable=False,
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    topics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # No extra indexes: run_id + relationship_id PK serves keyset page reads.
