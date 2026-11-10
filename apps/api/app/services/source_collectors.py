"""Exact public-repository collection with two independently conditional requests.

No owner listing, commit feed, arbitrary URLs or unbounded retry. One validated
initial GitHub numeric redirect is allowed; all other redirects are rejected.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from urllib.parse import urlsplit
import time

import httpx

from app.schemas.discovery import DiscoveryCreate
from app.services.ingestion.github import _normalise_repo, _compute_hash
from app.services.ingestion.models import NormalisedItem


class SourceFailure(Exception):
    def __init__(self, code="source_unavailable", *, retry_after: int | None = None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class CollectionState:
    cached: NormalisedItem | None = None
    etag_repo: str | None = None
    etag_readme: str | None = None


@dataclass(frozen=True)
class CollectionResult:
    item: NormalisedItem
    etag_repo: str | None
    etag_readme: str | None
    observed_at: datetime
    not_modified: bool


class GitHubRepoCollector:
    def __init__(
        self, client: httpx.Client | None = None, *, timeout_seconds: float = 8
    ):
        self.client = client
        self.timeout_seconds = timeout_seconds

    def collect(
        self,
        repo_url: str,
        *,
        state: CollectionState = CollectionState(),
        deadline: float,
    ) -> CollectionResult:
        repo_url = DiscoveryCreate(repo_url=repo_url).repo_url
        slug = repo_url.split("github.com/", 1)[1]
        cached = state.cached
        identity = cached.external_id if cached else None
        if identity is not None and not identity.isdigit():
            raise SourceFailure()
        path = f"/repositories/{identity}" if identity else f"/repos/{slug}"
        own = self.client is None
        client = self.client or httpx.Client(follow_redirects=False, trust_env=False)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trama-discovery/1",
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            repo = self._get(
                client,
                path,
                headers,
                state.etag_repo,
                deadline,
                allow_repo_redirect=cached is None,
            )
            if repo.status_code == 304:
                if cached is None or not state.etag_repo:
                    raise SourceFailure()
                raw = self._restore_raw(cached)
            else:
                raw = self._json(repo)
            if (
                raw.get("private")
                or raw.get("visibility") == "private"
                or not isinstance(raw.get("id"), int)
            ):
                raise SourceFailure()
            redirected_id = repo.extensions.get("trama_repository_id")
            if identity and str(raw["id"]) != identity:
                raise SourceFailure()
            if redirected_id and str(raw["id"]) != redirected_id:
                raise SourceFailure()
            canonical = DiscoveryCreate(
                repo_url=f"https://github.com/{raw.get('full_name', '')}"
            ).repo_url
            # Initial lookup must be the exact submitted repo. Subsequent checks use numeric identity.
            if not cached and canonical != repo_url and not redirected_id:
                raise SourceFailure()
            readme_path = f"/repos/{canonical.split('github.com/', 1)[1]}/readme"
            readme = self._get(
                client,
                readme_path,
                headers,
                state.etag_readme,
                deadline,
                allow_missing=True,
            )
            if readme.status_code == 304:
                if cached is None or not state.etag_readme:
                    raise SourceFailure()
                text = cached.metadata.get("readme")
            elif readme.status_code == 404:
                text = None
            else:
                data = self._json(readme)
                try:
                    text = base64.b64decode(
                        data.get("content", ""), validate=False
                    ).decode("utf-8", errors="replace")
                except (ValueError, TypeError):
                    raise SourceFailure() from None
            observed = datetime.now(timezone.utc)
            item = _normalise_repo(raw, text, "github", observed)
            if item is None:
                raise SourceFailure()
            # A cached README is already truncated. Do not truncate it repeatedly on 304.
            if readme.status_code == 304 and text is not None:
                item.metadata["readme"] = text
                item.content_hash = _compute_hash(
                    item.external_id,
                    item.source_key,
                    item.title,
                    item.description,
                    item.metadata,
                    item.original_url,
                    item.original_date,
                )
            if time.monotonic() >= deadline:
                raise SourceFailure("timeout")
            return CollectionResult(
                item,
                repo.headers.get("etag")
                or (state.etag_repo if repo.status_code == 304 else None),
                readme.headers.get("etag")
                or (state.etag_readme if readme.status_code == 304 else None),
                observed,
                repo.status_code == readme.status_code == 304,
            )
        except (httpx.TimeoutException, TimeoutError):
            raise SourceFailure("timeout") from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise SourceFailure() from None
        finally:
            if own:
                client.close()

    def _get(
        self,
        client,
        path,
        headers,
        etag,
        deadline,
        allow_missing=False,
        allow_repo_redirect=False,
    ):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceFailure("timeout")
        request_headers = {**headers, **({"If-None-Match": etag} if etag else {})}
        # Stream and bound body bytes; httpx.Response.json is only used after this bound.
        with client.stream(
            "GET",
            "https://api.github.com" + path,
            headers=request_headers,
            timeout=min(self.timeout_seconds, remaining),
            follow_redirects=False,
        ) as response:
            if response.status_code == 301 and allow_repo_redirect:
                location = response.headers.get("location", "")
                # Exactly one canonical GitHub numeric redirect, never a generic
                # redirect policy. Reject ambiguous/encoded URLs before forwarding.
                if len(location) > 2048 or any(ord(c) <= 32 for c in location):
                    raise SourceFailure()
                target = urlsplit(location)
                match = re.fullmatch(r"/repositories/([1-9][0-9]{0,19})", target.path)
                if (
                    target.scheme != "https"
                    or target.netloc != "api.github.com"
                    or target.query
                    or target.fragment
                    or not match
                ):
                    raise SourceFailure()
                response.close()
                redirected = self._get(client, target.path, headers, None, deadline)
                redirected.extensions["trama_repository_id"] = match.group(1)
                return redirected
            if response.status_code not in (
                {200, 304, 404} if allow_missing else {200, 304}
            ):
                retry = None
                try:
                    retry = (
                        max(1, min(int(response.headers.get("retry-after", "0")), 3600))
                        or None
                    )
                except ValueError:
                    pass
                raise SourceFailure(retry_after=retry)
            chunks = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 2_000_000 or time.monotonic() >= deadline:
                    raise SourceFailure(
                        "timeout"
                        if time.monotonic() >= deadline
                        else "source_unavailable"
                    )
                chunks.append(chunk)
            # iter_bytes() has already decoded Content-Encoding. The buffered
            # response must describe decoded bytes, not decompress them again.
            decoded_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {"content-encoding", "content-length"}
            }
            return httpx.Response(
                response.status_code, headers=decoded_headers, content=b"".join(chunks)
            )

    @staticmethod
    def _json(response):
        data = response.json()
        if not isinstance(data, dict):
            raise SourceFailure()
        return data

    @staticmethod
    def _restore_raw(item):
        meta = item.metadata
        raw = {
            key: meta.get(key)
            for key in [
                "name",
                "full_name",
                "owner",
                "topics",
                "language",
                "created_at",
                "stargazers_count",
                "forks_count",
                "visibility",
                "default_branch",
            ]
        }
        raw.update(
            id=int(item.external_id),
            description=item.description,
            html_url=item.original_url,
            pushed_at=item.original_date.isoformat() if item.original_date else None,
        )
        return raw
