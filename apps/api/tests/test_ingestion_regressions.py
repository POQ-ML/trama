"""Regression coverage for the six defects confirmed in PR #9 QA."""

import copy
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from app.models import AcademicItem
from app.repositories.ingestion import get_or_create_source, upsert_item
from app.services.ingestion.github import (
    ConnectorError,
    GitHubConnector,
    _normalise_repo,
    _SkipRepo,
)
from app.services.ingestion.openalex import OpenAlexConnector, _normalise_work
from app.services.ingestion.pipeline import IngestionPipeline
from sqlalchemy import select

NOW = datetime(2026, 1, 1, tzinfo=UTC)
REPO = {
    "id": 1,
    "name": "repo",
    "full_name": "owner/repo",
    "owner": {"login": "owner"},
    "html_url": "https://github.com/owner/repo",
    "description": "description",
}
WORK = {
    "id": "https://openalex.org/W001",
    "title": "Work",
    "publication_year": 2020,
    "publication_date": "2020-01-01",
    "primary_location": {"landing_page_url": "https://old.example"},
}


@pytest.fixture
def session(pg_engine):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", pg_engine.url.render_as_string(hide_password=False)
    )
    with patch("logging.config.fileConfig"):
        command.upgrade(config, "head")
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


def source(s, key):
    return get_or_create_source(s, key, key, key)


@pytest.mark.parametrize("previous", [None, "old"])
def test_readme_update(session, previous):
    src = source(session, "github")
    a = _normalise_repo(REPO, previous, "github", NOW)
    b = _normalise_repo(REPO, "new", "github", NOW)
    assert upsert_item(session, src, a) == "created"
    outcome = upsert_item(session, src, b)
    row = session.scalars(select(AcademicItem)).one()
    assert (outcome, row.metadata_["readme"]) == ("updated", "new")
    assert upsert_item(session, src, b) == "unchanged"
    assert row.metadata_["captured_at"] == NOW.isoformat()
    assert row.captured_at == NOW


@pytest.mark.parametrize("field", ["url", "date"])
def test_publication_provenance_update(session, field):
    src = source(session, "openalex")
    raw = copy.deepcopy(WORK)
    upsert_item(session, src, _normalise_work(raw, "openalex", NOW))
    if field == "date":
        raw["publication_date"] = "2020-02-02"
    else:
        raw["primary_location"]["landing_page_url"] = "https://new.example"
    outcome = upsert_item(session, src, _normalise_work(raw, "openalex", NOW))
    row = session.scalars(select(AcademicItem)).one()
    assert outcome == "updated"
    assert row.original_url == raw["primary_location"]["landing_page_url"]
    assert row.original_date.date().isoformat() == raw["publication_date"]
    assert (
        upsert_item(session, src, _normalise_work(raw, "openalex", NOW)) == "unchanged"
    )


@pytest.mark.parametrize(
    "mode", [{"repos": ["owner/repo"]}, {"org_or_user": "owner"}, {"query": "test"}]
)
def test_auth_error_counts(session, mode):
    with patch(
        "app.services.ingestion.github._make_request",
        side_effect=ConnectorError("HTTP 401"),
    ):
        result = IngestionPipeline(session).run(GitHubConnector(**mode))
    assert result.errors == 1


def test_user_mode():
    urls = []

    def request(url, *args):
        urls.append(url)
        if "/orgs/" in url:
            raise _SkipRepo("HTTP 404")
        return [REPO], {}

    with patch("app.services.ingestion.github._make_request", side_effect=request):
        items = list(GitHubConnector(org_or_user="owner", fetch_readme=False).fetch())
    assert len(items) == 1
    assert any("/users/owner/repos" in u for u in urls)


