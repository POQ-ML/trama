"""Bounded synchronous DB handlers; network/generation is performed by worker."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

from app.core.config import settings
from app.core.database import get_db
from app.repositories import runtime
from app.repositories.discovery import (
    get_discovery_page,
    set_feedback,
    expire_run,
    get_run,
)
from app.repositories.runtime import now
from app.schemas.discovery import (
    DiscoveryCreate,
    DiscoveryPage,
    RunRead,
    FeedbackUpdate,
    FeedbackRead,
)
from app.schemas.monitoring import MonitorUpdate, MonitorRead, ChangePage, ChangeRead

router = APIRouter()


def operation(call):
    try:
        return call()
    except (LookupError, NoResultFound):
        raise HTTPException(404, detail={"code": "not_found"}) from None
    except runtime.Conflict:
        raise HTTPException(409, detail={"code": "conflict"}) from None
    except ValueError:
        raise HTTPException(422, detail={"code": "invalid_request"}) from None


@router.post("/discoveries", response_model=RunRead, status_code=202)
def create(
    data: DiscoveryCreate,
    idempotency_key: str | None = Header(default=None, max_length=128),
    db: Session = Depends(get_db),
):
    with db.begin():
        return operation(
            lambda: runtime.submit(
                db,
                data,
                key=idempotency_key,
                deadline_seconds=settings.DISCOVERY_DEADLINE_SECONDS,
            )
        )


@router.get("/discoveries/{run_id}", response_model=DiscoveryPage)
def read(
    run_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: UUID | None = None,
    db: Session = Depends(get_db),
):
    with db.begin():
        page = operation(
            lambda: get_discovery_page(db, run_id, limit=limit, after=cursor)
        )
        if page.run.status in ("queued", "running") and page.run.deadline_at <= now():
            expire_run(db, run_id)
            page.run = get_run(db, run_id)
        return page


@router.patch("/relationships/{relationship_id}/feedback", response_model=FeedbackRead)
def feedback(
    relationship_id: UUID, data: FeedbackUpdate, db: Session = Depends(get_db)
):
    with db.begin():
        row = operation(lambda: set_feedback(db, relationship_id, data))
        return FeedbackRead(id=row.id, status=row.status, updated_at=row.updated_at)


@router.get("/discoveries/{run_id}/monitor", response_model=MonitorRead)
def monitor(run_id: UUID, db: Session = Depends(get_db)):
    with db.begin():
        return operation(
            lambda: runtime.monitor_read(runtime.monitor_for_run(db, run_id))
        )


@router.put("/discoveries/{run_id}/monitor", response_model=MonitorRead)
def configure_monitor(run_id: UUID, data: MonitorUpdate, db: Session = Depends(get_db)):
    with db.begin():
        return operation(lambda: runtime.configure(db, run_id, data))


@router.post(
    "/discoveries/{run_id}/monitor/check", response_model=MonitorRead, status_code=202
)
def check_monitor(run_id: UUID, db: Session = Depends(get_db)):
    with db.begin():
        return operation(lambda: runtime.request_check(db, run_id))


@router.post("/discoveries/{run_id}/reanalyze", response_model=RunRead, status_code=202)
def reanalyze(run_id: UUID, db: Session = Depends(get_db)):
    with db.begin():
        return operation(
            lambda: runtime.reanalyze(db, run_id, settings.DISCOVERY_DEADLINE_SECONDS)
        )


@router.get("/discoveries/{run_id}/changes", response_model=ChangePage)
def source_changes(
    run_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: UUID | None = None,
    db: Session = Depends(get_db),
):
    with db.begin():
        return operation(
            lambda: runtime.changes(db, run_id, limit=limit, cursor=cursor)
        )


@router.post("/source-changes/{event_id}/read", response_model=ChangeRead)
def acknowledge(event_id: UUID, db: Session = Depends(get_db)):
    with db.begin():
        return operation(lambda: runtime.acknowledge(db, event_id))
