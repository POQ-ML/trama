"""Discovery persistence contracts. No HTTP handlers are implemented here."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID
import re

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ErrorCode(str, Enum):
    SOURCE_UNAVAILABLE = "source_unavailable"
    TIMEOUT = "timeout"
    INVALID_EVIDENCE = "invalid_evidence"
    INTERNAL_ERROR = "internal_error"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    ANALYSIS_WARNING = "analysis_warning"


class DiscoveryCreate(ContractModel):
    repo_url: str = Field(max_length=2048)

    @field_validator("repo_url")
    @classmethod
    def canonical_repo(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.netloc != "github.com"
            or url.query
            or url.fragment
            or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", url.path)
            or any(part in {".", ".."} for part in url.path.split("/")[1:])
        ):
            raise ValueError("Use a canonical public GitHub repository URL")
        return value.rstrip("/").lower()


class RunUpdate(ContractModel):
    status: RunStatus
    project_id: UUID | None = None
    error_code: ErrorCode | None = None

    @model_validator(mode="after")
    def error_state(self):
        if (
            self.status in {RunStatus.PARTIAL, RunStatus.FAILED}
            and self.error_code is None
        ):
            raise ValueError("partial/failed require a safe error_code")
        if (
            self.status not in {RunStatus.PARTIAL, RunStatus.FAILED}
            and self.error_code is not None
        ):
            raise ValueError("error_code only belongs to partial/failed")
        return self


class _ItemRead(ContractModel):
    id: UUID
    origin_item_id: UUID
    label: str
    external_id: str
    original_url: str | None


class ProjectRead(_ItemRead):
    entity_type: Literal["project"] = "project"


class ArticleRead(_ItemRead):
    entity_type: Literal["article"] = "article"


class TopicRead(ContractModel):
    id: str
    namespace: Literal["openalex"] = "openalex"
    label: str
    score: float | None = None


class EvidenceRead(ContractModel):
    id: UUID
    origin_item_id: UUID
    side: Literal["repo", "article"]
    reference_url: str
    locator: str
    excerpt: str
    capture_version: str
    captured_at: AwareDatetime


class SuggestionRead(ContractModel):
    id: UUID
    relationship_type: Literal["project_article"] = "project_article"
    status: Literal["pending", "confirmed", "rejected"]
    project_id: UUID
    article: ArticleRead
    justification: str
    score: float | None
    topics: list[TopicRead]
    evidences: list[EvidenceRead]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class RunRead(ContractModel):
    warnings: list[str] = Field(default_factory=list)
    id: UUID
    repo_url: str
    project: ProjectRead | None
    status: RunStatus
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    deadline_at: AwareDatetime
    error_code: ErrorCode | None

    @model_validator(mode="after")
    def coherent_state(self):
        terminal = self.status in {
            RunStatus.COMPLETED,
            RunStatus.PARTIAL,
            RunStatus.FAILED,
        }
        error = self.status in {RunStatus.PARTIAL, RunStatus.FAILED}
        if terminal != (self.finished_at is not None) or error != (
            self.error_code is not None
        ):
            raise ValueError("Incoherent run status/timestamps/error")
        if self.deadline_at <= self.created_at:
            raise ValueError("deadline must follow creation")
        if self.status == RunStatus.QUEUED and self.started_at is not None:
            raise ValueError("queued runs have not started")
        if (
            self.status in {RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.PARTIAL}
            and self.started_at is None
        ):
            raise ValueError("running and successful runs require started_at")
        if (
            self.status in {RunStatus.COMPLETED, RunStatus.PARTIAL}
            and self.project is None
        ):
            raise ValueError("successful/partial runs require project")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("start must follow creation")
        if self.finished_at is not None and self.finished_at < (
            self.started_at or self.created_at
        ):
            raise ValueError("finish must follow start/creation")
        return self


class DiscoveryQuery(ContractModel):
    limit: int = Field(default=20, ge=1, le=50, strict=True)
    cursor: UUID | None = None


class DiscoveryPage(ContractModel):
    run: RunRead
    suggestions: list[SuggestionRead]
    total_suggestions: int = Field(ge=0)
    limit: int = Field(ge=1, le=50, strict=True)
    next_cursor: UUID | None


class FeedbackUpdate(ContractModel):
    status: Literal["confirmed", "rejected"]


class FeedbackRead(ContractModel):
    id: UUID
    status: Literal["confirmed", "rejected"]
    updated_at: AwareDatetime


class EvidenceInput(ContractModel):
    """INTERNAL ONLY: kwargs produced by trusted AI evidence builder, not a request body."""

    origin_item_id: UUID
    reference_url: str = Field(min_length=1, max_length=2048)
    locator: str = Field(min_length=1, max_length=255)
    excerpt: str = Field(min_length=1, max_length=2000)
    capture_version: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    captured_at: AwareDatetime
    metadata_: dict[str, JsonValue]


class SuggestionInput(ContractModel):
    """INTERNAL ONLY. Evidence is revalidated against persisted source snapshots."""

    article_item_id: UUID
    justification: str = Field(min_length=1, max_length=4000)
    score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    evidences: tuple[EvidenceInput, EvidenceInput]