def test_timestamps_provenance_and_changes(session):
    src = source(session, "github")
    a = _normalise_repo(REPO, "readme", "github", NOW)
    assert upsert_item(session, src, a) == "created"
    row = session.scalars(select(AcademicItem)).one()
    original = row.captured_at
    seen = row.metadata_["last_seen_at"]
    a.captured_at = datetime(2026, 2, 1, tzinfo=UTC)
    assert upsert_item(session, src, a) == "unchanged"
    session.refresh(row)
    assert row.captured_at == original
    assert row.metadata_["last_seen_at"] >= seen
    changed = {**REPO, "description": "new description"}
    assert (
        upsert_item(
            session, src, _normalise_repo(changed, "new", "github", a.captured_at)
        )
        == "updated"
    )
    session.refresh(row)
    assert row.captured_at == original
    assert row.metadata_["captured_at"] == NOW.isoformat()
    assert row.description == "new description"


def test_real_integrity_error_rollback_isolation(session):
    class Connector:
        source_key = "github"

        def fetch(self):
            for i in range(3):
                item = _normalise_repo({**REPO, "id": i + 1}, None, "github", NOW)
                if i == 1:
                    item.item_type = "INVALID"
                yield item

    result = IngestionPipeline(session).run(Connector())
    assert (result.created, result.errors, result.total_fetched) == (2, 1, 3)
    assert set(session.scalars(select(AcademicItem.external_id))) == {"1", "3"}


def test_readme_absent_real_connector(session):
    def request(url, *args):
        if url.endswith("/readme"):
            raise _SkipRepo("HTTP 404")
        return REPO, {}

    with patch("app.services.ingestion.github._make_request", side_effect=request):
        result = IngestionPipeline(session).run(GitHubConnector(repos=["owner/repo"]))
    assert (result.created, result.errors) == (1, 0)
    assert "readme" not in session.scalars(select(AcademicItem)).one().metadata_


def test_openalex_filters_encoded():
    c = OpenAlexConnector(filter_str="institutions.id:I4390", query="machine learning")
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(c._build_url({"page": "1"})).query)
    assert q["filter"] == ["institutions.id:I4390"]
    assert q["search"] == ["machine learning"]


