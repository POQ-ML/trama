"""Public polling/monitor contracts. Monitoring describes context, not all commits."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.schemas.discovery import ContractModel


class MonitorUpdate(ContractModel):
    enabled: bool
    interval_seconds: int = Field(default=300, ge=60, le=86400, strict=True)
    reanalyze_on_change: bool = False


class MonitorRead(ContractModel):
    id: UUID
    repo_url: str
    source_item_id: UUID | None
    enabled: bool
    interval_seconds: int
    reanalyze_on_change: bool
    latest_run_id: UUID
    last_checked_at: AwareDatetime | None
    last_changed_at: AwareDatetime | None
    next_check_at: AwareDatetime | None
    error_code: str | None
    stale: bool


class ChangeRead(ContractModel):
    id: UUID
    monitor_id: UUID
    repo_url: str
    kind: Literal["source_changed"] = "source_changed"
    observed_at: AwareDatetime
    previous_hash: str
    current_hash: str
    read_at: AwareDatetime | None
    latest_run_id: UUID | None


class ChangePage(ContractModel):
    items: list[ChangeRead]
    limit: int = Field(ge=1, le=50)
    next_cursor: UUID | None


class ApiErrorDetail(ContractModel):
    code: str
    message: str
    retryable: bool


class ApiError(ContractModel):
    error: ApiErrorDetail
