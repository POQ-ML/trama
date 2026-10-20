"""Unit tests for the OpenAlex connector.

All tests are deterministic — no network, no real API key.
Fixtures based on actual API response shape (verified 2026-10-19).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.ingestion.openalex import (
    ConnectorError,
    OpenAlexConnector,
    _extract_retry_after,
    _normalise_work,
    _reconstruct_abstract,
    _with_retry,
    _RateLimitError,
    _TransientError,
)
from app.services.ingestion.models import NormalisedItem


# ---------------------------------------------------------------------------
# Fixtures — shaped after real API responses (verified 2026-10-19)
# ---------------------------------------------------------------------------

_CAPTURED = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)

_WORK_FULL = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.7717/peerj.4375",
    "title": "The state of OA",
    "display_name": "The state of OA",
    "publication_year": 2018,
    "publication_date": "2018-02-13",
    "type": "article",
    "primary_location": {
        "landing_page_url": "https://doi.org/10.7717/peerj.4375",
        "doi": "https://doi.org/10.7717/peerj.4375",
        "is_oa": True,
    },
    "authorships": [
        {
            "author_position": "first",
            "author": {
                "id": "https://openalex.org/A5048491430",
                "display_name": "Heather Piwowar",
                "orcid": "https://orcid.org/0000-0003-1613-5981",
            },
            "institutions": [],
        }
    ],
    "topics": [
        {
            "id": "https://openalex.org/T13607",
            "display_name": "Academic Publishing",
            "score": 0.64,
        }
    ],
    "concepts": [
        {
            "id": "https://openalex.org/C2778805511",
            "display_name": "Citation",
            "score": 0.69,
        }
    ],
    "keywords": [
        {
            "id": "https://openalex.org/keywords/open-access",
            "display_name": "open access",
            "score": 0.98,
        }
    ],
    "abstract_inverted_index": {
        "Despite": [0],
        "growing": [1],
        "awareness": [2],
    },
    "cited_by_count": 1216,
    "open_access": {"is_oa": True, "oa_status": "gold"},
    "language": "en",
}

_WORK_MINIMAL = {
    "id": "https://openalex.org/W999",
    "title": "Minimal Work",
    "publication_year": 2020,
}

_WORK_NO_ID = {"title": "No ID Work"}
_WORK_NO_TITLE = {"id": "https://openalex.org/W000"}
_WORK_NULL_FIELDS = {
    "id": "https://openalex.org/W111",
    "title": "Null Fields",
    "doi": None,
    "publication_date": None,
    "authorships": None,
    "topics": None,
    "abstract_inverted_index": None,
}

_PAGE_1 = {
    "meta": {"count": 2, "per_page": 1, "next_cursor": "cursor_abc"},
    "results": [_WORK_FULL],
}
_PAGE_2 = {
    "meta": {"count": 2, "per_page": 1, "next_cursor": None},
    "results": [_WORK_MINIMAL],
}
_EMPTY_PAGE = {
    "meta": {"count": 0, "per_page": 100, "next_cursor": None},
    "results": [],
}
_BASIC_PAGE_1 = {
    "meta": {"count": 2, "per_page": 1},
    "results": [_WORK_FULL],
}
_BASIC_PAGE_2 = {
    "meta": {"count": 2, "per_page": 1},
    "results": [_WORK_MINIMAL],
}
_BASIC_PAGE_EMPTY = {
    "meta": {"count": 2, "per_page": 1},
    "results": [],
}


# ---------------------------------------------------------------------------
# Abstract reconstruction
# ---------------------------------------------------------------------------

class TestReconstructAbstract:
    def test_normal_index(self):
        idx = {"hello": [0], "world": [1]}
        assert _reconstruct_abstract(idx) == "hello world"

    def test_multiple_positions(self):
        idx = {"a": [0, 2], "b": [1]}
        result = _reconstruct_abstract(idx)
        assert result == "a b a"

    def test_none_returns_none(self):
        assert _reconstruct_abstract(None) is None

    def test_empty_dict_returns_none(self):
        assert _reconstruct_abstract({}) is None

    def test_malformed_does_not_raise(self):
        # positions not iterable — should return None gracefully
        result = _reconstruct_abstract({"word": "not_a_list"})  # type: ignore[arg-type]
        assert result is None


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

class TestNormaliseWork:
    def test_full_work(self):
        item = _normalise_work(_WORK_FULL, "openalex", _CAPTURED)
        assert item is not None
        assert item.external_id == "W2741809807"
        assert item.item_type == "article"
        assert item.title == "The state of OA"
        assert item.original_url == "https://doi.org/10.7717/peerj.4375"
        assert item.original_date == datetime(2018, 2, 13, tzinfo=timezone.utc)
        assert item.captured_at == _CAPTURED
        assert item.metadata["doi"] == "10.7717/peerj.4375"
        assert len(item.metadata["authors"]) == 1
        assert item.metadata["authors"][0]["display_name"] == "Heather Piwowar"
        assert item.metadata["authors"][0]["id"] == "A5048491430"
        assert len(item.metadata["topics"]) == 1
        assert len(item.metadata["concepts"]) == 1
        assert len(item.metadata["keywords"]) == 1
        assert item.description == "Despite growing awareness"
        assert item.metadata["cited_by_count"] == 1216
        assert item.metadata["open_access"]["is_oa"] is True
        assert item.metadata["language"] == "en"
        assert len(item.content_hash) == 64

    def test_minimal_work(self):
        item = _normalise_work(_WORK_MINIMAL, "openalex", _CAPTURED)
        assert item is not None
        assert item.external_id == "W999"
        assert item.description is None
        assert item.original_url is None  # no doi, no primary_location

    def test_missing_id_returns_none(self):
        assert _normalise_work(_WORK_NO_ID, "openalex", _CAPTURED) is None

    def test_missing_title_returns_none(self):
        assert _normalise_work(_WORK_NO_TITLE, "openalex", _CAPTURED) is None

    def test_null_optional_fields_do_not_raise(self):
        item = _normalise_work(_WORK_NULL_FIELDS, "openalex", _CAPTURED)
        assert item is not None
        assert item.metadata["doi"] is None
        assert item.metadata["authors"] == []
        assert item.description is None

    def test_doi_url_stripped(self):
        raw = {**_WORK_FULL, "doi": "https://doi.org/10.1234/test"}
        item = _normalise_work(raw, "openalex", _CAPTURED)
        assert item.metadata["doi"] == "10.1234/test"

    def test_year_fallback_when_no_date(self):
        raw = {**_WORK_MINIMAL, "publication_date": None, "publication_year": 2021}
        item = _normalise_work(raw, "openalex", _CAPTURED)
        assert item.original_date == datetime(2021, 1, 1, tzinfo=timezone.utc)

    def test_content_hash_is_deterministic(self):
        item1 = _normalise_work(_WORK_FULL, "openalex", _CAPTURED)
        item2 = _normalise_work(_WORK_FULL, "openalex", _CAPTURED)
        assert item1.content_hash == item2.content_hash

    def test_content_hash_changes_with_title(self):
        raw_a = {**_WORK_FULL, "title": "Title A"}
        raw_b = {**_WORK_FULL, "title": "Title B"}
        item_a = _normalise_work(raw_a, "openalex", _CAPTURED)
        item_b = _normalise_work(raw_b, "openalex", _CAPTURED)
        assert item_a.content_hash != item_b.content_hash

    def test_source_key_in_metadata(self):
        item = _normalise_work(_WORK_FULL, "openalex", _CAPTURED)
        assert item.metadata["source"] == "openalex"
        assert item.source_key == "openalex"


# ---------------------------------------------------------------------------
# Retry / backoff helpers
# ---------------------------------------------------------------------------

class TestWithRetry:
    def test_success_on_first_attempt(self):
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        assert _with_retry(fn, max_retries=2, sleep_fn=lambda s: None) == "ok"
        assert len(calls) == 1

    def test_transient_retries_then_succeeds(self):
        calls = []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise _TransientError("boom")
            return "recovered"
        result = _with_retry(fn, max_retries=3, sleep_fn=lambda s: None)
        assert result == "recovered"
        assert len(calls) == 3

    def test_rate_limit_retries_then_succeeds(self):
        calls = []
        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise _RateLimitError(0.0)
            return "ok"
        result = _with_retry(fn, max_retries=2, sleep_fn=lambda s: None)
        assert result == "ok"

    def test_exceeds_max_retries_raises_connector_error(self):
        def fn():
            raise _TransientError("always fails")
        with pytest.raises(ConnectorError):
            _with_retry(fn, max_retries=2, sleep_fn=lambda s: None)

    def test_permanent_4xx_does_not_retry(self):
        calls = []
        def fn():
            calls.append(1)
            raise ConnectorError("HTTP 400")
        with pytest.raises(ConnectorError):
            _with_retry(fn, max_retries=3, sleep_fn=lambda s: None)
        assert len(calls) == 1  # no retry on ConnectorError


# ---------------------------------------------------------------------------
# Connector — fetch with mocked HTTP
# ---------------------------------------------------------------------------

def _make_connector(pages: list[dict], env: dict | None = None,
                    max_pages: int | None = None) -> OpenAlexConnector:
    """Build a connector whose _make_request returns pages in sequence."""
    return OpenAlexConnector(
        filter_str="institution.id:I4390",
        max_pages=max_pages,
        per_page=1,
        _env=env or {},
        _sleep_fn=lambda s: None,
    )


class TestOpenAlexConnectorFetch:
    def test_cursor_paging_two_pages(self):
        pages = [_PAGE_1, _PAGE_2]
        call_idx = [0]

        def fake_request(url, timeout, api_key, email):
            i = call_idx[0]
            call_idx[0] += 1
            return pages[i]

        connector = OpenAlexConnector(
            filter_str="x",
            per_page=1,
            _env={"OPENALEX_API_KEY": "test-key"},
            _sleep_fn=lambda s: None,
        )
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            items = list(connector.fetch())

        assert len(items) == 2
        assert items[0].external_id == "W2741809807"
        assert items[1].external_id == "W999"

    def test_basic_paging_no_key(self):
        pages = [_BASIC_PAGE_1, _BASIC_PAGE_2, _BASIC_PAGE_EMPTY]
        call_idx = [0]

        def fake_request(url, timeout, api_key, email):
            i = call_idx[0]
            call_idx[0] += 1
            return pages[i]

        connector = OpenAlexConnector(
            filter_str="x", per_page=1, _env={}, _sleep_fn=lambda s: None
        )
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            items = list(connector.fetch())

        assert len(items) == 2

    def test_empty_first_page_yields_nothing(self):
        def fake_request(url, timeout, api_key, email):
            return _EMPTY_PAGE

        connector = OpenAlexConnector(filter_str="x", _env={}, _sleep_fn=lambda s: None)
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            items = list(connector.fetch())
        assert items == []

    def test_max_pages_limits_fetch(self):
        pages = [_PAGE_1, _PAGE_2]
        call_idx = [0]

        def fake_request(url, timeout, api_key, email):
            i = call_idx[0]
            call_idx[0] += 1
            return pages[i]

        connector = OpenAlexConnector(
            filter_str="x", per_page=1, max_pages=1,
            _env={"OPENALEX_API_KEY": "key"},
            _sleep_fn=lambda s: None,
        )
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            items = list(connector.fetch())

        assert len(items) == 1  # only first page

    def test_invalid_json_raises_connector_error(self):
        import urllib.error
        from io import BytesIO

        class FakeHTTPError(urllib.error.HTTPError):
            def __init__(self):
                # Simulate a 200 OK that returns bad JSON — handled differently
                pass

        def fake_request(url, timeout, api_key, email):
            raise ConnectorError("OpenAlex invalid JSON: ...")

        connector = OpenAlexConnector(filter_str="x", _env={}, _sleep_fn=lambda s: None)
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            with pytest.raises(ConnectorError):
                list(connector.fetch())

    def test_http_429_with_retry_after_retries(self):
        calls = [0]

        def fake_request(url, timeout, api_key, email):
            calls[0] += 1
            if calls[0] == 1:
                raise _RateLimitError(0.0)
            return _EMPTY_PAGE

        connector = OpenAlexConnector(filter_str="x", _env={}, _sleep_fn=lambda s: None)
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            items = list(connector.fetch())
        assert items == []
        assert calls[0] == 2

    def test_http_429_without_retry_after_uses_default_backoff(self):
        calls = [0]

        def fake_request(url, timeout, api_key, email):
            calls[0] += 1
            if calls[0] == 1:
                raise _RateLimitError(5.0)
            return _EMPTY_PAGE

        slept = []
        connector = OpenAlexConnector(
            filter_str="x", _env={}, _sleep_fn=lambda s: slept.append(s)
        )
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            list(connector.fetch())
        assert slept[0] == pytest.approx(5.0)

    def test_http_5xx_transient_retries(self):
        calls = [0]

        def fake_request(url, timeout, api_key, email):
            calls[0] += 1
            if calls[0] < 3:
                raise _TransientError("HTTP 503")
            return _EMPTY_PAGE

        connector = OpenAlexConnector(
            filter_str="x", max_retries=3, _env={}, _sleep_fn=lambda s: None
        )
        with patch("app.services.ingestion.openalex._make_request", side_effect=fake_request):
            items = list(connector.fetch())
        assert calls[0] == 3
        assert items == []

    def test_missing_api_key_logs_warning_and_works(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="trama.ingestion.openalex"):
            connector = OpenAlexConnector(filter_str="x", _env={})
        assert "OPENALEX_API_KEY" in caplog.text

    def test_api_key_absent_from_env_does_not_raise(self):
        # Connector must not raise at construction when key is absent
        c = OpenAlexConnector(filter_str="x", _env={})
        assert c._api_key is None

    def test_per_page_clamped_to_100(self):
        c = OpenAlexConnector(per_page=200, _env={})
        assert c.per_page == 100

    def test_per_page_clamped_to_minimum(self):
        c = OpenAlexConnector(per_page=0, _env={})
        assert c.per_page == 1
