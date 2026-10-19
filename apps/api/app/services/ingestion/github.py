"""GitHub connector — fetches and normalises repositories from the GitHub API.

API reference (verified 2026-10-19):
  https://docs.github.com/en/rest/search/search#search-repositories
  https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
  https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api

Rate limits (verified 2026-10-19):
  - Unauthenticated : 60 req/h (core), 10 req/min (search)
  - Authenticated   : 5 000 req/h (core), 30 req/min (search)
  X-RateLimit-{Limit,Remaining,Reset} headers present on every response.

Pagination (verified 2026-10-19):
  Link header with rel="next" URL; per_page=100 (max).

Retry / rate-limit policy:
  - 429 or 403 with Retry-After: honour header (capped)
  - 403 without Retry-After: secondary rate limit — backoff and retry
  - 5xx: exponential backoff
  - 404 / 451 (repo inaccessible): skip, log warning, do NOT retry
  - Timeout / connection: exponential backoff

Security:
  - GITHUB_TOKEN read exclusively from env var — never logged, never in
    exceptions, never in repr, never in metadata.
  - Only public repositories collected by default.
    If a repo returns private=True it is skipped with a warning.
  - README content truncated at README_MAX_CHARS to avoid huge payloads.

API version header: 'X-GitHub-Api-Version: 2022-11-28' (verified 2026-10-19
  as the stable version per GitHub docs).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterator

from app.services.ingestion.models import NormalisedItem

logger = logging.getLogger("trama.ingestion.github")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_API_BASE = "https://api.github.com"
_API_VERSION = "2022-11-28"       # verified header value
_DEFAULT_PER_PAGE = 100
_DEFAULT_TIMEOUT = 30
_MAX_RETRIES = 3
_MAX_RETRY_AFTER_SECONDS = 60
_BACKOFF_BASE = 1.0
_BACKOFF_CAP = 16.0
README_MAX_CHARS = 50_000         # truncate excessively large READMEs


class ConnectorError(Exception):
    """Non-retryable connector error. Message is safe to log."""


class _SkipRepo(Exception):
    """Raised when a single repo should be skipped (404/403/451/private)."""


class _RateLimitError(Exception):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after


class _TransientError(Exception):
    pass


# ------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------

def _build_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": "trama-ingestion/1.0",
    }
    if token:
        # Token value never stored in a loggable attribute
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_retry_after(headers) -> float:
    try:
        val = (headers.get("Retry-After") or headers.get("retry-after") or "").strip()
        if val:
            return min(float(val), float(_MAX_RETRY_AFTER_SECONDS))
    except (ValueError, TypeError, AttributeError):
        pass
    return 5.0


def _extract_rate_reset(headers) -> float:
    """Return seconds until rate limit resets, from X-RateLimit-Reset."""
    try:
        reset_ts = int(headers.get("X-RateLimit-Reset") or 0)
        if reset_ts:
            wait = reset_ts - time.time()
            return max(1.0, min(wait, float(_MAX_RETRY_AFTER_SECONDS)))
    except (ValueError, TypeError):
        pass
    return 5.0


def _extract_next_url(link_header: str | None) -> str | None:
    """Parse GitHub Link header, return URL with rel='next' or None."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        m = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', part)
        if m and m.group(2) == "next":
            return m.group(1)
    return None


def _make_request(url: str, timeout: int, token: str | None) -> tuple[Any, dict]:
    """GET url with GitHub headers, return (parsed_json, response_headers).

    Raises:
        _SkipRepo     — 404, 403 without Retry-After (inaccessible), 451
        _RateLimitError — 429, or 403 with Retry-After (secondary rate limit)
        _TransientError — 5xx, timeout, connection error
        ConnectorError  — unexpected 4xx, bad JSON
    """
    req = urllib.request.Request(url, headers=_build_headers(token))

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            # Collect headers into a plain dict (case-insensitive access below)
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 451):
            raise _SkipRepo(f"HTTP {exc.code}")
        if exc.code == 429:
            raise _RateLimitError(_extract_retry_after(exc.headers))
        if exc.code == 403:
            # Secondary rate limit: Retry-After present → wait and retry
            retry_after_val = (exc.headers.get("Retry-After") or
                               exc.headers.get("retry-after") or "")
            if retry_after_val.strip():
                raise _RateLimitError(_extract_retry_after(exc.headers))
            # 403 without Retry-After: could be rate-reset-based
            wait = _extract_rate_reset(exc.headers)
            raise _RateLimitError(wait)
        if 500 <= exc.code < 600:
            raise _TransientError(f"HTTP {exc.code}")
        raise ConnectorError(f"GitHub HTTP {exc.code}")
    except TimeoutError:
        raise _TransientError("timeout")
    except OSError as exc:
        raise _TransientError(f"connection error: {type(exc).__name__}")

    try:
        return json.loads(body), headers
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"GitHub invalid JSON: {exc}") from exc


