"""PostgreSQL contract tests. TEST_DATABASE_URL must name a disposable QA DB."""

from datetime import datetime, timedelta, timezone
import hashlib
import os
from uuid import uuid4
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session

from app.models import (
    DiscoveryRun,
    AcademicItem,
    Source,
    Entity,
    Evidence,
    Relationship,
    DiscoverySuggestion,
)
from app.repositories.discovery import (
    IdentityConflict,
    create_run,
    expire_run,
    get_discovery_page,
    get_run,
    save_suggestions,
    set_feedback,
    snapshot_from_item,
    update_run,
    upsert_item_entity,
)
from app.schemas.discovery import (
    DiscoveryCreate,
    EvidenceInput,
    FeedbackUpdate,
    RunUpdate,
    SuggestionInput,
)
from app.services.discovery_evidence import (
    EvidenceSelection,
    build_project_article_evidence,
)


@pytest.fixture(scope="module")
def discovery_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable TEST_DATABASE_URL required")
    assert make_url(url).database.startswith("qa_discovery_"), (
        "Use a dedicated disposable discovery QA database"
    )
    engine = create_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with patch("logging.config.fileConfig"):
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(discovery_engine):
    with discovery_engine.connect() as conn:
        tx = conn.begin()
        with Session(
            conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        tx.rollback()


def item(session, number=1, provider="openalex", title="Same article title"):
    source = session.scalar(
        select(Source).where(
            Source.provider == provider,
            Source.canonical_id == f"discovery-test-{provider}",
        )
    )
    if source is None:
        source = Source(
            id=uuid4(),
            provider=provider,
            canonical_id=f"discovery-test-{provider}",
            name=provider,
        )
        session.add(source)
    observed = datetime.now(timezone.utc) - timedelta(seconds=1)
    body = f"Graphs support context discovery {number}."
    row = AcademicItem(
        id=uuid4(),
        source=source,
        external_id=str(number) if provider == "github" else f"W{number}",
        item_type="repository" if provider == "github" else "article",
        title="owner/repo" if provider == "github" else title,
        description=body,
        original_url="https://publisher.example/article",
        captured_at=observed,
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        metadata_={
            "last_seen_at": observed.isoformat(),
            "full_name": "owner/repo",
            "readme": body,
            "topics": [{"id": "T1", "display_name": "Graphs", "score": 0.9}],
        },
    )
    session.add(row)
    session.flush()
    return row


def running(session):
    repo = item(session, provider="github")
    project = upsert_item_entity(session, repo.id, "project")
    run = create_run(session, DiscoveryCreate(repo_url="https://github.com/owner/repo"))
    update_run(session, run.id, RunUpdate(status="running", project_id=project.id))
    return repo, project, run


def proposal(repo, article, explanation="Potential contribution"):
    snapshots = [
        snapshot_from_item(repo, "github"),
        snapshot_from_item(article, "openalex"),
    ]
    selections = [
        EvidenceSelection("description", 0, 6, s.fields["description"][:6])
        for s in snapshots
    ]
    pair = build_project_article_evidence(*snapshots, *selections)
    return SuggestionInput(
        article_item_id=article.id,
        justification=explanation,
        score=0.8,
        evidences=tuple(EvidenceInput.model_validate(e) for e in pair),
    )


def test_identity_same_label_rename_and_conflict(session):
    a, b = item(session, 1), item(session, 2)
    ea, eb = (
        upsert_item_entity(session, a.id, "article"),
        upsert_item_entity(session, b.id, "article"),
    )
    assert ea.id != eb.id and ea.label == eb.label
    old = ea.id
    a.title = "Corrected title"
    session.flush()
    assert upsert_item_entity(session, a.id, "article").id == old
    assert ea.label == "Corrected title"
    with pytest.raises(IdentityConflict):
        upsert_item_entity(session, a.id, "project")
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(
            Entity(entity_type="article", label="duplicate", origin_item_id=a.id)
        )
        session.flush()


def test_atomic_idempotency_feedback_and_run_snapshots(session):
    repo, project, run = running(session)
    article = item(session)
    initial = proposal(repo, article)
    rel = save_suggestions(session, run.id, [initial])[0]
    assert save_suggestions(session, run.id, [initial]) == [rel]
    assert session.scalar(select(func.count()).select_from(Evidence)) == 2
    first = get_discovery_page(session, run.id).suggestions[0]
    set_feedback(session, rel, FeedbackUpdate(status="confirmed"))
    update_run(session, run.id, RunUpdate(status="completed"))
    # A new observation updates AcademicItem, never its old evidence/justification.
    article.description = "A completely different source version"
    article.content_hash = hashlib.sha256(article.description.encode()).hexdigest()
    article.metadata_ = {
        **article.metadata_,
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
        "topics": [{"id": "T2", "display_name": "New classification"}],
    }
    session.flush()
    second = create_run(session, DiscoveryCreate(repo_url=run.repo_url))
    update_run(session, second.id, RunUpdate(status="running", project_id=project.id))
    assert save_suggestions(
        session, second.id, [proposal(repo, article, "Another explanation")]
    ) == [rel]
    old, new = (
        get_discovery_page(session, run.id).suggestions[0],
        get_discovery_page(session, second.id).suggestions[0],
    )
    assert old.justification == first.justification and old.score == first.score
    assert old.topics[0].id == "T1" and new.topics[0].id == "T2"
    assert old.evidences[1].excerpt == first.evidences[1].excerpt
    assert old.status == new.status == "confirmed"
    assert new.justification == "Another explanation"
    set_feedback(session, rel, FeedbackUpdate(status="rejected"))
    assert get_discovery_page(session, second.id).suggestions[0].status == "rejected"
    with pytest.raises(ValueError):
        update_run(session, run.id, RunUpdate(status="running"))


def test_forged_evidence_rolls_back_whole_batch(session):
    repo, _, run = running(session)
    first, second = item(session, 1), item(session, 2)
    bad = proposal(repo, second)
    bad.evidences[0].excerpt = "Invented source text"
    with pytest.raises(ValueError):
        save_suggestions(session, run.id, [proposal(repo, first), bad])
    assert session.scalar(select(func.count()).select_from(Relationship)) == 0
    assert session.scalar(select(func.count()).select_from(Evidence)) == 0
    assert session.scalar(select(func.count()).select_from(DiscoverySuggestion)) == 0


def test_direction_and_evidence_immutable_at_database(session):
    repo, project, run = running(session)
    article = item(session)
    rel_id = save_suggestions(session, run.id, [proposal(repo, article)])[0]
    evidence = session.scalar(
        select(Evidence).where(Evidence.relationship_id == rel_id)
    )
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(
            text("UPDATE evidences SET excerpt=:text WHERE id=:id"),
            {"text": "modified", "id": evidence.id},
        )
    target = session.scalar(select(Entity).where(Entity.origin_item_id == article.id))
    with pytest.raises(DBAPIError), session.begin_nested():
        session.add(
            Relationship(
                source_id=target.id,
                target_id=project.id,
                relationship_type="project_article",
            )
        )
        session.flush()
    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(
            text("UPDATE entities SET origin_item_id=NULL WHERE id=:id"),
            {"id": project.id},
        )


def test_query_limit_cursor_total_and_constant_select_count(session, discovery_engine):
    repo, _, run = running(session)
    articles = [item(session, i) for i in range(1, 7)]
    save_suggestions(session, run.id, [proposal(repo, a) for a in articles])
    session.expunge_all()
    counts = []

    def count(conn, cursor, statement, params, ctx, many):
        if statement.lstrip().upper().startswith("SELECT"):
            counts.append(statement)

    event.listen(discovery_engine, "before_cursor_execute", count)
    try:
        page = get_discovery_page(session, run.id, limit=2)
        assert len(counts) == 4
        assert page.total_suggestions == 6 and page.next_cursor
        counts.clear()
        second = get_discovery_page(session, run.id, limit=50, after=page.next_cursor)
        assert len(counts) == 4
        assert second.total_suggestions == 6 and second.next_cursor is None
        assert len(second.suggestions) == 4
        assert not {s.id for s in page.suggestions} & {s.id for s in second.suggestions}
    finally:
        event.remove(discovery_engine, "before_cursor_execute", count)
    with pytest.raises(ValueError):
        get_discovery_page(session, run.id, limit=51)


def test_deadline_and_explicit_expiration(session):
    data = DiscoveryCreate(repo_url="https://github.com/owner/repo")
    with pytest.raises(ValueError):
        create_run(session, data, deadline_at=datetime.now(timezone.utc))
    run = create_run(session, data)
    run.deadline_at = run.created_at + timedelta(microseconds=1)
    session.flush()
    with pytest.raises(ValueError):
        update_run(session, run.id, RunUpdate(status="running"))
    assert expire_run(session, run.id).status == "failed"
    ended = run.finished_at
    assert expire_run(session, run.id).finished_at == ended
    assert get_run(session, run.id).error_code.value == "timeout"


def test_running_with_results_expires_partial(session):
    repo, _, run = running(session)
    save_suggestions(session, run.id, [proposal(repo, item(session))])
    run.deadline_at = run.created_at + timedelta(microseconds=1)
    session.flush()
    assert expire_run(session, run.id).status == "partial"
    assert get_discovery_page(session, run.id).suggestions


@pytest.fixture
def committed(discovery_engine):
    """Independent connections can observe commits; cleanup only this fixture's sources."""
    with Session(discovery_engine, expire_on_commit=False) as s, s.begin():
        repo, project, run = running(s)
        article = item(s)
        proposed = proposal(repo, article)
        rel_id = save_suggestions(s, run.id, [proposed])[0]
        values = (repo.id, project.id, run.id, article.id, rel_id, proposed)
        source_ids = [repo.source_id, article.source_id]
    yield values
    with discovery_engine.begin() as conn:
        items = select(AcademicItem.id).where(AcademicItem.source_id.in_(source_ids))
        entities = select(Entity.id).where(Entity.origin_item_id.in_(items))
        conn.execute(
            DiscoveryRun.__table__.delete().where(DiscoveryRun.project_id.in_(entities))
        )
        conn.execute(
            Relationship.__table__.delete().where(
                Relationship.source_id.in_(entities)
                | Relationship.target_id.in_(entities)
            )
        )
        conn.execute(Entity.__table__.delete().where(Entity.id.in_(entities)))
        conn.execute(
            AcademicItem.__table__.delete().where(
                AcademicItem.source_id.in_(source_ids)
            )
        )
        conn.execute(Source.__table__.delete().where(Source.id.in_(source_ids)))


def test_concurrent_commits_refresh_long_lived_identity_map(
    discovery_engine, committed
):
    repo_id, project_id, run_id, article_id, rel_id, _ = committed
    with Session(discovery_engine) as stale:
        stale.get(DiscoveryRun, run_id)
        rel = stale.get(Relationship, rel_id)
        entity = stale.scalar(select(Entity).where(Entity.origin_item_id == article_id))
        assert rel.status == "pending"
        with Session(discovery_engine) as other, other.begin():
            article = other.get(AcademicItem, article_id)
            article.title = "Renamed after another commit"
            other.flush()
            upsert_item_entity(other, article_id, "article")
            set_feedback(other, rel_id, FeedbackUpdate(status="confirmed"))
            update_run(other, run_id, RunUpdate(status="completed"))
        page = get_discovery_page(stale, run_id)
        assert page.run.status.value == "completed"
        assert page.suggestions[0].status == "confirmed"
        assert page.suggestions[0].article.label == "Renamed after another commit"
        assert entity.label == "Renamed after another commit"
        with pytest.raises(ValueError):
            update_run(stale, run_id, RunUpdate(status="running"))


def test_stale_item_evidence_is_revalidated_after_other_commit(
    discovery_engine, committed
):
    _, _, run_id, article_id, _, old_proposal = committed
    with Session(discovery_engine) as stale:
        old = stale.get(AcademicItem, article_id)
        with Session(discovery_engine) as other, other.begin():
            article = other.get(AcademicItem, article_id)
            article.description = "New observation invalidates old selections"
            article.content_hash = hashlib.sha256(
                article.description.encode()
            ).hexdigest()
            article.metadata_ = {
                **article.metadata_,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            }
        with pytest.raises(ValueError):
            save_suggestions(stale, run_id, [old_proposal])
        stale.rollback()
        assert old.description == "New observation invalidates old selections"


def test_deadline_rechecked_after_waiting_for_source_lock(discovery_engine, committed):
    from threading import Event, Thread
    import time

    _, _, run_id, article_id, _, proposed = committed
    with discovery_engine.begin() as conn:
        conn.execute(
            text("UPDATE discovery_runs SET deadline_at=:deadline WHERE id=:id"),
            {
                "deadline": datetime.now(timezone.utc) + timedelta(milliseconds=200),
                "id": run_id,
            },
        )
    waiting = Event()
    errors = []

    def statement(conn, cursor, sql, params, ctx, many):
        if "FOR UPDATE OF academic_items" in sql:
            waiting.set()
            assert "ORDER BY academic_items.id" in sql

    def worker():
        try:
            with Session(discovery_engine) as session, session.begin():
                save_suggestions(session, run_id, [proposed])
        except Exception as exc:
            errors.append(exc)

    event.listen(discovery_engine, "before_cursor_execute", statement)
    try:
        with discovery_engine.connect() as blocker:
            tx = blocker.begin()
            blocker.execute(
                select(AcademicItem.id)
                .where(AcademicItem.id == article_id)
                .with_for_update()
            )
            thread = Thread(target=worker)
            thread.start()
            assert waiting.wait(2)
            time.sleep(0.25)
            tx.commit()
        thread.join(3)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], ValueError)
        assert "deadline" in str(errors[0]).lower()
    finally:
        event.remove(discovery_engine, "before_cursor_execute", statement)
