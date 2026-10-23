"""Public DTO and trust-boundary tests, without network or database."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.discovery import (
    ArticleRead,
    DiscoveryCreate,
    DiscoveryPage,
    DiscoveryQuery,
    FeedbackUpdate,
    RunRead,
    RunStatus,
    RunUpdate,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://evil.test/a/b",
        "https://github.com/a/b?token=secret",
        "https://github.com/a/b#x",
        "https://u:p@github.com/a/b",
        "https://github.com/a/..",
        "https://github.com/a/b/tree/main",
    ],
)
def test_repo_rejects_noncanonical_urls(url):
    with pytest.raises(ValidationError):
        DiscoveryCreate(repo_url=url)


def test_create_has_only_repo_url():
    assert (
        DiscoveryCreate(repo_url="https://github.com/a/b/").repo_url
        == "https://github.com/a/b"
    )
    with pytest.raises(ValidationError):
        DiscoveryCreate(
            repo_url="https://github.com/a/b", deadline_at=datetime.now(timezone.utc)
        )


@pytest.mark.parametrize("limit", [0, 51, True, "20"])
def test_page_bounds(limit):
    with pytest.raises(ValidationError):
        DiscoveryQuery(limit=limit)


def test_cursor_and_default_query():
    assert DiscoveryQuery().limit == 20
    assert DiscoveryQuery().cursor is None
    with pytest.raises(ValidationError):
        DiscoveryQuery(cursor="not-a-uuid")


@pytest.mark.parametrize("status", ["pending", "silenced", "running"])
def test_feedback_is_only_a_human_decision(status):
    with pytest.raises(ValidationError):
        FeedbackUpdate(status=status)


def test_specific_entity_types_and_output_state():
    article = dict(
        id=uuid4(),
        entity_type="article",
        origin_item_id=uuid4(),
        label="Title",
        external_id="W1",
        original_url=None,
    )
    assert ArticleRead(**article).original_url is None
    with pytest.raises(ValidationError):
        ArticleRead(**{**article, "entity_type": "project"})
    now = datetime.now(timezone.utc)
    values = dict(
        id=uuid4(),
        repo_url="https://github.com/a/b",
        project=None,
        status="queued",
        created_at=now,
        started_at=None,
        finished_at=None,
        deadline_at=now + timedelta(minutes=5),
        error_code=None,
    )
    run = RunRead(**values)
    assert run.model_dump(mode="json")["status"] == "queued"
    for invalid in [
        dict(status="completed"),
        dict(error_code="timeout"),
        dict(started_at=now),
        dict(deadline_at=now),
    ]:
        with pytest.raises(ValidationError):
            RunRead(**{**values, **invalid})
    with pytest.raises(ValidationError):
        DiscoveryPage(
            run=run, suggestions=[], total_suggestions=-1, limit=20, next_cursor=None
        )
    with pytest.raises(ValidationError):
        RunUpdate(status="failed", error_code="provider payload secret")
    assert {s.value for s in RunStatus} == {
        "queued",
        "running",
        "completed",
        "partial",
        "failed",
    }