def _with_retry(fn, max_retries: int, sleep_fn=time.sleep) -> Any:
    """Run fn() with exponential backoff on transient / rate-limit errors.
    _SkipRepo propagates immediately without retry.
    """
    backoff = _BACKOFF_BASE
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except _SkipRepo:
            raise
        except _RateLimitError as exc:
            if attempt >= max_retries:
                raise ConnectorError(
                    f"GitHub rate limit after {attempt + 1} attempts"
                ) from exc
            wait = min(exc.retry_after, _MAX_RETRY_AFTER_SECONDS)
            logger.warning("GitHub rate limit — waiting %.1fs (retry %d/%d)",
                           wait, attempt + 1, max_retries)
            sleep_fn(wait)
        except _TransientError as exc:
            if attempt >= max_retries:
                raise ConnectorError(
                    f"GitHub transient error after {attempt + 1} attempts: {exc}"
                ) from exc
            wait = min(backoff, _BACKOFF_CAP)
            logger.warning("GitHub transient (%s) — waiting %.1fs (retry %d/%d)",
                           exc, wait, attempt + 1, max_retries)
            sleep_fn(wait)
            backoff = min(backoff * 2, _BACKOFF_CAP)
    raise ConnectorError("GitHub: unreachable retry loop exit")  # pragma: no cover


# ------------------------------------------------------------------
# README fetcher
# ------------------------------------------------------------------

def _fetch_readme(owner: str, repo: str, timeout: int,
                  token: str | None, sleep_fn, max_retries: int) -> str | None:
    """Fetch and decode README for owner/repo. Returns None if absent."""
    url = f"{_API_BASE}/repos/{owner}/{repo}/readme"
    try:
        data, _ = _with_retry(
            lambda: _make_request(url, timeout, token),
            max_retries,
            sleep_fn,
        )
    except _SkipRepo:
        return None  # README absent (404) — normal case
    except ConnectorError as exc:
        logger.warning("Could not fetch README for %s/%s: %s", owner, repo, exc)
        return None

    content_b64: str | None = data.get("content")
    if not content_b64:
        return None
    try:
        # GitHub returns base64 with newlines
        raw_bytes = base64.b64decode(content_b64.replace("\n", ""))
        text = raw_bytes.decode("utf-8", errors="replace")
        return text
    except Exception as exc:
        logger.warning("Could not decode README for %s/%s: %s", owner, repo, exc)
        return None


# ------------------------------------------------------------------
# Content hash
# ------------------------------------------------------------------