@pytest.mark.parametrize(
    "invocation", [["scripts/ingest.py"], ["-m", "scripts.ingest"]]
)
def test_documented_cli_import(invocation):
    env = {
        k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "DATABASE_URL")
    }
    proc = subprocess.run(
        [sys.executable, *invocation, "github", "--repos", "owner/repo"],
        env=env,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stderr
    assert "ModuleNotFoundError" not in proc.stderr
    assert "DATABASE_URL is not set" in proc.stderr


def test_repository_import_standalone():
    proc = subprocess.run(
        [sys.executable, "-c", "import app.repositories.ingestion"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_auth_exit(session):
    from argparse import Namespace

    from scripts.ingest import _run_github

    with (
        patch("scripts.ingest._require_db", return_value=session),
        patch(
            "app.services.ingestion.github._make_request",
            side_effect=ConnectorError("HTTP 401"),
        ),
    ):
        code = _run_github(
            Namespace(query=None, repos="owner/repo", org=None, max_pages=1)
        )
    assert code == 1


@pytest.mark.parametrize(
    "mode", [{"repos": ["owner/repo"]}, {"org_or_user": "owner"}, {"query": "test"}]
)
@pytest.mark.parametrize("failure", ["auth", "rate", "transient"])
def test_fetch_failures_count_and_cli_exit(session, mode, failure):
    from argparse import Namespace

    from app.services.ingestion.github import _RateLimitError, _TransientError
    from scripts.ingest import _run_github

    error = {
        "auth": ConnectorError("HTTP 401"),
        "rate": _RateLimitError(0),
        "transient": _TransientError("timeout"),
    }[failure]
    connector = GitHubConnector(**mode, max_retries=1, _sleep_fn=lambda _: None)
    with patch("app.services.ingestion.github._make_request", side_effect=error):
        result = IngestionPipeline(session).run(connector)
    assert (result.errors, result.created) == (1, 0)
    # Exercise CLI dispatch with the real connector and no retry sleeps.
    with (
        patch("scripts.ingest._require_db", return_value=session),
        patch("app.services.ingestion.github.GitHubConnector", return_value=connector),
        patch("app.services.ingestion.github._make_request", side_effect=error),
    ):
        assert (
            _run_github(
                Namespace(
                    query=mode.get("query"),
                    repos="owner/repo" if "repos" in mode else None,
                    org=mode.get("org_or_user"),
                    max_pages=1,
                )
            )
            == 1
        )


@pytest.mark.parametrize("mode", [{"org_or_user": "owner"}, {"query": "test"}])
@pytest.mark.parametrize("failure", [ConnectorError("HTTP 401"), _SkipRepo("HTTP 404")])
def test_page_failure_preserves_committed_items(session, mode, failure):
    calls = 0

    def request(url, *args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise failure
        body = [REPO] if "org_or_user" in mode else {"items": [REPO]}
        return body, {"link": '<https://api.github.com/next?page=2>; rel="next"'}

    with patch("app.services.ingestion.github._make_request", side_effect=request):
        result = IngestionPipeline(session).run(
            GitHubConnector(**mode, fetch_readme=False)
        )
    assert (result.created, result.errors, result.total_fetched) == (1, 1, 1)
    assert session.scalars(select(AcademicItem.external_id)).all() == ["1"]
    assert calls == 2


@pytest.mark.parametrize("failure_path", ["repo", "readme"])
def test_per_repo_failure_continues_and_resets_between_runs(session, failure_path):
    def request(url, *args):
        if "/bad/" in url and (failure_path == "repo" or url.endswith("/readme")):
            raise ConnectorError("HTTP 401")
        if url.endswith("/readme"):
            raise _SkipRepo("HTTP 404")
        return {**REPO, "owner": {"login": "bad" if "/bad/" in url else "owner"}}, {}

    connector = GitHubConnector(repos=["bad/repo", "owner/repo"])
    with patch("app.services.ingestion.github._make_request", side_effect=request):
        for expected in ["created", "unchanged"]:
            result = IngestionPipeline(session).run(connector)
            assert result.errors == 1
            assert getattr(result, expected) == 1
    assert session.scalars(select(AcademicItem.external_id)).all() == ["1"]


@pytest.mark.parametrize("status", [404, 451])
def test_inaccessible_repo_is_legitimate_skip(session, status):
    with patch(
        "app.services.ingestion.github._make_request",
        side_effect=_SkipRepo(f"HTTP {status}"),
    ):
        result = IngestionPipeline(session).run(GitHubConnector(repos=["owner/repo"]))
    assert (result.created, result.errors) == (0, 0)


@pytest.mark.parametrize(
    "error",
    [ConnectorError("HTTP 401"), ConnectorError("network"), _SkipRepo("HTTP 451")],
)
def test_org_failure_does_not_fallback_to_user(error):
    with (
        patch(
            "app.services.ingestion.github._make_request", side_effect=error
        ) as request,
        pytest.raises(ConnectorError),
    ):
        list(GitHubConnector(org_or_user="owner").fetch())
    assert request.call_count == 1


@pytest.mark.parametrize("provider", ["github", "openalex"])
def test_hash_excludes_observation_times_and_counters(provider):
    from app.services.ingestion import github, openalex

    module = github if provider == "github" else openalex
    metadata = {
        "readme": "body",
        "language": "en",
        "captured_at": "first",
        "last_seen_at": "first",
    }
    counter = "stargazers_count" if provider == "github" else "cited_by_count"
    metadata[counter] = 1
    before = module._compute_hash("1", provider, "Title", "Text", metadata)
    metadata.update(captured_at="later", last_seen_at="later", **{counter: 2})
    assert module._compute_hash("1", provider, "Title", "Text", metadata) == before
    metadata["language"] = "pt"
    assert module._compute_hash("1", provider, "Title", "Text", metadata) != before


@pytest.mark.parametrize("field", ["html_url", "pushed_at", "default_branch", "topics"])
def test_github_stable_fields_change_hash(field):
    raw = copy.deepcopy(REPO)
    before = _normalise_repo(raw, None, "github", NOW)
    raw[field] = (
        ["changed"]
        if field == "topics"
        else "2026-02-01T00:00:00Z"
        if field == "pushed_at"
        else "changed"
    )
    assert _normalise_repo(raw, None, "github", NOW).content_hash != before.content_hash
