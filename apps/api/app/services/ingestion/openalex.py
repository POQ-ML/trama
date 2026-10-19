"""OpenAlex connector — fetches and normalises Works from the OpenAlex API.

API reference (verified 2026-10-19):
  https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
  https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/paging

Rate limits (verified 2026-10-19):
  - No key  : 10 req/s, basic paging only (cursor beyond page 1 needs a key)
  - Free key: 30 req/s, cursor paging enabled, $1/day budget
  Identification: api_key query param OR Authorization: Bearer header.
  "Polite pool" (mailto): add ?mailto=you@example.com to be contacted on abuse.

Paging strategy (verified against live API 2026-10-19):
  - cursor=* for first page; follow next_cursor until None / empty results
  - per_page=100 (verified maximum)
  - Basic paging used as fallback when no key is present (≤10 000 results)

Retry / rate-limit policy:
  - 429 with Retry-After: honour the header (capped at MAX_RETRY_AFTER_SECONDS)
  - 429 without Retry-After: exponential backoff starting at 1s
  - 5xx transient: exponential backoff, up to MAX_RETRIES attempts
  - 4xx (non-429): permanent error — do not retry
  - Timeout / connection error: exponential backoff, up to MAX_RETRIES attempts
  - Max retries exceeded: raise ConnectorError (logged by pipeline)

Abstract reconstruction (verified against live API, 2026-10-19):
  The `abstract_inverted_index` field is a dict {word: [position, ...]}.
  We reconstruct plain-text by sorting words by their first position and
  joining with spaces.  If absent or None, `description` is set to None.

Security:
  - API key read exclusively from OPENALEX_API_KEY env var.
  - Contact email read from OPENALEX_EMAIL env var.
  - Neither value is logged, raised in exceptions, or stored in metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterator

from app.services.ingestion.models import NormalisedItem

logger = logging.getLogger("trama.ingestion.openalex")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_BASE_URL = "https://api.openalex.org"
_DEFAULT_PER_PAGE = 100
_DEFAULT_TIMEOUT = 30
_MAX_RETRIES = 3
_MAX_RETRY_AFTER_SECONDS = 60
_BACKOFF_BASE = 1.0
_BACKOFF_CAP = 16.0


class ConnectorError(Exception):
    """Non-retryable connector error. Message is safe to log."""


class _RateLimitError(Exception):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after


class _TransientError(Exception):
    pass


# ------------------------------------------------------------------
# Abstract reconstruction
# ------------------------------------------------------------------

def _reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Reconstruct plain-text abstract from OpenAlex inverted index.

    Verified format (2026-10-19): {word: [pos0, pos1, ...], ...}
    Returns None if absent, empty, or malformed.
    """
    if not inverted_index:
        return None
    try:
        position_word: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word.append((int(pos), str(word)))
        if not position_word:
            return None
        position_word.sort(key=lambda x: x[0])
        return " ".join(w for _, w in position_word)
    except Exception:
        logger.warning("Failed to reconstruct abstract from inverted index; skipping")
        return None


# ------------------------------------------------------------------
# Content hash
# ------------------------------------------------------------------

