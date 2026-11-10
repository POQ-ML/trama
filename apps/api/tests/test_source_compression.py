"""Decoded HTTP bodies must not be decoded a second time by the buffer."""

import base64
import gzip
import json
import time

import httpx
import pytest

from app.services.source_collectors import (
    CollectionState,
    GitHubRepoCollector,
    SourceFailure,
)

RAW = {
    "id": 42,
    "name": "repo",
    "full_name": "team/repo",
    "owner": {"login": "team"},
    "html_url": "https://github.com/team/repo",
    "description": "Graph retrieval context",
    "private": False,
}
README = "Contexto científico com evidência UTF-8."
BODY = {"content": base64.b64encode(README.encode()).decode()}


def response(payload, compressed, etag):
    plain = json.dumps(payload, ensure_ascii=False).encode()
    content = gzip.compress(plain) if compressed else plain
    headers = {
        "Content-Type": "application/json",
        "ETag": etag,
        "Content-Length": str(len(content)),
    }
    if compressed:
        headers["Content-Encoding"] = "gzip"
    return httpx.Response(200, headers=headers, content=content)


@pytest.mark.parametrize(
    "repo_gzip,readme_gzip", [(True, False), (False, True), (True, True)]
)
def test_gzip_repository_and_readme(repo_gzip, readme_gzip):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return (
            response(BODY, readme_gzip, "readme-etag")
            if request.url.path.endswith("/readme")
            else response(RAW, repo_gzip, "repo-etag")
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GitHubRepoCollector(client).collect(
            "https://github.com/team/repo", deadline=time.monotonic() + 5
        )
    assert calls == ["/repos/team/repo", "/repos/team/repo/readme"]
    assert result.item.description == RAW["description"]
    assert result.item.metadata["readme"] == README
    assert (result.etag_repo, result.etag_readme) == ("repo-etag", "readme-etag")


def test_gzip_headers_normalized_for_buffered_response():
    plain = json.dumps(RAW, ensure_ascii=False).encode()

    def handler(request):
        return response(RAW, True, "source-etag")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        buffered = GitHubRepoCollector(client)._get(
            client, "/repos/team/repo", {}, None, time.monotonic() + 5
        )
    assert buffered.json() == RAW
    assert "content-encoding" not in buffered.headers
    assert int(buffered.headers["content-length"]) == len(plain)
    assert buffered.headers["etag"] == "source-etag"


def test_gzip_baseline_keeps_etags_and_hash_on_304():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) > 2:
            return httpx.Response(
                304, headers={"ETag": request.headers["if-none-match"]}
            )
        return (
            response(BODY, True, "readme-etag")
            if request.url.path.endswith("/readme")
            else response(RAW, True, "repo-etag")
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        collector = GitHubRepoCollector(client)
        first = collector.collect(
            "https://github.com/team/repo", deadline=time.monotonic() + 5
        )
        second = collector.collect(
            "https://github.com/team/repo",
            state=CollectionState(first.item, first.etag_repo, first.etag_readme),
            deadline=time.monotonic() + 5,
        )
    assert second.not_modified and second.item.content_hash == first.item.content_hash
    assert second.item.metadata["readme"] == README
    assert calls[2].headers["if-none-match"] == "repo-etag"
    assert calls[3].headers["if-none-match"] == "readme-etag"


@pytest.mark.parametrize("side", ["repo", "readme"])
def test_gzip_limit_counts_decoded_bytes(side):
    calls = []

    def handler(request):
        calls.append(request)
        if side == "readme" and len(calls) == 1:
            return response(RAW, True, "repo-etag")
        payload = (
            {"content": "x" * 2_000_001}
            if side == "readme"
            else {**RAW, "description": "x" * 2_000_001}
        )
        return response(payload, True, "oversized")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceFailure) as error:
            GitHubRepoCollector(client).collect(
                "https://github.com/team/repo", deadline=time.monotonic() + 5
            )
    assert error.value.code == "source_unavailable"
    assert len(calls) == (2 if side == "readme" else 1)
