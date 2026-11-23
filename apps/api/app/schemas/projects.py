"""Local workspace navigation contracts; identity is supplied by the server."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.discovery import ContractModel, DiscoveryCreate, RunRead


class ProjectCreate(ContractModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank")
        return value.strip()


class ProjectRead(ContractModel):
    id: UUID
    name: str
    description: str | None
    source_count: int
    created_at: AwareDatetime


class ProjectSourceCreate(DiscoveryCreate):
    source_type: Literal["github"]


class ProjectSourceRead(ContractModel):
    id: UUID
    project_id: UUID
    source_type: Literal["github"]
    label: str
    repo_url: str
    latest_run: RunRead | None
    created_at: AwareDatetime


class ProjectDetail(ProjectRead):
    sources: list[ProjectSourceRead]


class ProjectActivityRead(ContractModel):
    id: UUID
    project_id: UUID
    project_name: str
    source_id: UUID
    source_label: str
    observed_at: AwareDatetime
    read_at: AwareDatetime | None
    kind: Literal["source_changed"] = "source_changed"
