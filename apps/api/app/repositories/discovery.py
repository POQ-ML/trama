"""Discovery persistence, no network or generation.

Caller owns one short ``with session.begin():`` transaction per operation/batch.
These functions flush but NEVER commit. Complete ingestion before entering this
transaction: the ingestion repository intentionally commits each imported item.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import UUID, uuid4
from typing import Any, Literal, cast

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    AcademicItem,
    DiscoveryRun,
    DiscoverySuggestion,
    Entity,
    Evidence,
    Relationship,
    Source,
    SourceMonitor,
)
from app.schemas.discovery import (
    DiscoveryCreate,
    DiscoveryPage,
    ProjectRead,
    ArticleRead,
    EvidenceInput,
    EvidenceRead,
    FeedbackUpdate,
    ErrorCode,
    RunRead,
    RunStatus,
    RunUpdate,
    SuggestionInput,
    SuggestionRead,
    TopicRead,
)
from app.services.discovery_evidence import (
    SourceSnapshot,
    EvidenceSelection,
    build_evidence,
)

_TERMINAL = {"completed", "partial", "failed"}
_TRANSITIONS = {"queued": {"running", "failed"}, "running": _TERMINAL}


class IdentityConflict(ValueError):
    """A supplied item/project identity conflicts with persisted source identity."""


def snapshot_from_item(item: AcademicItem, provider: str) -> SourceSnapshot:
    """Trusted adapter. Only call with item+provider loaded together from DB.

    URLs/hashes/times are NEVER taken from selections/client/LLM. OpenAlex's
    canonical work URL avoids admitting arbitrary publisher/landing URLs.
    """
    side: Literal["repo", "article"]
    if item.item_type == "repository" and provider == "github":
        side = "repo"
        slug = (item.metadata_ or {}).get("full_name") or item.title
        url = f"https://github.com/{slug}"
    elif item.item_type == "article" and provider == "openalex":
        side = "article"
        url = f"https://openalex.org/{item.external_id}"
    else:
        raise IdentityConflict(
            "Expected an ingested GitHub repository or OpenAlex article"
        )
    seen = (item.metadata_ or {}).get("last_seen_at")
    if not isinstance(seen, str):
        raise ValueError("A real last_seen_at observation is required")
    observed = datetime.fromisoformat(seen)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("Source observation must include timezone")
    fields = {"title": item.title}
    if item.description is not None:
        fields["description"] = item.description
    readme = (item.metadata_ or {}).get("readme")
    if side == "repo" and isinstance(readme, str):
        fields["metadata.readme"] = readme
    return SourceSnapshot(item.id, side, fields, url, item.content_hash, observed)


def _entity_read(entity: Entity, item: AcademicItem) -> ProjectRead | ArticleRead:
    cls: Any = ProjectRead if entity.entity_type == "project" else ArticleRead
    return cls(
        id=entity.id,
        entity_type=entity.entity_type,
        origin_item_id=item.id,
        label=entity.label,
        external_id=item.external_id,
        original_url=item.original_url,
    )


def project_topics(item: AcademicItem) -> list[TopicRead]:
    """Projection ONLY: OpenAlex article classifications, never a project claim."""
    topics: dict[str, TopicRead] = {}
    for raw in (item.metadata_ or {}).get("topics") or []:
        if not isinstance(raw, dict):
            continue
        identifier = str(raw.get("id") or "").rsplit("/", 1)[-1]
        label = raw.get("display_name")
        if (
            not identifier.startswith("T")
            or not identifier[1:].isdigit()
            or not isinstance(label, str)
            or not label.strip()
        ):
            continue
        score = raw.get("score")
        if type(score) not in {int, float} or not 0 <= cast(float, score) <= 1:
            score = None
        topics[identifier] = TopicRead(id=identifier, label=label, score=score)
    return list(topics.values())


def upsert_item_entity(session: Session, item_id: UUID, entity_type: str) -> Entity:
    if entity_type not in {"project", "article"}:
        raise ValueError(
            "Only item-backed project/article entities belong to discovery"
        )
    item, provider = session.execute(
        select(AcademicItem, Source.provider)
        .join(Source)
        .where(AcademicItem.id == item_id)
        .with_for_update(of=AcademicItem)
        .execution_options(populate_existing=True)
    ).one()
    expected = (
        ("repository", "github")
        if entity_type == "project"
        else ("article", "openalex")
    )
    if (item.item_type, provider) != expected:
        raise IdentityConflict("Entity type does not match the persisted provider/item")
    return _upsert_entities(session, [(item, entity_type)])[item_id]


def _upsert_entities(
    session: Session, items: list[tuple[AcademicItem, str]]
) -> dict[UUID, Entity]:
    if not items:
        return {}
    items = sorted(items, key=lambda entry: entry[0].id)
    rows: list[dict[str, Any]] = [
        {
            "id": uuid4(),
            "entity_type": kind,
            "origin_item_id": item.id,
            "label": item.title,
        }
        for item, kind in items
    ]
    stmt: Any = insert(Entity).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Entity.entity_type, Entity.origin_item_id],
        index_where=Entity.entity_type.in_(["project", "article"])
        & Entity.origin_item_id.is_not(None),
        set_={"label": stmt.excluded.label},
    ).returning(Entity)
    entities = session.scalars(
        stmt, execution_options={"populate_existing": True}
    ).all()
    return {entity.origin_item_id: entity for entity in entities}


def create_run(
    session: Session, data: DiscoveryCreate, *, deadline_at: datetime | None = None
) -> DiscoveryRun:
    now = datetime.now(timezone.utc)
    deadline_at = deadline_at or now + timedelta(minutes=5)
    if (
        deadline_at.tzinfo is None
        or deadline_at.utcoffset() is None
        or deadline_at <= now
    ):
        raise ValueError("deadline_at must be in the future")
    run = DiscoveryRun(
        id=uuid4(),
        repo_url=data.repo_url,
        created_at=now,
        deadline_at=deadline_at,
        status="queued",
    )
    session.add(run)
    session.flush()
    return run


def _run_source_matches(session, run, snapshot):
    if snapshot.reference_url.lower() == run.repo_url.lower():
        return True
    monitor = session.get(SourceMonitor, run.monitor_id) if run.monitor_id else None
    return monitor is not None and monitor.source_item_id == snapshot.origin_item_id


def update_run(session: Session, run_id: UUID, data: RunUpdate) -> DiscoveryRun:
    run = session.scalars(
        select(DiscoveryRun)
        .where(DiscoveryRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if data.status.value not in _TRANSITIONS.get(run.status, set()):
        raise ValueError(
            "Invalid discovery state transition; terminal runs are immutable"
        )
    now = datetime.now(timezone.utc)
    if data.status != RunStatus.FAILED and run.deadline_at <= now:
        raise ValueError("Run deadline has expired; mark failed with timeout")
    next_project_id = run.project_id
    if data.project_id is not None:
        project, item, provider = session.execute(
            select(Entity, AcademicItem, Source.provider)
            .join(AcademicItem, Entity.origin_item_id == AcademicItem.id)
            .join(Source)
            .where(Entity.id == data.project_id)
            .with_for_update(of=AcademicItem)
            .execution_options(populate_existing=True)
        ).one()
        snap = snapshot_from_item(item, provider)
        if (
            project.entity_type != "project"
            or snap.side != "repo"
            or not _run_source_matches(session, run, snap)
        ):
            raise IdentityConflict("Run URL and project identity disagree")
        if run.project_id is not None and run.project_id != project.id:
            raise IdentityConflict("Run project identity is immutable")
        next_project_id = project.id
    if (
        data.status in {RunStatus.COMPLETED, RunStatus.PARTIAL}
        and next_project_id is None
    ):
        raise ValueError("Successful/partial runs require a project")
    now = datetime.now(timezone.utc)
    if data.status != RunStatus.FAILED and run.deadline_at <= now:
        raise ValueError("Run deadline expired while waiting for locks")
    run.project_id = next_project_id
    run.status = data.status.value
    run.error_code = data.error_code.value if data.error_code else None
    if data.status == RunStatus.RUNNING:
        run.started_at = now
    else:
        run.finished_at = now
    session.flush()
    return run


def _validate_evidence(data: EvidenceInput, item: AcademicItem, provider: str) -> dict:
    meta = data.metadata_
    snapshot = snapshot_from_item(item, provider)
    expected = build_evidence(
        snapshot,
        EvidenceSelection(
            cast(str, meta.get("source_field")),
            cast(int, meta.get("start")),
            cast(int, meta.get("end")),
            data.excerpt,
        ),
    )
    supplied = data.model_dump()
    if supplied != expected:
        raise ValueError(
            "Evidence must exactly match the trusted persisted observation"
        )
    canonical = dict(expected)
    canonical["origin_item_id"] = str(canonical["origin_item_id"])
    canonical["captured_at"] = canonical["captured_at"].isoformat()
    expected["snapshot_key"] = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return expected


def save_suggestions(
    session: Session, run_id: UUID, suggestions: list[SuggestionInput]
) -> list[UUID]:
    """Atomically persist <=50 proposals; one flush batch, no per-row commit.

    Membership freezes justification/score/topics and the exact evidence pair.
    Feedback is global; reprocessing creates a new run, never resets human state.
    """
    if not 1 <= len(suggestions) <= 50:
        raise ValueError("A batch must contain between 1 and 50 suggestions")
    if len({s.article_item_id for s in suggestions}) != len(suggestions):
        raise IdentityConflict("Duplicate article identity in one batch")
    with session.begin_nested():
        return _save_suggestions(session, run_id, suggestions)


def _save_suggestions(
    session: Session, run_id: UUID, suggestions: list[SuggestionInput]
) -> list[UUID]:
    run = session.scalars(
        select(DiscoveryRun)
        .where(DiscoveryRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if (
        run.status != "running"
        or run.project_id is None
        or run.deadline_at <= datetime.now(timezone.utc)
    ):
        raise ValueError("An unexpired running discovery with a project is required")
    project = cast(Entity, session.get(Entity, run.project_id))
    ids = {s.article_item_id for s in suggestions} | {project.origin_item_id}
    loaded = session.execute(
        select(AcademicItem, Source.provider)
        .join(Source)
        .where(AcademicItem.id.in_(ids))
        .order_by(AcademicItem.id)
        .with_for_update(of=AcademicItem)
        .execution_options(populate_existing=True)
    ).all()
    if run.deadline_at <= datetime.now(timezone.utc):
        raise ValueError("Run deadline expired while waiting for source locks")
    sources = {item.id: (item, provider) for item, provider in loaded}
    if set(sources) != ids:
        raise IdentityConflict("Missing source item")
    repo_item, repo_provider = sources[cast(UUID, project.origin_item_id)]
    repo_snapshot = snapshot_from_item(repo_item, repo_provider)
    if repo_snapshot.side != "repo" or not _run_source_matches(session, run, repo_snapshot):
        raise IdentityConflict("Project does not match run repository")
    validated: dict[UUID, list[dict]] = {}
    for proposal in suggestions:
        item, provider = sources[proposal.article_item_id]
        if item.item_type != "article" or provider != "openalex":
            raise IdentityConflict("Suggestion target must be an OpenAlex article")
        if {e.origin_item_id for e in proposal.evidences} != {repo_item.id, item.id}:
            raise IdentityConflict("Evidence must support exactly these two endpoints")
        validated[item.id] = [
            _validate_evidence(e, *sources[e.origin_item_id])
            for e in proposal.evidences
        ]
        validated[item.id].sort(key=lambda e: e["metadata_"]["side"] != "repo")
    entities = _upsert_entities(
        session, [(sources[s.article_item_id][0], "article") for s in suggestions]
    )
    rows: list[dict[str, Any]] = [
        {
            "id": uuid4(),
            "source_id": project.id,
            "target_id": entities[s.article_item_id].id,
            "relationship_type": "project_article",
            "status": "pending",
            "justification": s.justification,
            "score": s.score,
        }
        for s in suggestions
    ]
    rows.sort(key=lambda row: row["target_id"])
    stmt: Any = insert(Relationship).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            Relationship.source_id,
            Relationship.target_id,
            Relationship.relationship_type,
        ],
        set_={
            "justification": case(
                (Relationship.status == "pending", stmt.excluded.justification),
                else_=Relationship.justification,
            ),
            "score": case(
                (Relationship.status == "pending", stmt.excluded.score),
                else_=Relationship.score,
            ),
        },
    ).returning(Relationship.target_id, Relationship.id)
    rels: dict[UUID, UUID] = dict(session.execute(stmt).all())
    evidence_rows = []
    memberships: list[dict[str, Any]] = []
    for s in suggestions:
        rel_id = rels[entities[s.article_item_id].id]
        for evidence in validated[s.article_item_id]:
            evidence_rows.append({"id": uuid4(), "relationship_id": rel_id, **evidence})
    # Deduplicate shared keys within a batch as well as across runs.
    unique_evidence = {
        (row["relationship_id"], row["snapshot_key"]): row for row in evidence_rows
    }
    stmt = insert(Evidence).values(list(unique_evidence.values()))
    # A read-only DO NOTHING avoids touching immutable snapshots.
    session.execute(stmt.on_conflict_do_nothing(constraint="uq_evidence_snapshot"))
    evidence_ids = {
        (e.relationship_id, e.snapshot_key): e.id
        for e in session.scalars(
            select(Evidence).where(
                tuple_(Evidence.relationship_id, Evidence.snapshot_key).in_(
                    list(unique_evidence)
                )
            )
        )
    }
    for s in suggestions:
        rel_id = rels[entities[s.article_item_id].id]
        pair = validated[s.article_item_id]
        memberships.append(
            {
                "run_id": run_id,
                "relationship_id": rel_id,
                "repo_evidence_id": evidence_ids[rel_id, pair[0]["snapshot_key"]],
                "article_evidence_id": evidence_ids[rel_id, pair[1]["snapshot_key"]],
                "justification": s.justification,
                "score": s.score,
                "topics": [
                    t.model_dump()
                    for t in project_topics(sources[s.article_item_id][0])
                ],
            }
        )
    existing = session.scalars(
        select(DiscoverySuggestion).where(
            DiscoverySuggestion.run_id == run_id,
            DiscoverySuggestion.relationship_id.in_(
                [m["relationship_id"] for m in memberships]
            ),
        )
    ).all()
    by_id = {m.relationship_id: m for m in existing}
    for values in memberships:
        old = by_id.get(values["relationship_id"])
        if old is not None and any(getattr(old, k) != v for k, v in values.items()):
            raise IdentityConflict(
                "A run's suggestion snapshot is immutable; create a new run"
            )
    session.execute(
        insert(DiscoverySuggestion).values(memberships).on_conflict_do_nothing()
    )
    session.flush()
    if run.deadline_at <= datetime.now(timezone.utc):
        raise ValueError("Run deadline expired during persistence; batch rolled back")
    return [m["relationship_id"] for m in memberships]


def set_feedback(
    session: Session, relationship_id: UUID, data: FeedbackUpdate
) -> Relationship:
    rel = session.scalars(
        select(Relationship)
        .where(Relationship.id == relationship_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if rel.relationship_type != "project_article":
        raise ValueError("Feedback belongs to a discovery project_article suggestion")
    rel.status = data.status
    rel.updated_at = datetime.now(timezone.utc)
    session.flush()
    return rel


def get_run(session: Session, run_id: UUID) -> RunRead:
    run, project, item = session.execute(
        select(DiscoveryRun, Entity, AcademicItem)
        .outerjoin(Entity, DiscoveryRun.project_id == Entity.id)
        .outerjoin(AcademicItem, Entity.origin_item_id == AcademicItem.id)
        .where(DiscoveryRun.id == run_id)
        .execution_options(populate_existing=True)
    ).one()
    return RunRead(
        id=run.id,
        repo_url=run.repo_url,
        project=cast(ProjectRead, _entity_read(project, item)) if project else None,
        status=cast(RunStatus, run.status),
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        deadline_at=run.deadline_at,
        error_code=cast(ErrorCode | None, run.error_code),
        warnings=list(run.warnings or []),
    )


def get_discovery_page(
    session: Session, run_id: UUID, *, limit: int = 20, after: UUID | None = None
) -> DiscoveryPage:
    """Four SELECTs regardless of page size: header, bounded page, evidence pair."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    run = get_run(session, run_id)
    total = session.scalar(
        select(func.count())
        .select_from(DiscoverySuggestion)
        .where(DiscoverySuggestion.run_id == run_id)
    )
    stmt = (
        select(DiscoverySuggestion, Relationship, Entity, AcademicItem)
        .join(Relationship, DiscoverySuggestion.relationship_id == Relationship.id)
        .join(Entity, Relationship.target_id == Entity.id)
        .join(AcademicItem, Entity.origin_item_id == AcademicItem.id)
        .where(DiscoverySuggestion.run_id == run_id)
        .order_by(Relationship.id)
        .limit(limit + 1)
    )
    if after is not None:
        stmt = stmt.where(Relationship.id > after)
    rows = session.execute(stmt.execution_options(populate_existing=True)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    evidence_ids = {
        eid
        for membership, *_ in rows
        for eid in (membership.repo_evidence_id, membership.article_evidence_id)
    }
    evidence_by_id = (
        {
            e.id: e
            for e in session.scalars(
                select(Evidence).where(Evidence.id.in_(evidence_ids))
            )
        }
        if evidence_ids
        else {}
    )
    results = []
    for membership, rel, entity, item in rows:
        pair = [
            evidence_by_id[membership.repo_evidence_id],
            evidence_by_id[membership.article_evidence_id],
        ]
        results.append(
            SuggestionRead(
                id=rel.id,
                status=cast(Literal["pending", "confirmed", "rejected"], rel.status),
                project_id=rel.source_id,
                article=cast(ArticleRead, _entity_read(entity, item)),
                justification=membership.justification,
                score=membership.score,
                topics=[TopicRead.model_validate(t) for t in membership.topics],
                evidences=[
                    EvidenceRead(
                        id=e.id,
                        origin_item_id=e.origin_item_id,
                        side=cast(Any, e.metadata_)["side"],
                        reference_url=cast(str, e.reference_url),
                        locator=cast(str, e.locator),
                        excerpt=cast(str, e.excerpt),
                        capture_version=cast(str, e.capture_version),
                        captured_at=e.captured_at,
                    )
                    for e in pair
                ],
                created_at=rel.created_at,
                updated_at=rel.updated_at,
            )
        )
    return DiscoveryPage(
        run=run,
        suggestions=results,
        total_suggestions=cast(int, total),
        limit=limit,
        next_cursor=results[-1].id if more else None,
    )


def expire_run(session: Session, run_id: UUID) -> DiscoveryRun:
    """Explicit, idempotent timeout recovery; no hidden writes in GET/read paths."""
    run = session.scalars(
        select(DiscoveryRun)
        .where(DiscoveryRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    now = datetime.now(timezone.utc)
    if run.status not in _TERMINAL and run.deadline_at <= now:
        count = session.scalar(
            select(func.count())
            .select_from(DiscoverySuggestion)
            .where(DiscoverySuggestion.run_id == run_id)
        )
        run.status = "partial" if count and run.project_id is not None else "failed"
        run.error_code = "timeout"
        run.finished_at = now
        session.flush()
    return run
