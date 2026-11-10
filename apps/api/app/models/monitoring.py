"""Durable conditional polling, occurrence events and HTTP idempotency keys."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SourceMonitor(Base):
    __tablename__ = "source_monitors"
    __table_args__ = (
        CheckConstraint(
            "interval_seconds BETWEEN 60 AND 86400", name="ck_monitor_interval"
        ),
        CheckConstraint(
            "failure_count >= 0 AND generation >= 0", name="ck_monitor_counts"
        ),
        Index(
            "ix_monitor_due", "next_check_at", postgresql_where=text("enabled = true")
        ),
    )
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    repo_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_item_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("academic_items.id", ondelete="RESTRICT"),
        unique=True,
    )
    latest_run_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_runs.id", ondelete="RESTRICT", use_alter=True),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default="300"
    )
    reanalyze_on_change: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    current_hash: Mapped[str | None] = mapped_column(String(64))
    analyzed_hash: Mapped[str | None] = mapped_column(String(64))
    etag_repo: Mapped[str | None] = mapped_column(String(512))
    etag_readme: Mapped[str | None] = mapped_column(String(512))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(32))
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lease_token: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceChange(Base):
    __tablename__ = "source_changes"
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    monitor_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_monitors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_run_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discovery_runs.id", ondelete="RESTRICT")
    )
    __table_args__ = (
        UniqueConstraint(
            "monitor_id", "generation", name="uq_source_change_occurrence"
        ),
    )


class DiscoveryRequest(Base):
    __tablename__ = "discovery_requests"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discovery_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
