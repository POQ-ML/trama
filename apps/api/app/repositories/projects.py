"""Owner-scoped workspace navigation. No external I/O or implicit commits."""

from uuid import uuid4

from sqlalchemy import and_, func, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert

from app.models import (
    AcademicItem, AcademicProject, DiscoveryRun, Entity, ProjectSource,
    SourceChange, SourceMonitor,
)
from app.repositories import runtime
from app.repositories.discovery import _entity_read
from app.schemas.discovery import RunRead
from app.schemas.projects import ProjectActivityRead, ProjectRead, ProjectSourceRead


def owned(owner):
    if owner is None:
        return AcademicProject.owner_id.is_(None)
    return AcademicProject.owner_id == owner


def project(session, pid, owner):
    row = session.scalar(
        select(AcademicProject).where(AcademicProject.id == pid, owned(owner))
    )
    if row is None:
        raise LookupError()
    return row


def read_project(row, count):
    return ProjectRead(
        id=row.id, name=row.name, description=row.description,
        created_at=row.created_at, source_count=count,
    )


def list_projects(session, owner):
    rows = session.execute(
        select(AcademicProject, func.count(ProjectSource.id))
        .outerjoin(ProjectSource, ProjectSource.project_id == AcademicProject.id)
        .where(owned(owner))
        .group_by(AcademicProject.id)
        .order_by(AcademicProject.created_at, AcademicProject.id)
    )
    return [read_project(p, count) for p, count in rows]


def binding(session, pid, sid, owner, *, lock=False):
    stmt = (
        select(ProjectSource, SourceMonitor)
        .join(AcademicProject, AcademicProject.id == ProjectSource.project_id)
        .join(SourceMonitor, SourceMonitor.id == ProjectSource.monitor_id)
        .where(ProjectSource.project_id == pid, ProjectSource.id == sid, owned(owner))
    )
    if lock:
        stmt = stmt.with_for_update(of=SourceMonitor)
    row = session.execute(stmt.execution_options(populate_existing=True)).first()
    if row is None:
        raise LookupError()
    return row


def belongs(monitor):
    """Include pre006 runs only by URL or a real, non-null origin-item identity."""
    return or_(
        DiscoveryRun.monitor_id == monitor.id,
        and_(
            DiscoveryRun.monitor_id.is_(None),
            or_(
                func.lower(func.rtrim(DiscoveryRun.repo_url, "/")) == monitor.repo_url,
                and_(
                    Entity.origin_item_id.is_not(None),
                    Entity.origin_item_id == monitor.source_item_id,
                ),
            ),
        ),
    )


def sources(session, pid, owner, sid=None):
    project(session, pid, owner)
    stmt = (
        select(ProjectSource, SourceMonitor)
        .join(SourceMonitor, SourceMonitor.id == ProjectSource.monitor_id)
        .where(ProjectSource.project_id == pid)
        .order_by(ProjectSource.created_at, ProjectSource.id)
    )
    if sid is not None:
        stmt = stmt.where(ProjectSource.id == sid)
    rows = session.execute(stmt.execution_options(populate_existing=True)).all()
    if sid is not None and not rows:
        raise LookupError()
    # One latest-row lookup per monitor in a single SQL statement; no ORM N+1.
    latest = (
        select(DiscoveryRun.id.label("rid"))
        .outerjoin(Entity, Entity.id == DiscoveryRun.project_id)
        .where(belongs(SourceMonitor))
        .order_by(DiscoveryRun.created_at.desc(), DiscoveryRun.id.desc())
        .limit(1).correlate(SourceMonitor).lateral()
    )
    monitor_ids = {m.id for _, m in rows}
    run_rows = session.execute(
        select(SourceMonitor.id, DiscoveryRun, Entity, AcademicItem)
        .select_from(SourceMonitor)
        .join(latest, true())
        .join(DiscoveryRun, DiscoveryRun.id == latest.c.rid)
        .outerjoin(Entity, Entity.id == DiscoveryRun.project_id)
        .outerjoin(AcademicItem, AcademicItem.id == Entity.origin_item_id)
        .where(SourceMonitor.id.in_(monitor_ids))
        .execution_options(populate_existing=True)
    ).all() if monitor_ids else []
    runs = {
        mid: RunRead(
            id=run.id, repo_url=run.repo_url,
            project=_entity_read(entity, item) if entity else None,
            status=run.status, created_at=run.created_at, started_at=run.started_at,
            finished_at=run.finished_at, deadline_at=run.deadline_at,
            error_code=run.error_code, warnings=list(run.warnings or []),
        )
        for mid, run, entity, item in run_rows
    }
    return [
        ProjectSourceRead(
            id=link.id, project_id=pid, source_type="github",
            label=monitor.repo_url.split("github.com/", 1)[-1],
            repo_url=monitor.repo_url, latest_run=runs.get(monitor.id),
            created_at=link.created_at,
        )
        for link, monitor in rows
    ]


def add_source(session, pid, owner, data):
    project(session, pid, owner)
    runtime.lock_key(session, "academic-project:" + str(pid))
    session.execute(
        insert(SourceMonitor).values(id=uuid4(), repo_url=data.repo_url)
        .on_conflict_do_nothing(index_elements=["repo_url"])
    )
    monitor = session.scalar(
        select(SourceMonitor).where(SourceMonitor.repo_url == data.repo_url)
        .with_for_update().execution_options(populate_existing=True)
    )
    link = session.scalar(
        select(ProjectSource).where(
            ProjectSource.project_id == pid, ProjectSource.monitor_id == monitor.id
        ).order_by(ProjectSource.created_at, ProjectSource.id).limit(1)
    )
    if link is None:
        link = ProjectSource(project_id=pid, monitor_id=monitor.id)
        session.add(link)
        session.flush()
    return sources(session, pid, owner, link.id)[0]


def transfer_monitor_bindings(session, old_id, new_id):
    # Preserve link IDs, including when both aliases had already been linked.
    session.execute(
        update(ProjectSource).where(ProjectSource.monitor_id == old_id)
        .values(monitor_id=new_id)
    )


def activity(session, owner):
    rows = session.execute(
        select(SourceChange, ProjectSource, AcademicProject, SourceMonitor)
        .select_from(SourceChange)
        .join(ProjectSource, ProjectSource.monitor_id == SourceChange.monitor_id)
        .join(AcademicProject, AcademicProject.id == ProjectSource.project_id)
        .join(SourceMonitor, SourceMonitor.id == ProjectSource.monitor_id)
        .where(owned(owner))
        .order_by(SourceChange.observed_at.desc(), SourceChange.id.desc(), ProjectSource.id)
        .limit(10)
    ).all()
    return [
        ProjectActivityRead(
            id=event.id, project_id=p.id, project_name=p.name, source_id=link.id,
            source_label=monitor.repo_url.split("github.com/", 1)[-1],
            observed_at=event.observed_at, read_at=event.read_at,
        )
        for event, link, p, monitor in rows
    ]
