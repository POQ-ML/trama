"""Navigation regressions on an isolated PostgreSQL schema; no external services."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import time

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.api.v1.projects import workspace_owner
from app.models import AcademicProject, DiscoveryRun, ProjectSource, SourceChange, SourceMonitor, User
from app.repositories import runtime as db
from app.repositories.discovery import create_run
from app.schemas.discovery import DiscoveryCreate
# Imported fixtures create/drop their own schema; they never use public data.
from test_runtime_mvp import FakeSource, context, runtime_engine  # noqa: F401


@pytest.fixture
def nav(context):
    factory, client, engine = context
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE academic_projects, users CASCADE"))
    return factory, client, engine


def new_project(client, name="Academic work"):
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def add_source(client, pid, slug="team/atlas"):
    response = client.post(
        f"/api/v1/projects/{pid}/sources",
        json={"source_type": "github", "repo_url": "https://github.com/" + slug},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_navigation_does_not_collect_and_reuses_diagnostics(nav):
    factory, client, _ = nav
    pid = new_project(client)
    source = add_source(client, pid)
    assert source["latest_run"] is None
    assert add_source(client, pid)["id"] == source["id"]
    pid2 = new_project(client, "Second")
    shared = add_source(client, pid2)
    other = add_source(client, pid, "team/other")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(DiscoveryRun)) == 0
        assert session.scalar(select(func.count()).select_from(SourceMonitor)) == 2
    response = client.post(f'/api/v1/projects/{pid}/sources/{source["id"]}/discoveries')
    assert response.status_code == 202, response.text
    rid = response.json()["id"]
    assert client.post(
        f'/api/v1/projects/{pid2}/sources/{shared["id"]}/discoveries'
    ).json()["id"] == rid
    assert client.get(
        f'/api/v1/projects/{pid2}/sources/{shared["id"]}'
    ).json()["latest_run"]["id"] == rid
    assert client.get(
        f'/api/v1/projects/{pid}/sources/{source["id"]}/discoveries/{rid}'
    ).status_code == 200
    assert client.get(
        f'/api/v1/projects/{pid}/sources/{other["id"]}/discoveries/{rid}'
    ).status_code == 404
    assert client.get(f"/api/v1/discoveries/{rid}").status_code == 200
    assert client.get(f"/api/v1/projects/{pid}").json()["source_count"] == 2


def test_owner_scope_all_routes_and_untrusted_owner(nav):
    factory, client, _ = nav
    shared_pid = new_project(client, "Shared")
    with factory() as session, session.begin():
        a, b = User(email="a@example.invalid"), User(email="b@example.invalid")
        session.add_all([a, b])
        session.flush()
        aid, bid = a.id, b.id
    client.app.dependency_overrides[workspace_owner] = lambda: aid
    pid = new_project(client, "Owned A")
    source = add_source(client, pid)
    assert client.get("/api/v1/projects").json()[0]["id"] == pid
    assert client.get(f"/api/v1/projects/{shared_pid}").status_code == 404
    client.app.dependency_overrides[workspace_owner] = lambda: bid
    paths = [
        ("get", f"/projects/{pid}", None),
        ("get", f'/projects/{pid}/sources/{source["id"]}', None),
        ("post", f"/projects/{pid}/sources", {"source_type": "github", "repo_url": source["repo_url"]}),
        ("post", f'/projects/{pid}/sources/{source["id"]}/discoveries', None),
        ("get", f'/projects/{pid}/sources/{source["id"]}/discoveries/{uuid4()}', None),
    ]
    for method, path, body in paths:
        kwargs = {"json": body} if body else {}
        response = getattr(client, method)("/api/v1" + path, **kwargs)
        assert response.status_code == 404, response.text
    assert client.get("/api/v1/projects/activity").json() == []
    assert client.post(
        "/api/v1/projects", json={"name": "Forged", "owner_id": str(aid)}
    ).status_code == 422
    client.app.dependency_overrides.pop(workspace_owner)
    assert client.get(
        "/api/v1/projects", headers={"X-Owner-Id": str(aid)}
    ).json()[0]["id"] == shared_pid


def test_activity_existing_only_scoped_limited(nav):
    factory, client, _ = nav
    assert client.get("/api/v1/projects/activity").json() == []
    pid = new_project(client)
    source = add_source(client, pid)
    pid2 = new_project(client)
    add_source(client, pid2)
    with factory() as session, session.begin():
        mid = session.scalar(select(ProjectSource.monitor_id).where(ProjectSource.id == source["id"]))
        user = User(email="activity@example.invalid")
        session.add(user)
        session.flush()
        uid = user.id
        for n in range(12):
            session.add(SourceChange(
                monitor_id=mid, generation=n + 1, repo_url=source["repo_url"],
                observed_at=datetime(2026, 1, n + 1, tzinfo=timezone.utc),
                previous_hash="a" * 64, current_hash="b" * 64,
            ))
    rows = client.get("/api/v1/projects/activity").json()
    assert len(rows) == 10
    assert rows[0]["observed_at"].startswith("2026-01-12")
    assert {row["project_id"] for row in rows} == {pid, pid2}
    assert all(row["kind"] == "source_changed" for row in rows)
    assert len({(row["id"], row["project_id"], row["source_id"]) for row in rows}) == 10
    client.app.dependency_overrides[workspace_owner] = lambda: uid
    assert client.get("/api/v1/projects/activity").json() == []
    client.app.dependency_overrides.pop(workspace_owner)


def test_rename_alias_transfers_bindings_without_changing_ids(nav):
    factory, client, engine = nav
    pid = new_project(client)
    source = add_source(client, pid)
    fake = FakeSource(engine.pool)
    with factory() as session:
        mid = session.scalar(select(ProjectSource.monitor_id).where(ProjectSource.id == source["id"]))

    def observe():
        with factory() as session, session.begin():
            monitor = session.get(SourceMonitor, mid)
            monitor.enabled = True
            monitor.next_check_at = db.now()
            session.flush()
            lease = db.claim_monitor(session)
        result = fake.check(source["repo_url"], state=lease.state, deadline=time.monotonic() + 10)
        with factory() as session, session.begin():
            db.record_observation(session, lease, result)

    observe()
    pid2 = new_project(client)
    alias = add_source(client, pid2, "team/renamed")
    fake.slug = "team/renamed"
    observe()
    renamed = client.get(f'/api/v1/projects/{pid}/sources/{source["id"]}').json()
    assert renamed["repo_url"] == "https://github.com/team/renamed"
    assert add_source(client, pid, "team/renamed")["id"] == source["id"]
    assert client.get(
        f'/api/v1/projects/{pid2}/sources/{alias["id"]}'
    ).json()["repo_url"] == renamed["repo_url"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceMonitor)) == 1


def test_validation(nav):
    _, client, _ = nav
    assert client.post("/api/v1/projects", json={"name": "  "}).status_code == 422
    pid = new_project(client)
    for body in [
        {"source_type": "moodle", "repo_url": "https://github.com/a/b"},
        {"source_type": "github", "repo_url": "http://127.0.0.1/x"},
        {"source_type": "github", "repo_url": "https://github.com/a/b", "monitor_id": str(uuid4())},
    ]:
        assert client.post(f"/api/v1/projects/{pid}/sources", json=body).status_code == 422


def test_scoped_idempotency_terminal_and_conflict(nav):
    factory, client, _ = nav
    pid = new_project(client)
    source = add_source(client, pid)
    other = add_source(client, pid, "team/second")
    url = f'/api/v1/projects/{pid}/sources/{source["id"]}/discoveries'
    headers = {"Idempotency-Key": "navigation-1234"}
    first = client.post(url, headers=headers)
    assert first.status_code == 202
    rid = first.json()["id"]
    with factory() as session, session.begin():
        run = session.get(DiscoveryRun, rid)
        run.status, run.error_code, run.finished_at = "failed", "source_unavailable", db.now()
    repeated = client.post(url, headers=headers)
    assert repeated.status_code == 202
    assert repeated.json()["id"] == rid and repeated.json()["status"] == "failed"
    assert client.post(
        f'/api/v1/projects/{pid}/sources/{other["id"]}/discoveries', headers=headers
    ).status_code == 409


def test_migration_legacy_backfill_and_loss_guard(nav):
    factory, client, engine = nav
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    scoped = engine.url.render_as_string(hide_password=False)
    with patch("app.core.config.settings.DATABASE_URL", scoped), patch("logging.config.fileConfig"):
        command.downgrade(cfg, "006_discovery_runtime")
        with factory() as session, session.begin():
            run = create_run(session, DiscoveryCreate(repo_url="https://github.com/legacy/repo"))
            rid = run.id
        with engine.connect() as conn:
            before = conn.execute(text("SELECT to_jsonb(r) FROM discovery_runs r WHERE id=:id"), {"id": rid}).scalar_one()
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            after = conn.execute(text("SELECT to_jsonb(r) FROM discovery_runs r WHERE id=:id"), {"id": rid}).scalar_one()
        assert after == before
        projects = client.get("/api/v1/projects").json()
        assert len(projects) == 1 and projects[0]["name"] == "Fontes anteriores"
        pid = projects[0]["id"]
        sources = client.get(f"/api/v1/projects/{pid}").json()["sources"]
        assert len(sources) == 1 and sources[0]["latest_run"]["id"] == str(rid)
        assert client.get(
            f'/api/v1/projects/{pid}/sources/{sources[0]["id"]}/discoveries/{rid}'
        ).status_code == 200
        with pytest.raises(DBAPIError, match="Cannot downgrade populated academic projects"):
            command.downgrade(cfg, "006_discovery_runtime")
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(AcademicProject)) == 1


def test_unrelated_monitorless_run_is_not_exposed(nav):
    factory, client, _ = nav
    pid = new_project(client)
    source = add_source(client, pid)
    with factory() as session, session.begin():
        run = create_run(session, DiscoveryCreate(repo_url="https://github.com/unrelated/repo"))
        rid = run.id
    assert client.get(
        f'/api/v1/projects/{pid}/sources/{source["id"]}'
    ).json()["latest_run"] is None
    assert client.get(
        f'/api/v1/projects/{pid}/sources/{source["id"]}/discoveries/{rid}'
    ).status_code == 404
