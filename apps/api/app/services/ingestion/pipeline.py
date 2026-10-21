"""Ingestion pipeline — orchestrates connectors and persistence.

Coordinates:
  1. Connector yields NormalisedItems
  2. Repository upserts each item (create / update / unchanged)
  3. IngestionResult accumulates counts per source

Transactional granularity: per item.  A failure on one item is logged and
counted as 'error'; items already committed are not rolled back.  This means
a partial run is recoverable: re-running will skip unchanged items (via
content_hash) and re-attempt only missing or changed ones.

The pipeline does NOT create Entity or Relationship records — that is the
responsibility of the Relationship Engine (out of scope for this pipeline).
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from app.repositories.ingestion import get_or_create_source, upsert_item
from app.services.ingestion.models import IngestionResult, NormalisedItem

logger = logging.getLogger("trama.ingestion.pipeline")


# ------------------------------------------------------------------
# Source descriptors
# ------------------------------------------------------------------

# Maps source_key → (provider, name, url) for Source record creation.
# These are the only recognised sources for this pipeline.
_SOURCE_DESCRIPTORS: dict[str, tuple[str, str, str]] = {
    "openalex": (
        "openalex",
        "OpenAlex",
        "https://openalex.org",
    ),
    "github": (
        "github",
        "GitHub",
        "https://github.com",
    ),
}


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------

class IngestionPipeline:
    """Orchestrates ingestion from a connector into the database.

    Usage:
        pipeline = IngestionPipeline(session)
        result = pipeline.run(connector)
        print(result)
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def run(self, connector) -> IngestionResult:
        """Run ingestion for the given connector.

        Args:
            connector: any object with a .fetch() -> Iterator[NormalisedItem]
                       and a .source_key: str attribute.

        Returns:
            IngestionResult with per-source counts.
        """
        source_key: str = connector.source_key
        result = IngestionResult(source_key=source_key)

        descriptor = _SOURCE_DESCRIPTORS.get(source_key)
        if descriptor is None:
            msg = (
                f"Unknown source_key '{source_key}'. "
                f"Known: {list(_SOURCE_DESCRIPTORS)}"
            )
            logger.error(msg)
            result.errors += 1
            result.error_details.append(msg)
            return result

        provider, name, url = descriptor
        source = get_or_create_source(
            self._session,
            provider=provider,
            canonical_id=source_key,
            name=name,
            url=url,
        )

        logger.info("Starting ingestion for source_key=%r (source.id=%s)", source_key, source.id)

        try:
            items: Iterable[NormalisedItem] = connector.fetch()
            for item in items:
                result.total_fetched += 1
                try:
                    outcome = upsert_item(self._session, source, item)
                    if outcome == "created":
                        result.created += 1
                    elif outcome == "updated":
                        result.updated += 1
                    elif outcome == "unchanged":
                        result.unchanged += 1
                except Exception as exc:
                    result.errors += 1
                    # Log the error type and external_id — never the full content
                    msg = f"upsert failed for external_id={item.external_id!r}: {type(exc).__name__}"
                    logger.error(msg)
                    result.error_details.append(msg)
                    # Roll back any uncommitted state from this item
                    try:
                        self._session.rollback()
                    except Exception:
                        pass

        except Exception as exc:
            result.errors += 1
            msg = f"connector.fetch() raised {type(exc).__name__}: {exc}"
            logger.error(msg)
            result.error_details.append(msg)

        # Recoverable per-repository fetch failures do not terminate iteration.
        fetch_errors = getattr(connector, "fetch_errors", ())
        result.errors += len(fetch_errors)
        result.error_details.extend(fetch_errors)
        for msg in fetch_errors:
            logger.error(msg)

        logger.info(
            "Ingestion done: source=%r fetched=%d created=%d updated=%d "
            "unchanged=%d skipped=%d errors=%d",
            source_key,
            result.total_fetched,
            result.created,
            result.updated,
            result.unchanged,
            result.skipped,
            result.errors,
        )
        return result
