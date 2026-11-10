"""Regression port of the QA team's 20 independent collector scenarios.

Preserves that team's validation as repository tests, not a new independent QA
pass. All HTTP responses use MockTransport; no live requests or credentials
are needed. Only imports, unused imports and formatting were adapted.
"""

import base64
import time
from unittest.mock import patch

import httpx
import pytest

from app.services.ingestion.github import README_MAX_CHARS
from app.services.source_collectors import (
    CollectionState,
    GitHubRepoCollector,
    SourceFailure,
)


RAW = {
    "id": 876543,
    "name": "route",
    "full_name": "qa/route",
    "private": False,
    "visibility": "public",
    "owner": {"login": "qa", "type": "User"},
    "html_url": "https://github.com/qa/route",
    "description": "Directed graph Dijkstra transit routes",
    "topics": ["shortest-path"],
    "language": "Python",
    "created_at": "2020-01-01T00:00:00Z",
    "pushed_at": "2026-10-23T00:00:00Z",
    "updated_at": "2026-10-23T00:00:00Z",
    "stargazers_count": 10,
    "forks_count": 2,
    "default_branch": "main",
}


def readme(text):
    return {
        "encoding": "base64",
        "content": base64.b64encode(text.encode()).decode(),
    }


def collect(
    responses,
    *,
    state=CollectionState(),
    url="https://github.com/qa/route",
    deadline=None,
):
    calls = []

    def handler(request):
        calls.append(request)
        response = responses[len(calls) - 1]
        if isinstance(response, Exception):
            raise response
        status, body, etag = response
        return httpx.Response(
            status, json=body, headers={"ETag": etag} if etag else {}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        value = GitHubRepoCollector(client).collect(
            url,
            state=state,
            deadline=deadline if deadline is not None else time.monotonic() + 5,
        )
    return value, calls


@pytest.fixture
def initial():
    return collect(
        [
            (200, RAW, "repoA"),
            (200, readme("Dijkstra route graph README"), "readmeA"),
        ]
    )[0]


@pytest.mark.parametrize(
    "repo_status,readme_status", [(304, 304), (304, 200), (200, 304)]
)
def test_independent_conditional_requests(initial, repo_status, readme_status):
    state = CollectionState(initial.item, "repoA", "readmeA")
    raw = {**RAW, "description": "Changed repository metadata"}
    value, calls = collect(
        [
            (
                repo_status,
                raw if repo_status == 200 else None,
                "repoB" if repo_status == 200 else None,
            ),
            (
                readme_status,
                readme("Changed Dijkstra README") if readme_status == 200 else None,
                "readmeB" if readme_status == 200 else None,
            ),
        ],
        state=state,
    )
    assert calls[0].url.path == "/repositories/876543"
    assert calls[1].url.path == "/repos/qa/route/readme"
    assert calls[0].headers["If-None-Match"] == "repoA"
    assert calls[1].headers["If-None-Match"] == "readmeA"
    assert value.item.external_id == initial.item.external_id
    assert (value.item.content_hash == initial.item.content_hash) == (
        repo_status == readme_status == 304
    )
    assert value.not_modified == (repo_status == readme_status == 304)
    if repo_status == 304:
        assert value.item.description == initial.item.description
    if readme_status == 304:
        assert value.item.metadata["readme"] == initial.item.metadata["readme"]
    assert value.etag_repo == ("repoB" if repo_status == 200 else "repoA")
    assert value.etag_readme == ("readmeB" if readme_status == 200 else "readmeA")


def test_truncated_readme_does_not_drift_on_repeated_304():
    first, _ = collect(
        [
            (200, RAW, "repoA"),
            (200, readme("á" * (README_MAX_CHARS + 100)), "readmeA"),
        ]
    )
    old = first.item
    assert old.metadata["readme"].endswith("[truncated]")
    for _ in range(3):
        value, _ = collect(
            [(304, None, None), (304, None, None)],
            state=CollectionState(old, "repoA", "readmeA"),
        )
        assert value.item.metadata["readme"] == first.item.metadata["readme"]
        assert value.item.content_hash == first.item.content_hash
        old = value.item


def test_rename_follows_numeric_identity_and_rebuilds_readme_path(initial):
    renamed = {
        **RAW,
        "full_name": "renamed/route-v2",
        "name": "route-v2",
        "owner": {"login": "renamed", "type": "User"},
        "html_url": "https://github.com/renamed/route-v2",
    }
    value, calls = collect(
        [(200, renamed, "repoB"), (304, None, None)],
        state=CollectionState(initial.item, "repoA", "readmeA"),
    )
    assert calls[0].url.path == "/repositories/876543"
    assert calls[1].url.path == "/repos/renamed/route-v2/readme"
    assert value.item.external_id == initial.item.external_id
    assert value.item.original_url == "https://github.com/renamed/route-v2"
    assert value.item.content_hash != initial.item.content_hash
    # Single-monitor behavior belongs to repository/runtime, not this collector.


def test_pushed_at_activity_changes_hash_without_lexical_change(initial):
    changed = {**RAW, "pushed_at": "2026-10-24T00:00:00Z"}
    value, _ = collect(
        [(200, changed, "repoB"), (304, None, None)],
        state=CollectionState(initial.item, "repoA", "readmeA"),
    )
    assert value.item.description == initial.item.description
    assert value.item.metadata["readme"] == initial.item.metadata["readme"]
    assert value.item.title == initial.item.title
    assert value.item.content_hash != initial.item.content_hash


def test_volatile_counter_changes_do_not_change_context_hash(initial):
    value, _ = collect(
        [
            (200, {**RAW, "stargazers_count": 999, "forks_count": 888}, "repoB"),
            (304, None, None),
        ],
        state=CollectionState(initial.item, "repoA", "readmeA"),
    )
    assert value.item.content_hash == initial.item.content_hash


@pytest.mark.parametrize("which", ["repo", "readme"])
def test_304_without_cache_not_accepted(which):
    responses = (
        [(304, None, "repoA")]
        if which == "repo"
        else [(200, RAW, "repoA"), (304, None, "readmeA")]
    )
    with pytest.raises(SourceFailure):
        collect(responses)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_errors_no_redirect_no_retry(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://evil.test/secret", "Retry-After": "10"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceFailure) as exc:
            GitHubRepoCollector(client).collect(
                "https://github.com/qa/route", deadline=time.monotonic() + 5
            )
    assert len(calls) == 1
    assert exc.value.code == "source_unavailable"
    assert str(exc.value) == "source_unavailable"


def test_missing_readme_is_valid_and_removes_old_context(initial):
    value, _ = collect(
        [(304, None, None), (404, None, None)],
        state=CollectionState(initial.item, "repoA", "readmeA"),
    )
    assert "readme" not in value.item.metadata
    assert value.item.content_hash != initial.item.content_hash


@pytest.mark.parametrize("side", ["repo", "readme"])
def test_two_mb_body_limit(side):
    calls = []

    def handler(request):
        calls.append(request)
        if side == "readme" and len(calls) == 1:
            return httpx.Response(200, json=RAW)
        return httpx.Response(200, content=b"x" * 2_000_001)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceFailure) as exc:
            GitHubRepoCollector(client).collect(
                "https://github.com/qa/route", deadline=time.monotonic() + 5
            )
    assert exc.value.code == "source_unavailable"
    assert len(calls) == (1 if side == "repo" else 2)


def test_expired_deadline_no_outbound_request():
    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as client:
        with pytest.raises(SourceFailure) as exc:
            GitHubRepoCollector(client).collect(
                "https://github.com/qa/route", deadline=time.monotonic() - 1
            )
    assert exc.value.code == "timeout"
    assert not calls


def test_deadline_rechecked_while_streaming():
    clock = {"now": 0}
    calls = []

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            clock["now"] = 2
            yield b"{}"

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=SlowStream())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with patch(
            "app.services.source_collectors.time.monotonic",
            side_effect=lambda: clock["now"],
        ):
            with pytest.raises(SourceFailure) as exc:
                GitHubRepoCollector(client).collect(
                    "https://github.com/qa/route", deadline=1
                )
    assert exc.value.code == "timeout"
    assert len(calls) == 1


def test_identity_changed_or_private_rejected(initial):
    for bad in [{**RAW, "id": 111}, {**RAW, "private": True}]:
        with pytest.raises(SourceFailure):
            collect(
                [(200, bad, "new")],
                state=CollectionState(initial.item, "repoA", "readmeA"),
            )
