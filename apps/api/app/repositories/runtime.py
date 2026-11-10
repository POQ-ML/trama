"""Short PostgreSQL transactions for durable scheduling, ingestion and notifications.

No external I/O here; callers own transaction boundaries. Locks fence stale
workers and serialize one observation at a time per source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from uuid import UUID, uuid4

from sqlalchemy import select, or_, func
from sqlalchemy.dialects.postgresql import insert

from app.models import (
    AcademicItem,
    Source,
    DiscoveryRun,
    SourceMonitor,
    SourceChange,
    DiscoveryRequest,
)
from app.repositories.discovery import create_run, get_run, expire_run
from app.schemas.discovery import DiscoveryCreate
from app.schemas.monitoring import MonitorRead, MonitorUpdate, ChangeRead, ChangePage
from app.services.ingestion.models import NormalisedItem
from app.services.source_collectors import CollectionResult, CollectionState


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc)


def lock_key(session, value):
    key = int.from_bytes(
        hashlib.sha256(value.encode()).digest()[:8], "big", signed=True
    )
    session.execute(select(func.pg_advisory_xact_lock(key)))


def monitor_read(m):
    return MonitorRead(
        id=m.id,
        repo_url=m.repo_url,
        source_item_id=m.source_item_id,
        enabled=m.enabled,
        interval_seconds=m.interval_seconds,
        reanalyze_on_change=m.reanalyze_on_change,
        latest_run_id=m.latest_run_id,
        last_checked_at=m.last_checked_at,
        last_changed_at=m.last_changed_at,
        next_check_at=m.next_check_at if m.enabled else None,
        error_code=m.error_code,
        stale=m.current_hash is not None and m.current_hash != m.analyzed_hash,
    )


def monitor_for_run(session, run_id, *, lock=False):
    run = session.get(DiscoveryRun, run_id, populate_existing=True)
    if run is None:
        raise LookupError()
    if run.monitor_id is None:
        raise LookupError()
    stmt = (
        select(SourceMonitor)
        .where(SourceMonitor.id == run.monitor_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    result = session.scalar(stmt)
    if result is None:
        raise LookupError()
    return result


def submit(
    session, data: DiscoveryCreate, *, key=None, deadline_seconds=120, monitor=None
):
    if key is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise ValueError("Invalid idempotency key")
        lock_key(session, "request:" + key)
        previous = session.get(DiscoveryRequest, key)
        if previous:
            if previous.repo_url != data.repo_url:
                raise Conflict()
            return get_run(session, previous.run_id)
    if monitor is None:
        session.execute(
            insert(SourceMonitor)
            .values(id=uuid4(), repo_url=data.repo_url)
            .on_conflict_do_nothing(index_elements=["repo_url"])
        )
        monitor = session.scalars(
            select(SourceMonitor)
            .where(SourceMonitor.repo_url == data.repo_url)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
    # expire_run holds a row lock only inside this short transaction.
    active = session.scalar(
        select(DiscoveryRun).where(
            DiscoveryRun.monitor_id == monitor.id,
            DiscoveryRun.status.in_(["queued", "running"]),
        )
    )
    if active and active.deadline_at <= now():
        expire_run(session, active.id)
        active = None
    if active is None:
        active = create_run(
            session, data, deadline_at=now() + timedelta(seconds=deadline_seconds)
        )
        active.monitor_id = monitor.id
        monitor.latest_run_id = active.id
    if key is not None:
        session.add(DiscoveryRequest(key=key, repo_url=data.repo_url, run_id=active.id))
    session.flush()
    return get_run(session, active.id)


def configure(session, run_id, data: MonitorUpdate):
    m = monitor_for_run(session, run_id, lock=True)
    m.enabled = data.enabled
    m.interval_seconds = data.interval_seconds
    m.reanalyze_on_change = data.reanalyze_on_change
    m.next_check_at = now() if m.enabled else None
    session.flush()
    return monitor_read(m)


def request_check(session, run_id):
    m = monitor_for_run(session, run_id, lock=True)
    if not m.enabled:
        raise Conflict("Enable monitoring before scheduling a check")
    m.next_check_at = now()
    session.flush()
    return monitor_read(m)


def reanalyze(session, run_id, deadline_seconds=120):
    m = monitor_for_run(session, run_id, lock=True)
    return submit(
        session,
        DiscoveryCreate(repo_url=m.repo_url),
        deadline_seconds=deadline_seconds,
        monitor=m,
    )


def persist_items(session, items: list[NormalisedItem]):
    """One bounded batch; preserve first capture and reject stale observations."""
    if not items or len(items) > 50:
        raise ValueError("Bounded source batch required")
    providers = {i.source_key for i in items}
    if len(providers) != 1 or not providers <= {"github", "openalex"}:
        raise ValueError("Invalid source batch")
    provider = next(iter(providers))
    for item in items:
        expected = "repository" if provider == "github" else "article"
        if item.item_type != expected or not re.fullmatch(
            r"[0-9a-f]{64}", item.content_hash
        ):
            raise ValueError("Invalid normalized source")
        if provider == "openalex" and not re.fullmatch(r"W[0-9]+", item.external_id):
            raise ValueError("Invalid OpenAlex id")
        if provider == "github" and not item.external_id.isdigit():
            raise ValueError("Invalid GitHub id")
    # Provider row lock serializes competing source/external-id inserts without
    # holding any connection during network calls.
    stmt = insert(Source).values(
        id=uuid4(),
        provider=provider,
        canonical_id=provider,
        name=provider.title(),
        url={"github": "https://github.com", "openalex": "https://openalex.org"}[
            provider
        ],
    )
    source_id = session.scalar(
        stmt.on_conflict_do_update(
            index_elements=["provider", "canonical_id"], set_={"canonical_id": provider}
        ).returning(Source.id)
    )
    previous = {
        i.external_id: i
        for i in session.scalars(
            select(AcademicItem)
            .where(
                AcademicItem.source_id == source_id,
                AcademicItem.external_id.in_([i.external_id for i in items]),
            )
            .order_by(AcademicItem.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    rows = []
    ids = {}
    for incoming in sorted(
        {i.external_id: i for i in items}.values(), key=lambda i: i.external_id
    ):
        old = previous.get(incoming.external_id)
        observed = incoming.captured_at or now()
        if observed.tzinfo is None:
            raise ValueError("Observation timezone required")
        seen = (old.metadata_ or {}).get("last_seen_at") if old else None
        if old is not None and seen and datetime.fromisoformat(seen) > observed:
            ids[incoming.external_id] = old.id
            continue
        same = old is not None and old.content_hash == incoming.content_hash
        metadata = (
            dict(old.metadata_ or {})
            if same and old is not None
            else dict(incoming.metadata or {})
        )
        captured = old.captured_at if old else observed
        metadata["captured_at"] = (
            (old.metadata_ or {}).get("captured_at", captured.isoformat())
            if old
            else captured.isoformat()
        )
        metadata["last_seen_at"] = observed.isoformat()
        identity = old.id if old else uuid4()
        ids[incoming.external_id] = identity
        rows.append(
            dict(
                id=identity,
                source_id=source_id,
                external_id=incoming.external_id,
                item_type=incoming.item_type,
                title=old.title if same and old is not None else incoming.title,
                description=old.description
                if same and old is not None
                else incoming.description,
                original_url=old.original_url
                if same and old is not None
                else incoming.original_url,
                original_date=old.original_date
                if same and old is not None
                else incoming.original_date,
                captured_at=captured,
                content_hash=incoming.content_hash,
                metadata_=metadata,
            )
        )
    if rows:
        stmt = insert(AcademicItem).values(rows)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["source_id", "external_id"],
                set_={
                    key: getattr(
                        stmt.excluded, "metadata" if key == "metadata" else key
                    )
                    for key in [
                        "title",
                        "description",
                        "original_url",
                        "original_date",
                        "content_hash",
                        "metadata",
                    ]
                },
            )
        )
    session.flush()
    return ids


@dataclass(frozen=True)
class Lease:
    monitor_id: UUID
    token: UUID
    repo_url: str
    state: CollectionState
    run_id: UUID | None = None
    deadline_at: datetime | None = None


def _state(session, m):
    if m.source_item_id is None:
        return CollectionState(etag_repo=m.etag_repo, etag_readme=m.etag_readme)
    item = session.get(AcademicItem, m.source_item_id, populate_existing=True)
    if item is None:
        raise LookupError()
    cached = NormalisedItem(
        item.external_id,
        item.item_type,
        item.title,
        "github",
        item.content_hash,
        item.description,
        item.original_url,
        item.original_date,
        dict(item.metadata_ or {}),
        item.captured_at,
    )
    return CollectionState(cached, m.etag_repo, m.etag_readme)


def claim_run(session):
    run = session.scalar(
        select(DiscoveryRun)
        .join(SourceMonitor, DiscoveryRun.monitor_id == SourceMonitor.id)
        .where(
            DiscoveryRun.status == "queued",
            DiscoveryRun.deadline_at > now(),
            or_(
                SourceMonitor.lease_expires_at.is_(None),
                SourceMonitor.lease_expires_at <= now(),
            ),
        )
        .order_by(DiscoveryRun.created_at, DiscoveryRun.id)
        .with_for_update(of=(DiscoveryRun, SourceMonitor), skip_locked=True)
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if run is None:
        return None
    m = session.scalar(
        select(SourceMonitor)
        .where(SourceMonitor.id == run.monitor_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if m is None or (m.lease_expires_at and m.lease_expires_at > now()):
        return None
    token = uuid4()
    run.status = "running"
    run.started_at = now()
    run.claim_token = token
    run.lease_expires_at = run.deadline_at
    m.lease_token = token
    m.lease_expires_at = run.deadline_at
    session.flush()
    return Lease(m.id, token, m.repo_url, _state(session, m), run.id, run.deadline_at)


def claim_monitor(session, *, lease_seconds=30):
    instant = now()
    m = session.scalar(
        select(SourceMonitor)
        .where(
            SourceMonitor.enabled.is_(True),
            SourceMonitor.next_check_at <= instant,
            or_(
                SourceMonitor.lease_expires_at.is_(None),
                SourceMonitor.lease_expires_at <= instant,
            ),
        )
        .order_by(SourceMonitor.next_check_at)
        .with_for_update(skip_locked=True)
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if m is None:
        return None
    token = uuid4()
    m.lease_token = token
    m.lease_expires_at = instant + timedelta(seconds=lease_seconds)
    session.flush()
    return Lease(m.id, token, m.repo_url, _state(session, m))


def fenced_monitor(session, lease):
    m = session.scalar(
        select(SourceMonitor)
        .where(SourceMonitor.id == lease.monitor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        m is None
        or m.lease_token != lease.token
        or m.lease_expires_at is None
        or m.lease_expires_at <= now()
    ):
        raise Conflict("Expired monitor lease")
    return m


def record_observation(
    session, lease: Lease, result: CollectionResult, *, deadline_seconds=120
):
    # Identity lock precedes monitor locks, including canonical rename collisions.
    lock_key(session, "github:" + result.item.external_id)
    m = fenced_monitor(session, lease)
    old_item = session.scalar(
        select(AcademicItem)
        .join(Source)
        .where(
            Source.provider == "github",
            AcademicItem.external_id == result.item.external_id,
        )
    )
    other = (
        session.scalar(
            select(SourceMonitor).where(
                SourceMonitor.source_item_id == old_item.id, SourceMonitor.id != m.id
            )
        )
        if old_item
        else None
    )
    if other is not None:
        raise Conflict("Source already has a canonical monitor")
    if m.last_checked_at and result.observed_at < m.last_checked_at:
        raise Conflict("Stale observation")
    seen = (old_item.metadata_ or {}).get("last_seen_at") if old_item else None
    if seen and datetime.fromisoformat(seen) > result.observed_at:
        raise Conflict("Older than persisted source")
    canonical = DiscoveryCreate(
        repo_url=f"https://github.com/{result.item.metadata['full_name']}"
    ).repo_url
    alias = session.scalar(
        select(SourceMonitor)
        .where(SourceMonitor.repo_url == canonical, SourceMonitor.id != m.id)
        .with_for_update()
    )
    if alias is not None:
        if alias.source_item_id is not None:
            raise Conflict("Canonical source identity collision")
        # A renamed URL may have a placeholder queue row. Keep its run history,
        # fence its worker, and coalesce it into the existing numeric source.
        for run in session.scalars(
            select(DiscoveryRun)
            .where(DiscoveryRun.monitor_id == alias.id)
            .with_for_update()
            .order_by(DiscoveryRun.id)
        ):
            if run.status in ("queued", "running"):
                run.status = "failed"
                run.error_code = "source_unavailable"
                run.finished_at = now()
                run.claim_token = None
            run.monitor_id = m.id
        session.flush()
        session.delete(alias)
        session.flush()
    item_id = persist_items(session, [result.item])[result.item.external_id]
    m.source_item_id = item_id
    m.repo_url = canonical
    previous = m.current_hash
    m.current_hash = result.item.content_hash
    m.last_checked_at = result.observed_at
    m.etag_repo = result.etag_repo
    m.etag_readme = result.etag_readme
    m.error_code = None
    m.failure_count = 0
    m.lease_token = None
    m.lease_expires_at = None
    m.next_check_at = (
        now() + timedelta(seconds=m.interval_seconds) if m.enabled else None
    )
    changed = previous is not None and previous != m.current_hash
    if changed:
        m.generation += 1
        m.last_changed_at = result.observed_at
        session.add(
            SourceChange(
                id=uuid4(),
                monitor_id=m.id,
                generation=m.generation,
                repo_url=canonical,
                observed_at=result.observed_at,
                previous_hash=previous,
                current_hash=m.current_hash,
                latest_run_id=m.latest_run_id,
            )
        )
    session.flush()
    if changed and m.enabled and m.reanalyze_on_change:
        submit(
            session,
            DiscoveryCreate(repo_url=canonical),
            deadline_seconds=deadline_seconds,
            monitor=m,
        )
    return item_id, m.id


def record_failure(session, lease, code, *, retry_after=None):
    try:
        m = fenced_monitor(session, lease)
    except Conflict:
        return
    m.error_code = "timeout" if code == "timeout" else "source_unavailable"
    m.last_checked_at = now()
    m.failure_count += 1
    backoff = min(3600, m.interval_seconds * (2 ** min(m.failure_count, 5)))
    if retry_after:
        backoff = max(backoff, min(retry_after, 3600))
    m.next_check_at = now() + timedelta(seconds=backoff) if m.enabled else None
    m.lease_token = None
    m.lease_expires_at = None
    session.flush()


def change_read(event):
    return ChangeRead(
        id=event.id,
        monitor_id=event.monitor_id,
        repo_url=event.repo_url,
        observed_at=event.observed_at,
        previous_hash=event.previous_hash,
        current_hash=event.current_hash,
        read_at=event.read_at,
        latest_run_id=event.latest_run_id,
    )


def changes(session, run_id, *, limit=20, cursor=None):
    m = monitor_for_run(session, run_id)
    stmt = (
        select(SourceChange)
        .where(SourceChange.monitor_id == m.id)
        .order_by(SourceChange.generation.desc())
        .limit(limit + 1)
    )
    if cursor:
        generation = session.scalar(
            select(SourceChange.generation).where(
                SourceChange.id == cursor, SourceChange.monitor_id == m.id
            )
        )
        if generation is None:
            raise ValueError("Invalid notification cursor")
        stmt = stmt.where(SourceChange.generation < generation)
    rows = list(session.scalars(stmt))
    more = len(rows) > limit
    rows = rows[:limit]
    return ChangePage(
        items=[change_read(e) for e in rows],
        limit=limit,
        next_cursor=rows[-1].id if more else None,
    )


def acknowledge(session, event_id):
    event = session.scalar(
        select(SourceChange)
        .where(SourceChange.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None:
        raise LookupError()
    if event.read_at is None:
        event.read_at = now()
    session.flush()
    return change_read(event)


def recover_expired(session, *, limit=20):
    # Only deadline-expired jobs are recovered; a slow live worker cannot later write.
    rows = list(
        session.scalars(
            select(DiscoveryRun)
            .where(
                DiscoveryRun.status.in_(["queued", "running"]),
                DiscoveryRun.deadline_at <= now(),
            )
            .order_by(DiscoveryRun.deadline_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    )
    for run in rows:
        expire_run(session, run.id)
        run.claim_token = None
        run.lease_expires_at = None
    session.flush()
    return len(rows)