def _compute_hash(external_id: str, source_key: str, title: str,
                  description: str | None, metadata: dict) -> str:
    payload = json.dumps(
        {
            "external_id": external_id,
            "source_key": source_key,
            "title": title,
            "description": description,
            "topics": metadata.get("topics"),
            "language": metadata.get("language"),
            "owner": metadata.get("owner"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ------------------------------------------------------------------
# Normalisation
# ------------------------------------------------------------------

def _parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _normalise_repo(raw: dict[str, Any], readme: str | None,
                    source_key: str, captured_at: datetime) -> NormalisedItem | None:
    """Normalise a GitHub repo dict → NormalisedItem.

    Returns None if:
      - repo is private (logged, counted as skipped)
      - external_id or full_name absent (logged)
    """
    if raw.get("private"):
        logger.warning(
            "Skipping private repo '%s' — only public repos collected",
            raw.get("full_name", "<unknown>"),
        )
        return None

    repo_id: int | None = raw.get("id")
    if repo_id is None:
        logger.warning("GitHub repo missing 'id'; skipping")
        return None
    external_id = str(repo_id)

    full_name: str = (raw.get("full_name") or "").strip()
    if not full_name:
        logger.warning("GitHub repo %s missing 'full_name'; skipping", external_id)
        return None

    description: str | None = (raw.get("description") or "").strip() or None

    owner_raw = raw.get("owner") or {}
    owner: dict = {
        "login": owner_raw.get("login"),
        "type": owner_raw.get("type"),
    }

    metadata: dict[str, Any] = {
        "name": raw.get("name"),
        "full_name": full_name,
        "owner": owner,
        "topics": raw.get("topics") or [],
        "language": raw.get("language"),
        "created_at": raw.get("created_at"),
        "stargazers_count": raw.get("stargazers_count"),
        "forks_count": raw.get("forks_count"),
        "visibility": raw.get("visibility"),
        "default_branch": raw.get("default_branch"),
        "source": "github",
        "github_id": repo_id,
        "captured_at": captured_at.isoformat(),
    }

    if readme is not None:
        if len(readme) > README_MAX_CHARS:
            readme = readme[:README_MAX_CHARS] + "\n[truncated]"
        metadata["readme"] = readme

    content_hash = _compute_hash(external_id, source_key, full_name, description, metadata)

    # original_date: prefer pushed_at (most recent activity), fallback updated_at
    original_date = (
        _parse_github_datetime(raw.get("pushed_at"))
        or _parse_github_datetime(raw.get("updated_at"))
    )

    return NormalisedItem(
        external_id=external_id,
        item_type="repository",
        title=full_name,
        source_key=source_key,
        content_hash=content_hash,
        description=description,
        original_url=raw.get("html_url"),
        original_date=original_date,
        metadata=metadata,
        captured_at=captured_at,
    )


# ------------------------------------------------------------------
# Connector
# ------------------------------------------------------------------

class GitHubConnector:
    """Fetches public repositories from the GitHub API and yields NormalisedItems.

    Configuration via environment (read at construction time):
        GITHUB_TOKEN — optional PAT for 5 000 req/h (vs 60 req/h without).
                       Without a token the connector works with reduced limits
                       and logs a warning.

    Token is never logged, stored in a public attribute, included in any
    exception message, or written to metadata.

    Three fetch modes (mutually exclusive; evaluated in order):
        repos:       explicit list of 'owner/repo' strings
        org_or_user: fetch all public repos for an org or user login
        query:       GitHub repository search query (e.g. 'topic:fastapi')

    Args:
        query:        search query string (search mode)
        repos:        list of 'owner/repo' strings (explicit mode)
        org_or_user:  org or user login (org/user mode)
        fetch_readme: whether to fetch README for each repo (default True)
        per_page:     1–100, default 100
        max_pages:    stop after N pages (None = no limit)
        timeout:      HTTP timeout in seconds
        max_retries:  retry attempts on transient / rate-limit errors
        source_key:   value written to NormalisedItem.source_key
        _env:         env dict override (tests only)
        _sleep_fn:    sleep override (tests only)
    """

    SOURCE_KEY = "github"

    def __init__(
        self,
        query: str | None = None,
        repos: list[str] | None = None,
        org_or_user: str | None = None,
        fetch_readme: bool = True,
        per_page: int = _DEFAULT_PER_PAGE,
        max_pages: int | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
        source_key: str = SOURCE_KEY,
        _env: dict | None = None,
        _sleep_fn=time.sleep,
    ) -> None:
        env = _env if _env is not None else os.environ
        self._token: str | None = env.get("GITHUB_TOKEN") or None

        if not self._token:
            logger.warning(
                "GITHUB_TOKEN not set — using unauthenticated mode "
                "(60 req/h). Set GITHUB_TOKEN for 5 000 req/h."
            )

        self.query = query
        self.repos = repos or []
        self.org_or_user = org_or_user
        self.fetch_readme = fetch_readme
        self.per_page = min(max(1, per_page), 100)
        self.max_pages = max_pages
        self.timeout = timeout
        self.max_retries = max_retries
        self.source_key = source_key
        self._sleep_fn = _sleep_fn

    # ------------------------------------------------------------------ #

    def fetch(self) -> Iterator[NormalisedItem]:
        """Yield NormalisedItems for all matching public repositories.

        Raises ConnectorError on unrecoverable page-level failure.
        Individual inaccessible repos (404/403/451/private) are skipped
        with a warning — they do not abort the overall fetch.
        """
        if self.repos:
            yield from self._fetch_explicit()
        elif self.org_or_user:
            yield from self._fetch_org_user()
        elif self.query:
            yield from self._fetch_search()
        else:
            raise ConnectorError(
                "GitHubConnector requires one of: query, repos, or org_or_user"
            )

    # ------------------------------------------------------------------ #

    def _get_readme(self, owner: str, repo: str) -> str | None:
        if not self.fetch_readme:
            return None
        return _fetch_readme(owner, repo, self.timeout, self._token,
                             self._sleep_fn, self.max_retries)

    def _process_repo(self, raw: dict, captured_at: datetime) -> NormalisedItem | None:
        owner_login = (raw.get("owner") or {}).get("login") or ""
        repo_name = raw.get("name") or ""
        readme = self._get_readme(owner_login, repo_name) if owner_login and repo_name else None
        return _normalise_repo(raw, readme, self.source_key, captured_at)

    def _fetch_explicit(self) -> Iterator[NormalisedItem]:
        """Fetch a fixed list of 'owner/repo' strings."""
        for repo_slug in self.repos:
            try:
                owner, repo_name = repo_slug.split("/", 1)
            except ValueError:
                logger.warning("Invalid repo slug '%s', skipping", repo_slug)
                continue

            url = f"{_API_BASE}/repos/{owner}/{repo_name}"
            captured_at = datetime.now(timezone.utc)
            try:
                raw, _ = _with_retry(
                    lambda u=url: _make_request(u, self.timeout, self._token),
                    self.max_retries,
                    self._sleep_fn,
                )
            except _SkipRepo as exc:
                logger.warning("Skipping repo %s: %s", repo_slug, exc)
                continue
            except ConnectorError as exc:
                logger.error("Error fetching repo %s: %s", repo_slug, exc)
                continue

            item = self._process_repo(raw, captured_at)
            if item is not None:
                yield item

    def _fetch_org_user(self) -> Iterator[NormalisedItem]:
        """Fetch all public repos for an org or user."""
        url: str | None = (
            f"{_API_BASE}/orgs/{self.org_or_user}/repos"
            f"?type=public&per_page={self.per_page}"
        )
        page_num = 0

        while url:
            if self.max_pages is not None and page_num >= self.max_pages:
                logger.info("GitHub org/user: max_pages=%d reached", self.max_pages)
                break

            captured_at = datetime.now(timezone.utc)
            try:
                data, headers = _with_retry(
                    lambda u=url: _make_request(u, self.timeout, self._token),
                    self.max_retries,
                    self._sleep_fn,
                )
            except ConnectorError as exc:
                logger.error("GitHub org/user page %d error: %s", page_num + 1, exc)
                break

            if not isinstance(data, list) or not data:
                logger.info("GitHub org/user: empty page %d, done", page_num + 1)
                break

            page_num += 1
            logger.info("GitHub org/user page %d: %d repos", page_num, len(data))

            for raw in data:
                item = self._process_repo(raw, captured_at)
                if item is not None:
                    yield item

            url = _extract_next_url(headers.get("link"))

    def _fetch_search(self) -> Iterator[NormalisedItem]:
        """Search repositories using GitHub search API."""
        # Search endpoint uses per_page and page (no Link-header cursor in search)
        page = 1

        while True:
            if self.max_pages is not None and page > self.max_pages:
                logger.info("GitHub search: max_pages=%d reached", self.max_pages)
                break

            params = urllib.parse.urlencode({
                "q": self.query,
                "per_page": self.per_page,
                "page": page,
            })
            url = f"{_API_BASE}/search/repositories?{params}"
            captured_at = datetime.now(timezone.utc)

            try:
                data, headers = _with_retry(
                    lambda u=url: _make_request(u, self.timeout, self._token),
                    self.max_retries,
                    self._sleep_fn,
                )
            except ConnectorError as exc:
                logger.error("GitHub search page %d error: %s", page, exc)
                break

            if not isinstance(data, dict):
                logger.error("GitHub search: unexpected response type on page %d", page)
                break

            items = data.get("items")
            if not isinstance(items, list) or not items:
                logger.info("GitHub search: empty results on page %d, done", page)
                break

            logger.info("GitHub search page %d: %d repos (total=%s)",
                        page, len(items), data.get("total_count"))

            for raw in items:
                item = self._process_repo(raw, captured_at)
                if item is not None:
                    yield item

            # GitHub search: use Link header when present, otherwise increment page
            next_url = _extract_next_url(headers.get("link"))
            if next_url:
                # next_url already contains correct page param; extract page number
                parsed = urllib.parse.urlparse(next_url)
                qp = dict(urllib.parse.parse_qsl(parsed.query))
                try:
                    page = int(qp.get("page", page + 1))
                except ValueError:
                    page += 1
            else:
                logger.info("GitHub search: no next page after page %d, done", page)
                break