def _compute_hash(external_id: str, source_key: str, title: str,
                  description: str | None, metadata: dict) -> str:
    """SHA-256 of stable content fields. Change → new hash → triggers update."""
    payload = json.dumps(
        {
            "external_id": external_id,
            "source_key": source_key,
            "title": title,
            "description": description,
            "authors": metadata.get("authors"),
            "topics": metadata.get("topics"),
            "doi": metadata.get("doi"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ------------------------------------------------------------------
# Normalisation
# ------------------------------------------------------------------

def _normalise_work(raw: dict[str, Any], source_key: str,
                    captured_at: datetime) -> NormalisedItem | None:
    """Normalise one OpenAlex Work dict → NormalisedItem.

    Returns None if record lacks external_id or title (logged, not raised).
    All absent optional fields set to None — never fabricated.
    """
    raw_id: str | None = raw.get("id")
    if not raw_id:
        logger.warning("OpenAlex Work missing 'id'; skipping")
        return None
    external_id = raw_id.rsplit("/", 1)[-1]  # strip URL prefix → 'W2741809807'

    title: str = (raw.get("title") or raw.get("display_name") or "").strip()
    if not title:
        logger.warning("OpenAlex Work %s missing title; skipping", external_id)
        return None

    # DOI: normalise to '10.xxxx/yyy'
    doi_raw: str | None = raw.get("doi")
    doi: str | None = None
    if doi_raw:
        doi = doi_raw.replace("https://doi.org/", "").strip()

    # original_url
    original_url: str | None = None
    primary_loc = raw.get("primary_location")
    if isinstance(primary_loc, dict):
        original_url = primary_loc.get("landing_page_url") or primary_loc.get("doi")
    if not original_url and doi:
        original_url = f"https://doi.org/{doi}"

    # original_date
    original_date: datetime | None = None
    pub_date: str | None = raw.get("publication_date")
    if pub_date:
        try:
            original_date = datetime.fromisoformat(pub_date).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    if original_date is None:
        year = raw.get("publication_year")
        if year:
            try:
                original_date = datetime(int(year), 1, 1, tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

    # Authors
    authors: list[dict] = []
    for authorship in (raw.get("authorships") or []):
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        if not isinstance(author, dict):
            continue
        aid = (author.get("id") or "").rsplit("/", 1)[-1] or None
        authors.append({
            "id": aid,
            "display_name": author.get("display_name"),
            "orcid": author.get("orcid"),
        })

    # Topics (verified field as of 2026-10-19)
    topics: list[dict] = []
    for t in (raw.get("topics") or []):
        if isinstance(t, dict):
            topics.append({
                "id": (t.get("id") or "").rsplit("/", 1)[-1] or None,
                "display_name": t.get("display_name"),
                "score": t.get("score"),
            })

    # Concepts (legacy, still returned as of 2026-10-19)
    concepts: list[dict] = []
    for c in (raw.get("concepts") or []):
        if isinstance(c, dict):
            concepts.append({
                "id": (c.get("id") or "").rsplit("/", 1)[-1] or None,
                "display_name": c.get("display_name"),
                "score": c.get("score"),
            })

    # Keywords
    keywords: list[dict] = []
    for k in (raw.get("keywords") or []):
        if isinstance(k, dict):
            keywords.append({
                "id": (k.get("id") or "").rsplit("/", 1)[-1] or None,
                "display_name": k.get("display_name"),
                "score": k.get("score"),
            })

    description = _reconstruct_abstract(raw.get("abstract_inverted_index"))

    open_access = raw.get("open_access")
    if not isinstance(open_access, dict):
        open_access = None

    metadata: dict[str, Any] = {
        "doi": doi,
        "authors": authors,
        "topics": topics,
        "concepts": concepts,
        "keywords": keywords,
        "work_type": raw.get("type"),
        "cited_by_count": raw.get("cited_by_count"),
        "open_access": open_access,
        "publication_year": raw.get("publication_year"),
        "language": raw.get("language"),
        "source": "openalex",
        "openalex_url": raw_id,
        "captured_at": captured_at.isoformat(),
    }

    content_hash = _compute_hash(external_id, source_key, title, description, metadata)

    return NormalisedItem(
        external_id=external_id,
        item_type="article",
        title=title,
        source_key=source_key,
        content_hash=content_hash,
        description=description,
        original_url=original_url,
        original_date=original_date,
        metadata=metadata,
        captured_at=captured_at,
    )


# ------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------

def _make_request(url: str, timeout: int, api_key: str | None,
                  email: str | None) -> dict[str, Any]:
    """GET url, inject credentials, return parsed JSON.

    Raises:
        _RateLimitError  — HTTP 429
        _TransientError  — HTTP 5xx, timeout, connection error
        ConnectorError   — HTTP 4xx (non-429), bad JSON, unexpected schema
    """
    parsed = urllib.parse.urlparse(url)
    params = dict(urllib.parse.parse_qsl(parsed.query))

    if api_key:
        params["api_key"] = api_key
    elif email:
        params["mailto"] = email

    final_url = urllib.parse.urlunparse(
        parsed._replace(query=urllib.parse.urlencode(params))
    )

    req = urllib.request.Request(
        final_url,
        headers={"User-Agent": "trama-ingestion/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            retry_after = _extract_retry_after(exc.headers)
            raise _RateLimitError(retry_after)
        if 500 <= exc.code < 600:
            raise _TransientError(f"HTTP {exc.code}")
        raise ConnectorError(f"OpenAlex HTTP {exc.code}")
    except TimeoutError:
        raise _TransientError("timeout")
    except OSError as exc:
        raise _TransientError(f"connection error: {type(exc).__name__}")

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"OpenAlex invalid JSON: {exc}") from exc


def _extract_retry_after(headers) -> float:
    try:
        val = (headers.get("Retry-After") or headers.get("retry-after") or "").strip()
        if val:
            return min(float(val), float(_MAX_RETRY_AFTER_SECONDS))
    except (ValueError, TypeError, AttributeError):
        pass
    return 5.0


def _with_retry(fn, max_retries: int, sleep_fn=time.sleep) -> Any:
    """Run fn with exponential backoff on transient / rate-limit errors."""
    backoff = _BACKOFF_BASE
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except _RateLimitError as exc:
            if attempt >= max_retries:
                raise ConnectorError(
                    f"OpenAlex rate limit exceeded after {attempt + 1} attempts"
                ) from exc
            wait = min(exc.retry_after, _MAX_RETRY_AFTER_SECONDS)
            logger.warning("OpenAlex 429 — waiting %.1fs (retry %d/%d)",
                           wait, attempt + 1, max_retries)
            sleep_fn(wait)
        except _TransientError as exc:
            if attempt >= max_retries:
                raise ConnectorError(
                    f"OpenAlex transient error after {attempt + 1} attempts: {exc}"
                ) from exc
            wait = min(backoff, _BACKOFF_CAP)
            logger.warning("OpenAlex transient (%s) — waiting %.1fs (retry %d/%d)",
                           exc, wait, attempt + 1, max_retries)
            sleep_fn(wait)
            backoff = min(backoff * 2, _BACKOFF_CAP)
    raise ConnectorError("OpenAlex: unreachable retry loop exit")  # pragma: no cover


# ------------------------------------------------------------------
# Connector
# ------------------------------------------------------------------

class OpenAlexConnector:
    """Fetches Works from the OpenAlex API and yields NormalisedItems.

    Configuration via environment (read at construction time):
        OPENALEX_API_KEY  — optional; enables cursor paging past page 1
        OPENALEX_EMAIL    — optional; polite-pool identification

    Neither value is logged, stored in a public attribute, or included
    in any exception message or repr.

    Args:
        filter_str:  OpenAlex filter expression (e.g. 'institution.id:I4210')
        query:       free-text search (mutually exclusive with cursor paging)
        per_page:    1–100, default 100
        max_pages:   stop after N pages (None = no limit)
        timeout:     HTTP timeout in seconds
        max_retries: retry attempts on transient / rate-limit errors
        source_key:  value written to NormalisedItem.source_key
        _env:        env dict override (tests only — never in production)
        _sleep_fn:   sleep override (tests only)
    """

    SOURCE_KEY = "openalex"

    def __init__(
        self,
        filter_str: str | None = None,
        query: str | None = None,
        per_page: int = _DEFAULT_PER_PAGE,
        max_pages: int | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
        source_key: str = SOURCE_KEY,
        _env: dict | None = None,
        _sleep_fn=time.sleep,
    ) -> None:
        env = _env if _env is not None else os.environ
        self._api_key: str | None = env.get("OPENALEX_API_KEY") or None
        self._email: str | None = env.get("OPENALEX_EMAIL") or None

        if not self._api_key:
            logger.info(
                "OPENALEX_API_KEY not set — no key mode "
                "(10 req/s, basic paging only, ≤10 000 results). "
                "Set OPENALEX_API_KEY for cursor paging."
            )
        if not self._email and not self._api_key:
            logger.info(
                "OPENALEX_EMAIL not set — not in polite pool. "
                "Set OPENALEX_EMAIL for identification."
            )

        self.filter_str = filter_str
        self.query = query
        self.per_page = min(max(1, per_page), 100)
        self.max_pages = max_pages
        self.timeout = timeout
        self.max_retries = max_retries
        self.source_key = source_key
        self._sleep_fn = _sleep_fn

    # ------------------------------------------------------------------ #

    def fetch(self) -> Iterator[NormalisedItem]:
        """Yield NormalisedItems for all matching Works.

        Uses cursor paging when OPENALEX_API_KEY is set; otherwise basic paging
        (limited to 10 000 results per the API docs).
        ConnectorError raised on unrecoverable page-level failure.
        """
        if self._api_key:
            yield from self._fetch_cursor()
        else:
            yield from self._fetch_basic()

    # ------------------------------------------------------------------ #

    def _fetch_cursor(self) -> Iterator[NormalisedItem]:
        cursor = "*"
        page_num = 0

        while True:
            if self.max_pages is not None and page_num >= self.max_pages:
                logger.info("OpenAlex: max_pages=%d reached, stopping", self.max_pages)
                break

            url = self._build_url({"cursor": cursor})
            captured_at = datetime.now(timezone.utc)

            data = _with_retry(
                lambda u=url: _make_request(u, self.timeout, self._api_key, self._email),
                self.max_retries,
                self._sleep_fn,
            )

            results = data.get("results")
            if not isinstance(results, list) or not results:
                logger.info("OpenAlex cursor: empty results on page %d, done", page_num + 1)
                break

            page_num += 1
            logger.info("OpenAlex cursor page %d: %d results", page_num, len(results))

            for raw in results:
                item = _normalise_work(raw, self.source_key, captured_at)
                if item is not None:
                    yield item

            meta = data.get("meta") or {}
            next_cursor = meta.get("next_cursor")
            if not next_cursor:
                logger.info("OpenAlex cursor: done after %d pages", page_num)
                break
            cursor = next_cursor

    def _fetch_basic(self) -> Iterator[NormalisedItem]:
        page = 1

        while True:
            if self.max_pages is not None and page > self.max_pages:
                logger.info("OpenAlex basic: max_pages=%d reached, stopping", self.max_pages)
                break

            url = self._build_url({"page": str(page)})
            captured_at = datetime.now(timezone.utc)

            data = _with_retry(
                lambda u=url: _make_request(u, self.timeout, self._api_key, self._email),
                self.max_retries,
                self._sleep_fn,
            )

            results = data.get("results")
            if not isinstance(results, list) or not results:
                logger.info("OpenAlex basic: empty results on page %d, done", page)
                break

            logger.info("OpenAlex basic page %d: %d results", page, len(results))

            for raw in results:
                item = _normalise_work(raw, self.source_key, captured_at)
                if item is not None:
                    yield item

            page += 1

    def _build_url(self, extra: dict[str, str]) -> str:
        params: dict[str, str] = {"per_page": str(self.per_page)}
        if self.filter_str:
            params["filter"] = self.filter_str
        if self.query:
            params["search"] = self.query
        params.update(extra)
        return f"{_BASE_URL}/works?{urllib.parse.urlencode(params)}"
