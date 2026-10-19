"""Repository for ingestion persistence operations.

Handles upsert of Source and AcademicItem records, deduplication, and
change detection via content_hash.  All DB interactions are transactional
at the item level — a failure on one item does not roll back items already
committed.

Deduplication key: (source_id, external_id) — enforced by UNIQUE constraint
in the database (migration 003).

Update rule: an existing item is updated only when its content_hash has
changed (meaning at least one content field changed at the source).  Volatile
fields (captured_at) are never used for change detection.

Provenance: captured_at is set by the connector at fetch time and written on
creation; it is NOT overwritten on update to preserve the original capture
timestamp.  A second field 'last_seen_at' (stored in metadata_) records the
most recent fetch that observed this item.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academic_item import AcademicItem
from app.models.source import Source
from app.services.ingestion.models import NormalisedItem

logger = logging.getLogger("trama.ingestion.repository")

UpsertOutcome = Literal["created", "updated", "unchanged"]


# ------------------------------------------------------------------
# Source helpers
# ------------------------------------------------------------------

def get_or_create_source(
    session: Session,
    provider: str,
    canonical_id: str,
    name: str,
    url: str | None = None,
) -> Source:
    """Return existing Source or create a new one (committed immediately).

    Uses UNIQUE (provider, canonical_id) as the natural key.
    """
    stmt = select(Source).where(
        Source.provider == provider,
        Source.canonical_id == canonical_id,
    )
    existing = session.execute(stmt).scalar_one_or_none()
    if existing:
        return existing

    source = Source(
        id=uuid.uuid4(),
        provider=provider,
        name=name,
        canonical_id=canonical_id,
        url=url,
    )
    session.add(source)
    session.commit()
    logger.info("Created Source provider=%r canonical_id=%r", provider, canonical_id)
    return source


# ------------------------------------------------------------------
# AcademicItem upsert
# ------------------------------------------------------------------

def upsert_item(
    session: Session,
    source: Source,
    item: NormalisedItem,
) -> UpsertOutcome:
    """Persist a NormalisedItem as an AcademicItem with upsert semantics.

    Returns:
        'created'   — new record inserted
        'updated'   — existing record updated (content_hash changed)
        'unchanged' — existing record unchanged (same content_hash)

    Each call is committed individually.  Caller is responsible for
    accumulating outcome counts.

    Provenance: captured_at is immutable after creation.
    metadata_['last_seen_at'] is updated on every run (not a change trigger).
    """
    stmt = select(AcademicItem).where(
        AcademicItem.source_id == source.id,
        AcademicItem.external_id == item.external_id,
    )
    existing: AcademicItem | None = session.execute(stmt).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing is None:
        # Merge captured_at into metadata at creation time so it survives updates.
        item_meta = dict(item.metadata or {})
        item_captured = item.captured_at or now
        item_meta.setdefault("captured_at", item_captured.isoformat())
        item_meta["last_seen_at"] = now.isoformat()

        new_item = AcademicItem(
            id=uuid.uuid4(),
            source_id=source.id,
            external_id=item.external_id,
            item_type=item.item_type,
            title=item.title,
            description=item.description,
            original_url=item.original_url,
            original_date=item.original_date,
            captured_at=item_captured,
            content_hash=item.content_hash,
            metadata_=item_meta,
        )
        session.add(new_item)
        session.commit()
        logger.debug("Created AcademicItem external_id=%r", item.external_id)
        return "created"

    if existing.content_hash == item.content_hash:
        # Content unchanged — update only last_seen_at in metadata
        meta = dict(existing.metadata_ or {})
        meta["last_seen_at"] = now.isoformat()
        existing.metadata_ = meta
        session.commit()
        logger.debug("Unchanged AcademicItem external_id=%r", item.external_id)
        return "unchanged"

    # Content changed — update all content fields; preserve original captured_at
    existing.item_type = item.item_type
    existing.title = item.title
    existing.description = item.description
    existing.original_url = item.original_url
    existing.original_date = item.original_date
    existing.content_hash = item.content_hash
    # Merge metadata: preserve original captured_at, update rest
    original_captured_at = (existing.metadata_ or {}).get("captured_at")
    new_meta = {**(item.metadata or {}), "last_seen_at": now.isoformat()}
    if original_captured_at:
        new_meta["captured_at"] = original_captured_at
    existing.metadata_ = new_meta
    session.commit()
    logger.debug("Updated AcademicItem external_id=%r (hash changed)", item.external_id)
    return "updated"
