"""Real PostgreSQL + injected external services; no GitHub/OpenAlex/LLM calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.main import create_app
from app.models import DiscoveryRun, SourceMonitor, SourceChange
from app.repositories import runtime as db
from app.schemas.discovery import DiscoveryCreate
from app.services.discovery_explanations import DiscoveryExplainer, CandidateRejected
from app.services.discovery_search import DiscoverySearch
from app.services.ingestion.github import _normalise_repo
from app.services.ingestion.models import NormalisedItem
from app.services.execution import Runtime
from app.services.source_collectors import CollectionResult, SourceFailure

TEXT = "Graph neural recommendation for scientific citation networks."


@pytest.fixture(scope="module")
def runtime_engine():
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Dedicated disposable TEST_DATABASE_URL required")
    assert make_url(raw).database.startswith("qa_discovery_")
    base = create_engine(raw)
    name = "qa_runtime_" + uuid4().hex[:12]
    with base.begin() as conn:
        conn.execute(text("CREATE SCHEMA " + name))
        # Prevent finding public.alembic_version through search_path.
        conn.execute(
            text(
                "CREATE TABLE "
                + name
                + ".alembic_version(version_num varchar(32) PRIMARY KEY)"
            )
        )
    scoped = (
        make_url(raw)
        .update_query_dict({"options": "-csearch_path=" + name + ",public"})
        .render_as_string(hide_password=False)
    )
    engine = create_engine(scoped)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with (
        patch("app.core.config.settings.DATABASE_URL", scoped),
        patch("logging.config.fileConfig"),
    ):
        command.upgrade(cfg, "head")
    yield engine, name
    engine.dispose()
    with base.begin() as conn:
        conn.execute(text("DROP SCHEMA " + name + " CASCADE"))
    base.dispose()


@pytest.fixture
def context(runtime_engine):
    engine, name = runtime_engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + name + ".sources CASCADE"))
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    app = create_app()

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield factory, client, engine


class FakeSource:
    def __init__(self, pool):
        self.pool = pool
        self.body = TEXT
        self.slug = "team/atlas"
        self.failure = None

    def check(self, url, *, state, deadline):
        assert self.pool.checkedout() == 0, "No session may survive external I/O"
        if self.failure:
            raise self.failure
        observed = datetime.now(timezone.utc)
        raw = {
            "id": 123,
            "name": self.slug.split("/")[1],
            "full_name": self.slug,
            "owner": {"login": self.slug.split("/")[0]},
            "description": self.body,
            "html_url": "https://github.com/" + self.slug,
            "private": False,
        }
        item = _normalise_repo(raw, self.body, "github", observed)
        return CollectionResult(item, "repo-etag", "readme-etag", observed, False)


class Searcher:
    def __init__(self, pool, items=True, fail=False):
        self.pool = pool
        self.items = items
        self.fail = fail

    async def search(self, query, *, limit, timeout):
        assert self.pool.checkedout() == 0
        if self.fail:
            raise RuntimeError("DO NOT LEAK TOKEN")
        if not self.items:
            return []
        return [
            NormalisedItem(
                "W123",
                "article",
                "Graph neural recommendation for scientific citation networks",
                "openalex",
                "b" * 64,
                description="We compare graph neural encoders for citation recommendation.",
                metadata={"doi": "10.1234/graph"},
            )
        ]


def worker(context, *, empty=False, fail=False, explainer=None):
    factory, _, engine = context
    source = FakeSource(engine.pool)
    runtime = Runtime(
        factory,
        source_monitor=source,
        search_factory=lambda: DiscoverySearch(Searcher(engine.pool, not empty, fail)),
        explainer_factory=explainer or (lambda: DiscoveryExplainer()),
    )
    return runtime, source


def create(client, key=None):
    response = client.post(
        "/api/v1/discoveries",
        json={"repo_url": "https://github.com/team/atlas"},
        headers={"Idempotency-Key": key} if key else {},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def run_tick(runtime):
    assert asyncio.run(runtime.tick())


def test_api_worker_fallback_and_idempotency(context):
    factory, client, _ = context
    identifier = create(client, "request_123")
    assert create(client, "request_456") == identifier
    runtime, _ = worker(context)
    run_tick(runtime)
    body = client.get("/api/v1/discoveries/" + identifier).json()
    assert (
        body["run"]["status"] == "partial"
        and body["run"]["error_code"] == "analysis_warning"
    )
    assert body["run"]["warnings"] == ["explanation_unavailable"]
    assert body["total_suggestions"] == 1
    suggestion = body["suggestions"][0]
    assert {e["side"] for e in suggestion["evidences"]} == {"repo", "article"}
    assert "contingência" in suggestion["justification"]
    assert (
        client.patch(
            "/api/v1/relationships/" + suggestion["id"] + "/feedback",
            json={"status": "confirmed"},
        ).json()["status"]
        == "confirmed"
    )
    assert create(client, "request_123") == identifier
    conflict = client.post(
        "/api/v1/discoveries",
        json={"repo_url": "https://github.com/other/repo"},
        headers={"Idempotency-Key": "request_123"},
    )
    assert conflict.status_code == 409
    assert set(conflict.json()["error"]) == {"code", "message", "retryable"}
    assert (
        client.get("/api/v1/discoveries/" + identifier + "?limit=51").status_code == 422
    )


@pytest.mark.parametrize("kind", ["empty", "insufficient", "failed", "abstain"])
def test_distinct_empty_insufficient_failure_and_abstention(context, kind):
    _, client, _ = context
    identifier = create(client)

    class Abstaining:
        async def explain(self, *args, **kwargs):
            raise CandidateRejected("semantic_mismatch")

    runtime, source = worker(
        context,
        empty=kind == "empty",
        fail=kind == "failed",
        explainer=(lambda: Abstaining()) if kind == "abstain" else None,
    )
    if kind == "insufficient":
        source.body = "Python application"
    run_tick(runtime)
    body = client.get("/api/v1/discoveries/" + identifier).json()
    assert body["total_suggestions"] == 0
    if kind in {"empty", "abstain"}:
        assert body["run"]["status"] == "completed" and body["run"]["warnings"] == []
    else:
        assert body["run"]["status"] == "failed"
        assert body["run"]["error_code"] == (
            "insufficient_context" if kind == "insufficient" else "source_unavailable"
        )
    assert "DO NOT LEAK" not in str(body)


def test_monitor_occurrences_stale_feedback_and_ack(context):
    factory, client, _ = context
    identifier = create(client)
    runtime, source = worker(context)
    run_tick(runtime)
    prefix = "/api/v1/discoveries/" + identifier
    original = client.get(prefix).json()["suggestions"][0]
    client.patch(
        "/api/v1/relationships/" + original["id"] + "/feedback",
        json={"status": "confirmed"},
    )
    assert (
        client.put(
            prefix + "/monitor", json={"enabled": True, "interval_seconds": 60}
        ).status_code
        == 200
    )
    for body in [TEXT + " Changed.", TEXT, TEXT + " Changed."]:
        source.body = body
        client.post(prefix + "/monitor/check")
        run_tick(runtime)
    notice = client.get(prefix + "/changes").json()
    assert len(notice["items"]) == 3
    monitor = client.get(prefix + "/monitor").json()
    assert monitor["stale"] is True
    client.post("/api/v1/source-changes/" + notice["items"][0]["id"] + "/read")
    assert client.get(prefix + "/monitor").json()["stale"] is True
    retained = client.get(prefix).json()["suggestions"][0]
    assert (
        retained["status"] == "confirmed"
        and retained["evidences"] == original["evidences"]
    )
    # A failed check never erases the last source hash or its stale indication.
    source.failure = SourceFailure()
    client.post(prefix + "/monitor/check")
    run_tick(runtime)
    monitor = client.get(prefix + "/monitor").json()
    assert monitor["stale"] and monitor["error_code"] == "source_unavailable"
    assert len(client.get(prefix + "/changes").json()["items"]) == 3
    client.put(prefix + "/monitor", json={"enabled": False})
    with factory() as s, s.begin():
        assert db.claim_monitor(s) is None


def test_latest_first_pagination_over_twenty_events(context):
    factory, client, _ = context
    identifier = create(client)
    runtime, _ = worker(context)
    run_tick(runtime)
    with factory() as s, s.begin():
        m = db.monitor_for_run(s, identifier)
        for generation in range(1, 27):
            s.add(
                SourceChange(
                    id=uuid4(),
                    monitor_id=m.id,
                    generation=generation,
                    repo_url=m.repo_url,
                    observed_at=db.now(),
                    previous_hash="a" * 64,
                    current_hash="b" * 64,
                    latest_run_id=m.latest_run_id,
                )
            )
        m.generation = 26
    page = client.get("/api/v1/discoveries/" + identifier + "/changes").json()
    assert len(page["items"]) == 20 and page["next_cursor"]
    with factory() as s:
        expected = s.scalar(
            select(SourceChange.id).where(SourceChange.generation == 26)
        )
        assert page["items"][0]["id"] == str(expected)
    remaining = client.get(
        "/api/v1/discoveries/" + identifier + "/changes?cursor=" + page["next_cursor"]
    ).json()
    assert len(remaining["items"]) == 6 and remaining["next_cursor"] is None
    assert not {i["id"] for i in page["items"]} & {i["id"] for i in remaining["items"]}


def test_numeric_rename_keeps_single_monitor(context):
    factory, client, _ = context
    identifier = create(client)
    runtime, source = worker(context)
    run_tick(runtime)
    prefix = "/api/v1/discoveries/" + identifier
    first = client.put(prefix + "/monitor", json={"enabled": True}).json()
    source.slug = "team/renamed"
    run_tick(runtime)
    renamed = client.get(prefix + "/monitor").json()
    assert (
        renamed["id"] == first["id"]
        and renamed["repo_url"] == "https://github.com/team/renamed"
    )
    response = client.post(
        "/api/v1/discoveries", json={"repo_url": renamed["repo_url"]}
    )
    assert response.status_code == 202
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(SourceMonitor)) == 1


def test_concurrent_enqueue_claim_and_fencing(context):
    factory, client, _ = context

    def enqueue(_):
        with factory() as s, s.begin():
            return db.submit(
                s, DiscoveryCreate(repo_url="https://github.com/team/atlas")
            ).id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(enqueue, range(4)))
    assert len(set(ids)) == 1

    def claim(_):
        with factory() as s, s.begin():
            return db.claim_run(s)

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, range(2)))
    assert sum(l is not None for l in leases) == 1
    lease = next(l for l in leases if l)
    runtime, source = worker(context)
    result = source.check(lease.repo_url, state=lease.state, deadline=100)
    with factory() as s, s.begin():
        db.record_observation(s, lease, result)
    with factory() as s, s.begin():
        with pytest.raises(db.Conflict):
            db.record_observation(s, lease, result)


def test_expiration_read_recovers_without_worker(context):
    factory, client, _ = context
    identifier = create(client)
    with factory() as s, s.begin():
        row = s.get(DiscoveryRun, identifier)
        row.deadline_at = row.created_at + timedelta(microseconds=1)
    body = client.get("/api/v1/discoveries/" + identifier).json()
    assert body["run"]["status"] == "failed" and body["run"]["error_code"] == "timeout"


def test_migration_runtime_refuses_data_loss(context):
    factory, client, engine = context
    create(client)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    from sqlalchemy.exc import DBAPIError

    with (
        pytest.raises(DBAPIError),
        patch(
            "app.core.config.settings.DATABASE_URL",
            engine.url.render_as_string(hide_password=False),
        ),
        patch("logging.config.fileConfig"),
    ):
        command.downgrade(cfg, "005_discovery_contract")
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(DiscoveryRun)) == 1


def test_busy_monitor_does_not_block_other_queued_jobs(context):
    factory, client, _ = context
    first = create(client)
    with factory() as session, session.begin():
        monitor = db.monitor_for_run(session, first, lock=True)
        monitor.lease_token = uuid4()
        monitor.lease_expires_at = db.now() + timedelta(seconds=30)
        second = db.submit(
            session, DiscoveryCreate(repo_url="https://github.com/team/second")
        )
        second_id = second.id
    with factory() as session, session.begin():
        claimed = db.claim_run(session)
        assert claimed is not None and claimed.run_id == second_id


def test_runtime_downgrade_preserves_legacy_runs(context):
    factory, _, engine = context
    from app.repositories.discovery import create_run, get_run

    with factory() as session, session.begin():
        legacy = create_run(
            session, DiscoveryCreate(repo_url="https://github.com/team/legacy")
        )
        identity = legacy.id
        created = legacy.created_at
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with (
        patch(
            "app.core.config.settings.DATABASE_URL",
            engine.url.render_as_string(hide_password=False),
        ),
        patch("logging.config.fileConfig"),
    ):
        command.downgrade(cfg, "005_discovery_contract")
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT repo_url FROM discovery_runs WHERE id=:id"),
                    {"id": identity},
                )
                == "https://github.com/team/legacy"
            )
        command.upgrade(cfg, "head")
    with factory() as session:
        restored = get_run(session, identity)
        assert restored.created_at == created and restored.status.value == "queued"



@pytest.mark.parametrize("configured_timeout,expected_timeout", [(30, 20), (12, 12), (0.5, 0.5)])
def test_runtime_explanation_timeout_respects_server_cap(configured_timeout, expected_timeout):
    from app.core.config import settings

    configured = settings.model_copy(
        update={
            "DISCOVERY_LLM_ENABLED": True,
            "GEMINI_API_KEY": "synthetic",
            "LLM_TIMEOUT_SECONDS": configured_timeout,
        }
    )
    runtime = Runtime(lambda: None, settings=configured)
    provider = object()
    with patch("app.services.llm.require_provider", return_value=provider) as factory:
        explainer = runtime._default_explainer()
    config = factory.call_args.args[0]
    assert config.timeout_seconds == explainer.timeout_seconds == expected_timeout
    assert config.max_retries == 0 and explainer.max_calls == 3


def test_runtime_disabled_explainer_keeps_budget_without_provider():
    from app.core.config import settings

    runtime = Runtime(
        lambda: None,
        settings=settings.model_copy(update={"DISCOVERY_LLM_ENABLED": False}),
    )
    with patch("app.services.llm.require_provider") as factory:
        explainer = runtime._default_explainer()
    factory.assert_not_called()
    assert explainer.provider is None
    assert explainer.timeout_seconds == 20 and explainer.max_calls == 3


def test_provider_reuse_sdk_budget_and_cleanup():
    from app.core.config import settings

    configured = settings.model_copy(
        update={
            "DISCOVERY_LLM_ENABLED": True,
            "LLM_MODEL": "configured-test-model",
            "GEMINI_API_KEY": "synthetic",
            "LLM_TIMEOUT_SECONDS": 12,
        }
    )
    runtime = Runtime(lambda: None, settings=configured)
    provider = object()
    with patch("app.services.llm.require_provider", return_value=provider) as factory:
        one, two = runtime._default_explainer(), runtime._default_explainer()
        assert one is not two and one.provider is two.provider is provider
        assert factory.call_count == 1
        config = factory.call_args.args[0]
        assert config.model == "configured-test-model" and config.api_key == "synthetic"
        assert config.max_retries == 0 and config.timeout_seconds == 12

    class Client:
        def __init__(self):
            self.aio = self
            self.async_closes = 0
            self.sync_closes = 0

        async def aclose(self):
            self.async_closes += 1

        def close(self):
            self.sync_closes += 1

    client = Client()
    with patch("google.genai.Client", return_value=client) as sdk:
        runtime._client_factory(api_key="synthetic")
        assert sdk.call_args.kwargs["http_options"].retry_options.attempts == 1
    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())
    assert client.async_closes == client.sync_closes == 1
