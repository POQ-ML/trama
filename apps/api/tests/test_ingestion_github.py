"""Unit tests for the GitHub connector.

All tests are deterministic — no network, no real token.
Fixtures based on actual API response shape (verified 2026-10-19).
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.ingestion.github import (
    ConnectorError,
    GitHubConnector,
    _SkipRepo,
    _RateLimitError,
    _TransientError,
    _extract_next_url,
    _normalise_repo,
    _with_retry,
    README_MAX_CHARS,
)
from app.services.ingestion.models import NormalisedItem


# ---------------------------------------------------------------------------
# Fixtures — shaped after real API responses (verified 2026-10-19)
# ---------------------------------------------------------------------------

_CAPTURED = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)

_REPO_FULL = {
    "id": 160919119,
    "name": "fastapi",
    "full_name": "fastapi/fastapi",
    "private": False,
    "owner": {"login": "fastapi", "type": "Organization"},
    "html_url": "https://github.com/fastapi/fastapi",
    "description": "FastAPI framework",
    "topics": ["python", "api", "fastapi"],
    "language": "Python",
    "created_at": "2018-12-08T08:21:47Z",
    "updated_at": "2026-10-19T17:12:33Z",
    "pushed_at": "2026-10-19T17:12:03Z",
    "stargazers_count": 103251,
    "forks_count": 8500,
    "visibility": "public",
    "default_branch": "main",
}

_REPO_MINIMAL = {
    "id": 1,
    "name": "hello",
    "full_name": "octocat/hello",
    "private": False,
    "owner": {"login": "octocat", "type": "User"},
    "html_url": "https://github.com/octocat/hello",
    "description": None,
    "topics": [],
    "language": None,
    "created_at": "2020-01-01T00:00:00Z",
    "updated_at": "2020-01-01T00:00:00Z",
    "pushed_at": None,
    "stargazers_count": 0,
    "forks_count": 0,
    "visibility": "public",
    "default_branch": "main",
}

_REPO_PRIVATE = {**_REPO_FULL, "private": True}
_REPO_NO_ID = {**_REPO_FULL}
_REPO_NO_ID.pop("id")


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


_README_RESPONSE = {
    "name": "README.md",
    "content": _b64("# Hello\nThis is a README."),
    "encoding": "base64",
}

_SEARCH_PAGE_1 = {
    "total_count": 2,
    "incomplete_results": False,
    "items": [_REPO_FULL],
}
_SEARCH_PAGE_2 = {
    "total_count": 2,
    "incomplete_results": False,
    "items": [_REPO_MINIMAL],
}
_SEARCH_EMPTY = {
    "total_count": 0,
    "incomplete_results": False,
    "items": [],
}


# ---------------------------------------------------------------------------
# Link header parsing
# ---------------------------------------------------------------------------

class TestExtractNextUrl:
    def test_returns_next_url(self):
        header = '<https://api.github.com/search?page=2>; rel="next", <https://api.github.com/search?page=1>; rel="first"'
        assert _extract_next_url(header) == "https://api.github.com/search?page=2"

    def test_no_next_returns_none(self):
        header = '<https://api.github.com/search?page=1>; rel="first"'
        assert _extract_next_url(header) is None

    def test_none_returns_none(self):
        assert _extract_next_url(None) is None

    def test_empty_string_returns_none(self):
        assert _extract_next_url("") is None


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

class TestNormaliseRepo:
    def test_full_repo(self):
        item = _normalise_repo(_REPO_FULL, "README content", "github", _CAPTURED)
        assert item is not None
        assert item.external_id == "160919119"
        assert item.item_type == "repository"
        assert item.title == "fastapi/fastapi"
        assert item.description == "FastAPI framework"
        assert item.original_url == "https://github.com/fastapi/fastapi"
        assert item.original_date == datetime(2026, 10, 19, 17, 12, 3, tzinfo=timezone.utc)
        assert item.metadata["topics"] == ["python", "api", "fastapi"]
        assert item.metadata["language"] == "Python"
        assert item.metadata["owner"]["login"] == "fastapi"
        assert item.metadata["readme"] == "README content"
        assert item.captured_at == _CAPTURED
        assert len(item.content_hash) == 64

    def test_private_repo_returns_none(self):
        assert _normalise_repo(_REPO_PRIVATE, None, "github", _CAPTURED) is None

    def test_missing_id_returns_none(self):
        assert _normalise_repo(_REPO_NO_ID, None, "github", _CAPTURED) is None

    def test_null_description_is_none(self):
        item = _normalise_repo(_REPO_MINIMAL, None, "github", _CAPTURED)
        assert item is not None
        assert item.description is None

    def test_readme_absent_not_in_metadata(self):
        item = _normalise_repo(_REPO_FULL, None, "github", _CAPTURED)
        assert "readme" not in item.metadata

    def test_readme_truncation(self):
        long_readme = "x" * (README_MAX_CHARS + 1000)
        item = _normalise_repo(_REPO_FULL, long_readme, "github", _CAPTURED)
        assert item.metadata["readme"].endswith("[truncated]")
        assert len(item.metadata["readme"]) <= README_MAX_CHARS + 20

    def test_pushed_at_used_as_original_date(self):
        item = _normalise_repo(_REPO_FULL, None, "github", _CAPTURED)
        assert item.original_date == datetime(2026, 10, 19, 17, 12, 3, tzinfo=timezone.utc)

    def test_fallback_to_updated_at_when_no_pushed_at(self):
        raw = {**_REPO_MINIMAL}  # pushed_at is None in _REPO_MINIMAL
        item = _normalise_repo(raw, None, "github", _CAPTURED)
        assert item.original_date == datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_content_hash_deterministic(self):
        i1 = _normalise_repo(_REPO_FULL, None, "github", _CAPTURED)
        i2 = _normalise_repo(_REPO_FULL, None, "github", _CAPTURED)
        assert i1.content_hash == i2.content_hash

    def test_content_hash_changes_with_description(self):
        r1 = {**_REPO_FULL, "description": "A"}
        r2 = {**_REPO_FULL, "description": "B"}
        i1 = _normalise_repo(r1, None, "github", _CAPTURED)
        i2 = _normalise_repo(r2, None, "github", _CAPTURED)
        assert i1.content_hash != i2.content_hash

    def test_source_key_in_metadata(self):
        item = _normalise_repo(_REPO_FULL, None, "github", _CAPTURED)
        assert item.metadata["source"] == "github"
        assert item.source_key == "github"


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------

class TestWithRetry:
    def test_skip_repo_propagates_immediately(self):
        calls = [0]
        def fn():
            calls[0] += 1
            raise _SkipRepo("404")
        with pytest.raises(_SkipRepo):
            _with_retry(fn, max_retries=3, sleep_fn=lambda s: None)
        assert calls[0] == 1  # no retry on SkipRepo

    def test_rate_limit_retries(self):
        calls = [0]
        def fn():
            calls[0] += 1
            if calls[0] == 1:
                raise _RateLimitError(0.0)
            return ("ok", {})
        result = _with_retry(fn, max_retries=2, sleep_fn=lambda s: None)
        assert result == ("ok", {})

    def test_transient_gives_up_after_max_retries(self):
        def fn():
            raise _TransientError("boom")
        with pytest.raises(ConnectorError):
            _with_retry(fn, max_retries=2, sleep_fn=lambda s: None)


# ---------------------------------------------------------------------------
# Connector — search mode
# ---------------------------------------------------------------------------

def _make_search_connector(pages, env=None, max_pages=None):
    """Connector wired to return pages in sequence."""
    call_idx = [0]
    link_headers = []
    for i in range(len(pages) - 1):
        link_headers.append(f'<https://api.github.com/search?page={i+2}>; rel="next"')
    link_headers.append(None)  # last page has no next

    def fake_request(url, timeout, token):
        i = call_idx[0]
        call_idx[0] += 1
        page_data = pages[i]
        headers = {}
        if i < len(link_headers) and link_headers[i]:
            headers["link"] = link_headers[i]
        return page_data, headers

    connector = GitHubConnector(
        query="topic:python",
        fetch_readme=False,
        per_page=1,
        max_pages=max_pages,
        _env=env or {},
        _sleep_fn=lambda s: None,
    )
    return connector, fake_request


class TestGitHubConnectorSearch:
    def test_two_pages(self):
        connector, fake_req = _make_search_connector([_SEARCH_PAGE_1, _SEARCH_PAGE_2, _SEARCH_EMPTY])
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())
        assert len(items) == 2
        assert items[0].external_id == "160919119"
        assert items[1].external_id == "1"

    def test_empty_results_yields_nothing(self):
        connector, fake_req = _make_search_connector([_SEARCH_EMPTY])
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())
        assert items == []

    def test_max_pages_limits_fetch(self):
        connector, fake_req = _make_search_connector(
            [_SEARCH_PAGE_1, _SEARCH_PAGE_2], max_pages=1
        )
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())
        assert len(items) == 1

    def test_429_retried(self):
        calls = [0]
        def fake_req(url, timeout, token):
            calls[0] += 1
            if calls[0] == 1:
                raise _RateLimitError(0.0)
            return _SEARCH_EMPTY, {}

        connector = GitHubConnector(
            query="x", fetch_readme=False, _env={}, _sleep_fn=lambda s: None
        )
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            list(connector.fetch())
        assert calls[0] == 2

    def test_404_skipped_not_raised(self):
        calls = [0]
        def fake_req(url, timeout, token):
            calls[0] += 1
            raise _SkipRepo("404")

        # With explicit repos mode, 404 should be skipped
        connector = GitHubConnector(
            repos=["owner/missing"],
            fetch_readme=False,
            _env={},
            _sleep_fn=lambda s: None,
        )
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())
        assert items == []

    def test_private_repo_skipped(self):
        def fake_req(url, timeout, token):
            return _REPO_PRIVATE, {}

        connector = GitHubConnector(
            repos=["fastapi/fastapi"],
            fetch_readme=False,
            _env={},
            _sleep_fn=lambda s: None,
        )
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())
        assert items == []

    def test_readme_fetched_and_decoded(self):
        readme_calls = [0]

        def fake_req(url, timeout, token):
            readme_calls[0] += 1
            if "readme" in url.lower():
                return _README_RESPONSE, {}
            return _REPO_FULL, {}

        connector = GitHubConnector(
            repos=["fastapi/fastapi"],
            fetch_readme=True,
            _env={},
            _sleep_fn=lambda s: None,
        )
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())

        assert len(items) == 1
        assert "Hello" in items[0].metadata["readme"]

    def test_readme_404_does_not_abort(self):
        def fake_req(url, timeout, token):
            if "readme" in url.lower():
                raise _SkipRepo("404")
            return _REPO_FULL, {}

        connector = GitHubConnector(
            repos=["fastapi/fastapi"],
            fetch_readme=True,
            _env={},
            _sleep_fn=lambda s: None,
        )
        with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
            items = list(connector.fetch())

        assert len(items) == 1
        assert "readme" not in items[0].metadata

    def test_no_token_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="trama.ingestion.github"):
            GitHubConnector(query="x", _env={})
        assert "GITHUB_TOKEN" in caplog.text

    def test_token_not_in_logs_or_errors(self, caplog):
        """Token must never appear in log output."""
        import logging
        fake_token = "ghp_SYNTHETIC_TEST_TOKEN_NOT_REAL_00000"
        calls = [0]

        def fake_req(url, timeout, token):
            calls[0] += 1
            raise _TransientError("boom")

        connector = GitHubConnector(
            query="x",
            fetch_readme=False,
            max_retries=0,
            _env={"GITHUB_TOKEN": fake_token},
            _sleep_fn=lambda s: None,
        )
        with caplog.at_level(logging.DEBUG, logger="trama.ingestion.github"):
            with patch("app.services.ingestion.github._make_request", side_effect=fake_req):
                try:
                    list(connector.fetch())
                except ConnectorError:
                    pass

        assert fake_token not in caplog.text

    def test_no_mode_raises_connector_error(self):
        connector = GitHubConnector(_env={})
        with pytest.raises(ConnectorError, match="requires one of"):
            list(connector.fetch())
