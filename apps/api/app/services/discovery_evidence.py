"""Pure grounding contract for project/article *relevance* suggestions.

Trust boundary: Backend constructs SourceSnapshot from a persisted AcademicItem,
never from LLM/client-supplied source text, URL, hash, ID or observation time.
This module performs no fetch and cannot authenticate a remote source. Source
content is data, never instructions. A JSON schema alone proves no grounding.

Offsets count Python Unicode code points, end exclusive, in the exact normalized
field (not bytes or original Markdown line numbers). The immutable excerpt plus
item/field hashes and offsets preserves what was observed without copying a
whole README per evidence. Hashes identify content; they are not signatures or
an independently verifiable inclusion proof. Backend must persist these values
unchanged and retain old Evidence when AcademicItem changes. observed_at is the
actual source observation time, not explanation generation time or an invented
now(). Use canonical provider URLs derived by Backend when a publisher URL is
outside the deliberately narrow URL policy below.

No result establishes implementation/use, authorship, or a repo topic merely
because an article has that topic. Human acceptance concerns relevance only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Literal, Mapping
from urllib.parse import urlsplit
from uuid import UUID

MAX_EXCERPT_CHARS = 2_000
MAX_FIELD_CHARS = 100_000
_FIELDS = {
    "repo": frozenset({"title", "description", "metadata.readme"}),
    "article": frozenset({"title", "description"}),
}


@dataclass(frozen=True)
class SourceSnapshot:
    origin_item_id: UUID
    side: Literal["repo", "article"]
    fields: Mapping[str, str]
    reference_url: str
    content_hash: str
    observed_at: datetime


@dataclass(frozen=True)
class EvidenceSelection:
    field: str
    start: int
    end: int
    excerpt: str


def _validate_url(url: str, side: str) -> None:
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError("Invalid canonical source URL")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port is not None:
            raise ValueError("Source URL must be canonical HTTPS without credentials or port")
    except ValueError as exc:
        raise ValueError("Invalid canonical source URL") from exc
    if parsed.query or parsed.fragment:
        raise ValueError("Canonical source URL must not contain query or fragment")
    if side == "repo":
        valid = parsed.netloc == "github.com" and re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", parsed.path)
        valid = valid and all(p not in {".", ".."} for p in parsed.path.split("/")[1:] if p)
    else:
        valid = (
            parsed.netloc == "openalex.org" and re.fullmatch(r"/W[0-9]+/?", parsed.path)
        ) or (
            parsed.netloc == "doi.org" and re.fullmatch(r"/10\.[0-9]{4,9}/[^\s]+", parsed.path)
        )
    if not valid:
        raise ValueError("Source URL is outside canonical provider policy")


def build_evidence(snapshot: SourceSnapshot, selection: EvidenceSelection) -> dict:
    """Return Evidence constructor kwargs; relationship_id is added by Backend.

    Only selections are untrusted proposals. SourceSnapshot MUST be supplied by
    Backend's trusted source adapter. This function cannot check item existence
    or whether the supplied URL belongs to that item; Backend must do both.
    """
    if not isinstance(snapshot.origin_item_id, UUID) or snapshot.origin_item_id.int == 0:
        raise ValueError("A persisted AcademicItem UUID is required")
    if snapshot.side not in _FIELDS:
        raise ValueError("Unknown evidence side")
    if not isinstance(snapshot.content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot.content_hash):
        raise ValueError("content_hash must be the item's SHA-256 hex digest")
    observed = snapshot.observed_at
    if not isinstance(observed, datetime) or observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must be an actual timezone-aware observation")
    _validate_url(snapshot.reference_url, snapshot.side)
    if selection.field not in _FIELDS[snapshot.side]:
        raise ValueError("Unsupported source field")
    text = snapshot.fields.get(selection.field)
    if not isinstance(text, str) or len(text) > MAX_FIELD_CHARS:
        raise ValueError("Missing or oversized source field")
    if type(selection.start) is not int or type(selection.end) is not int:
        raise ValueError("Offsets must be integers, not booleans")
    if not 0 <= selection.start < selection.end <= len(text):
        raise ValueError("Offsets must select an existing nonempty source range")
    excerpt = selection.excerpt
    if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > MAX_EXCERPT_CHARS:
        raise ValueError("Excerpt must be nonblank and within size limit")
    if text[selection.start:selection.end] != excerpt:
        raise ValueError("Excerpt must equal the literal source range")
    field_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    observed = observed.astimezone(timezone.utc)
    return {
        "origin_item_id": snapshot.origin_item_id,
        "reference_url": snapshot.reference_url,
        "locator": f"{selection.field}:chars[{selection.start}:{selection.end}]",
        "excerpt": excerpt,
        "capture_version": f"sha256:{snapshot.content_hash}",
        "captured_at": observed,
        "metadata_": {
            "contract_version": 1,
            "side": snapshot.side,
            "role": "project" if snapshot.side == "repo" else "article",
            "claim_kind": "relevance_support",
            "verification": "literal_source_range",
            "extraction_method": "exact_slice_v1",
            "source_field": selection.field,
            "offset_unit": "unicode_codepoint",
            "start": selection.start,
            "end": selection.end,
            "item_content_hash": snapshot.content_hash,
            "field_sha256": field_hash,
            "field_length": len(text),
            "observed_at": observed.isoformat(),
        },
    }


def build_project_article_evidence(
    repo_snapshot: SourceSnapshot,
    article_snapshot: SourceSnapshot,
    repo_selection: EvidenceSelection,
    article_selection: EvidenceSelection,
) -> tuple[dict, dict]:
    """Validate both sides atomically before returning constructor kwargs.

    Backend additionally checks item types, entity origins and relationship pair
    against its database. Presence of two valid excerpts does not itself prove
    semantic relevance; explanation/assessment is a separate contract.
    """
    if repo_snapshot.side != "repo" or article_snapshot.side != "article":
        raise ValueError("project_article requires repo and article evidence")
    if repo_snapshot.origin_item_id == article_snapshot.origin_item_id:
        raise ValueError("Both sides must refer to distinct AcademicItems")
    return build_evidence(repo_snapshot, repo_selection), build_evidence(article_snapshot, article_selection)
