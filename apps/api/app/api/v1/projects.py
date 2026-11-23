"""Local workspace navigation. workspace_owner is deliberately NOT authentication."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.discovery import operation
from app.core.config import settings
from app.core.database import get_db
from app.models import AcademicProject, DiscoveryRun, Entity
from app.repositories import projects as repo
from app.repositories import runtime
from app.repositories.discovery import expire_run, get_discovery_page, get_run
from app.schemas.discovery import DiscoveryCreate, DiscoveryPage, RunRead
from app.schemas.projects import (
    ProjectActivityRead, ProjectCreate, ProjectDetail, ProjectRead,
    ProjectSourceCreate, ProjectSourceRead,
)

router = APIRouter()


def workspace_owner() -> UUID | None:
    """Shared unowned LOCAL workspace; no client identity/header is consulted."""
    return None


@router.get("/projects", response_model=list[ProjectRead])
def listing(db: Session = Depends(get_db), owner: UUID | None = Depends(workspace_owner)):
    with db.begin():
        return repo.list_projects(db, owner)


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create(
    data: ProjectCreate, db: Session = Depends(get_db),
    owner: UUID | None = Depends(workspace_owner),
):
    with db.begin():
        row = AcademicProject(owner_id=owner, **data.model_dump())
        db.add(row)
        db.flush()
        return repo.read_project(row, 0)


# This fixed path must precede the UUID path below.
@router.get("/projects/activity", response_model=list[ProjectActivityRead])
def activity(db: Session = Depends(get_db), owner: UUID | None = Depends(workspace_owner)):
    with db.begin():
        return repo.activity(db, owner)


@router.get("/projects/{pid}", response_model=ProjectDetail)
def detail(
    pid: UUID, db: Session = Depends(get_db),
    owner: UUID | None = Depends(workspace_owner),
):
    with db.begin():
        row = operation(lambda: repo.project(db, pid, owner))
        source_rows = repo.sources(db, pid, owner)
        return ProjectDetail(
            **repo.read_project(row, len(source_rows)).model_dump(), sources=source_rows
        )


@router.post("/projects/{pid}/sources", response_model=ProjectSourceRead, status_code=201)
def add(
    pid: UUID, data: ProjectSourceCreate, db: Session = Depends(get_db),
    owner: UUID | None = Depends(workspace_owner),
):
    with db.begin():
        return operation(lambda: repo.add_source(db, pid, owner, data))


@router.get("/projects/{pid}/sources/{sid}", response_model=ProjectSourceRead)
def source(
    pid: UUID, sid: UUID, db: Session = Depends(get_db),
    owner: UUID | None = Depends(workspace_owner),
):
    with db.begin():
        return operation(lambda: repo.sources(db, pid, owner, sid)[0])


@router.post(
    "/projects/{pid}/sources/{sid}/discoveries", response_model=RunRead, status_code=202
)
def discover(
    pid: UUID, sid: UUID,
    idempotency_key: str | None = Header(default=None, max_length=128),
    db: Session = Depends(get_db), owner: UUID | None = Depends(workspace_owner),
):
    with db.begin():
        _, monitor = operation(lambda: repo.binding(db, pid, sid, owner, lock=True))
        return operation(lambda: runtime.submit(
            db, DiscoveryCreate(repo_url=monitor.repo_url), monitor=monitor,
            key=idempotency_key, deadline_seconds=settings.DISCOVERY_DEADLINE_SECONDS,
        ))


@router.get(
    "/projects/{pid}/sources/{sid}/discoveries/{rid}", response_model=DiscoveryPage
)
def diagnosis(
    pid: UUID, sid: UUID, rid: UUID,
    limit: int = Query(20, ge=1, le=50), cursor: UUID | None = None,
    db: Session = Depends(get_db), owner: UUID | None = Depends(workspace_owner),
):
    with db.begin():
        _, monitor = operation(lambda: repo.binding(db, pid, sid, owner))

        def check():
            match = db.scalar(
                select(DiscoveryRun.id)
                .outerjoin(Entity, Entity.id == DiscoveryRun.project_id)
                .where(DiscoveryRun.id == rid, repo.belongs(monitor))
            )
            if match is None:
                raise LookupError()
            page = get_discovery_page(db, rid, limit=limit, after=cursor)
            if (
                page.run.status in ("queued", "running")
                and page.run.deadline_at <= runtime.now()
            ):
                expire_run(db, rid)
                page.run = get_run(db, rid)
            return page

        return operation(check)
