"""Academic workspace containers, separate from repository diagnosis entities."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AcademicProject(Base):
    __tablename__ = "academic_projects"
    __table_args__ = (Index("ix_academic_project_owner", "owner_id", "created_at"),)

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjectSource(Base):
    __tablename__ = "project_sources"
    __table_args__ = (
        CheckConstraint("source_type='github'", name="ck_project_source_type"),
        Index("ix_project_source_project", "project_id"),
        Index("ix_project_source_monitor", "monitor_id"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("academic_projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monitor_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_monitors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="github", server_default="github"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
