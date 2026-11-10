"""Safe one-hop numeric GitHub redirects; all responses are offline."""

import base64
import time
from unittest.mock import patch

import httpx
import pytest

from app.services.source_collectors import GitHubRepoCollector, SourceFailure


RAW = {
    "id": 198616978,
    "full_name": "canonical/library",
    "name": "library",
    "owner": {"login": "canonical"},
    "html_url": "https://github.com/canonical/library",
    "private": False,
    "description": "A public library",
}


def run(handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return GitHubRepoCollector(client).collect(
            "https://github.com/old/library", deadline=time.monotonic() + 5
        )


def test_canonical_one_hop_numeric_redirect_and_same_headers():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                301,
                headers={"Location": "https://api.github.com/repositories/198616978"},
            )
        if len(calls) == 2:
            return httpx.Response(200, json=RAW)
        return httpx.Response(
            200, json={"content": base64.b64encode(b"Actual readme").decode()}
        )

    with patch.dict("os.environ", {"GITHUB_TOKEN": "synthetic-only"}):
        result = run(handler)
    assert [r.url.path for r in calls] == [
        "/repos/old/library",
        "/repositories/198616978",
        "/repos/canonical/library/readme",
    ]
    assert all(r.headers["authorization"] == "Bearer synthetic-only" for r in calls)
    assert (
        result.item.external_id == "198616978"
        and result.item.title == "canonical/library"
    )
    assert result.item.metadata["readme"] == "Actual readme"


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.test/repositories/198616978",
        "http://api.github.com/repositories/198616978",
        "https://api.github.com:443/repositories/198616978",
        "https://user:pass@api.github.com/repositories/198616978",
        "https://api.github.com/repos/other/library",
        "https://api.github.com/repositories/not-numeric",
        "https://api.github.com/repositories/198616978?x=1",
        "https://api.github.com/repositories/198616978#x",
        "/repositories/198616978",
        "https://api.github.com/repositories/%31",
        "https://api.github.com/repositories/0",
    ],
)
def test_reject_invalid_locations_before_second_request(location):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(301, headers={"Location": location})

    with pytest.raises(SourceFailure):
        run(handler)
    assert len(calls) == 1


@pytest.mark.parametrize("second_status", [301, 302, 404, 500])
def test_second_hop_or_destination_failure_never_retried(second_status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            301 if len(calls) == 1 else second_status,
            headers={"Location": "https://api.github.com/repositories/198616978"},
        )

    with pytest.raises(SourceFailure):
        run(handler)
    assert len(calls) == 2


def test_redirect_response_identity_must_match_and_readme_redirect_disallowed():
    calls = []

    def wrong_id(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                301,
                headers={"Location": "https://api.github.com/repositories/198616978"},
            )
        return httpx.Response(200, json={**RAW, "id": 999})

    with pytest.raises(SourceFailure):
        run(wrong_id)
    assert len(calls) == 2
    calls.clear()

    def readme_redirect(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                301,
                headers={"Location": "https://api.github.com/repositories/198616978"},
            )
        if len(calls) == 2:
            return httpx.Response(200, json=RAW)
        return httpx.Response(
            301, headers={"Location": "https://api.github.com/repositories/198616978"}
        )

    with pytest.raises(SourceFailure):
        run(readme_redirect)
    assert len(calls) == 3


def test_deadline_shared_by_both_requests():
    calls = []
    clock = [0.0]

    def handler(request):
        calls.append(request)
        clock[0] = 10
        return httpx.Response(
            301, headers={"Location": "https://api.github.com/repositories/198616978"}
        )

    with patch(
        "app.services.source_collectors.time.monotonic", side_effect=lambda: clock[0]
    ):
        with pytest.raises(SourceFailure) as error:
            run(handler)
    assert error.value.code == "timeout" and len(calls) == 1
