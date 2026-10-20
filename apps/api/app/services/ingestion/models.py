"""Normalised data transfer objects produced by each connector.

These are plain dataclasses — no ORM, no DB dependency.  The pipeline layer
converts them to SQLAlchemy models.  All timestamps are UTC-aware datetimes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalisedItem:
    """A normalised record ready to be persisted as an AcademicItem.

    Fields map 1-to-1 to the AcademicItem columns; see docs/ingestion/audit.md
    for the full field-mapping table per source.
    """

    # Required fields --------------------------------------------------------
    external_id: str          # provider-assigned identifier (immutable)
    item_type: str            # 'article' | 'repository' (closed set — see migration 004)
    title: str                # canonical human-readable title
    source_key: str           # identifies which Source row to use (e.g. 'openalex')
    content_hash: str         # SHA-256 of content fields — used for change detection

    # Optional fields --------------------------------------------------------
    description: str | None = None          # abstract / README / summary
    original_url: str | None = None         # canonical URL at the provider
    original_date: datetime | None = None   # publication / push date (UTC)

    # Structured provenance & provider-specific extras.
    # Never store credentials here.
    metadata: dict[str, Any] = field(default_factory=dict)

    # When this record was fetched from the API (set by the connector).
    captured_at: datetime | None = None     # UTC; set by connector at fetch time


@dataclass
class IngestionResult:
    """Summary of one ingestion run for a single source."""

    source_key: str
    total_fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0      # private repos, schema errors, etc.
    errors: int = 0

    error_details: list[str] = field(default_factory=list)  # non-sensitive messages

    def __str__(self) -> str:  # pragma: no cover
        return (
            f"[{self.source_key}] fetched={self.total_fetched} "
            f"created={self.created} updated={self.updated} "
            f"unchanged={self.unchanged} skipped={self.skipped} "
            f"errors={self.errors}"
        )
