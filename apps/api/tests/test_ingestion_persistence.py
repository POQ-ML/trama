"""Tests for ingestion repository and pipeline persistence.

Two tiers:
  - Unit (SQLite in-memory, db_session fixture from conftest):
      creation, reimport, update on change, no update when unchanged,
      provenance preserved, partial failure isolation.
  - Integration (Postgres, pg_session fixture, auto-skipped without DB):
      same scenarios against real constraints.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from app.models.academic_item import AcademicItem
from app.models.source import Source
from app.repositories.ingestion import get_or_create_source, upsert_item
from app.services.ingestion.models import IngestionResult, NormalisedItem
from app.services.ingestion.pipeline import IngestionPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CAPTURED = datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc)


def _make_item(
    external_id: str = "W001",
    source_key: str = "openalex",
    title: str = "Test Work",
    description: str | None = "Abstract text",
    content_hash: str | None = None,
    item_type: str = "article",
) -> NormalisedItem:
    from app.services.ingestion.openalex import _compute_hash
    meta = {"doi": "10.1/test", "authors": [], "topics": []}
    ch = content_hash or _compute_hash(external_id, source_key, title, description, meta)
    return NormalisedItem(
        external_id=external_id,
        item_type=item_type,
        title=title,
        source_key=source_key,
        content_hash=ch,
        description=description,
        original_url=f"https://example.com/{external_id}",
        original_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        metadata=meta,
        captured_at=_CAPTURED,
    )


def _make_source(session, provider="openalex", name="OpenAlex") -> Source:
    return get_or_create_source(
        session,
        provider=provider,
        canonical_id=provider,
        name=name,
        url="https://openalex.org",
    )


# ---------------------------------------------------------------------------
# Unit tests (SQLite in-memory, db_session from conftest)
# ---------------------------------------------------------------------------

class TestGetOrCreateSource:
    def test_creates_new_source(self, db_session):
        source = _make_source(db_session)
        assert source.id is not None
        assert source.provider == "openalex"

    def test_returns_existing_source(self, db_session):
        s1 = _make_source(db_session)
        s2 = _make_source(db_session)
        assert s1.id == s2.id

    def test_different_provider_creates_different_source(self, db_session):
        s1 = get_or_create_source(db_session, "openalex", "openalex", "OA", None)
        s2 = get_or_create_source(db_session, "github", "github", "GH", None)
        assert s1.id != s2.id


class TestUpsertItem:
    def test_creates_new_item(self, db_session):
        source = _make_source(db_session)
        item = _make_item()
        outcome = upsert_item(db_session, source, item)
        assert outcome == "created"

        from sqlalchemy import select
        row = db_session.execute(
            select(AcademicItem).where(AcademicItem.external_id == "W001")
        ).scalar_one()
        assert row.title == "Test Work"
        assert row.source_id == source.id

    def test_reimport_same_item_is_unchanged(self, db_session):
        source = _make_source(db_session)
        item = _make_item()
        upsert_item(db_session, source, item)
        outcome = upsert_item(db_session, source, item)
        assert outcome == "unchanged"

    def test_update_when_content_changes(self, db_session):
        source = _make_source(db_session)
        item_v1 = _make_item(title="Old Title", content_hash="a" * 64)
        upsert_item(db_session, source, item_v1)

        item_v2 = _make_item(title="New Title", content_hash="b" * 64)
        outcome = upsert_item(db_session, source, item_v2)
        assert outcome == "updated"

        from sqlalchemy import select
        row = db_session.execute(
            select(AcademicItem).where(AcademicItem.external_id == "W001")
        ).scalar_one()
        assert row.title == "New Title"

    def test_no_duplicate_on_reimport(self, db_session):
        from sqlalchemy import select, func
        source = _make_source(db_session)
        item = _make_item()
        upsert_item(db_session, source, item)
        upsert_item(db_session, source, item)
        count = db_session.execute(
            select(func.count()).select_from(AcademicItem).where(
                AcademicItem.external_id == "W001"
            )
        ).scalar()
        assert count == 1

    def test_captured_at_preserved_on_update(self, db_session):
        source = _make_source(db_session)
        item_v1 = _make_item(content_hash="a" * 64)
        item_v1.captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        upsert_item(db_session, source, item_v1)

        item_v2 = _make_item(title="Updated", content_hash="b" * 64)
        item_v2.captured_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
        upsert_item(db_session, source, item_v2)

        from sqlalchemy import select
        row = db_session.execute(
            select(AcademicItem).where(AcademicItem.external_id == "W001")
        ).scalar_one()
        # Original captured_at preserved in metadata
        assert row.metadata_["captured_at"] == datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()

    def test_provenance_fields_stored(self, db_session):
        source = _make_source(db_session)
        item = _make_item()
        upsert_item(db_session, source, item)

        from sqlalchemy import select
        row = db_session.execute(
            select(AcademicItem).where(AcademicItem.external_id == "W001")
        ).scalar_one()
        assert row.original_url == "https://example.com/W001"
        assert row.metadata_["doi"] == "10.1/test"

    def test_item_type_repository(self, db_session):
        source = get_or_create_source(db_session, "github", "github", "GitHub", None)
        item = _make_item(external_id="12345", source_key="github", item_type="repository")
        outcome = upsert_item(db_session, source, item)
        assert outcome == "created"

        from sqlalchemy import select
        row = db_session.execute(
            select(AcademicItem).where(AcademicItem.external_id == "12345")
        ).scalar_one()
        assert row.item_type == "repository"


# ---------------------------------------------------------------------------
# Pipeline unit tests
# ---------------------------------------------------------------------------

class _FakeConnector:
    """Minimal connector double — yields a fixed list of NormalisedItems."""

    def __init__(self, items: list[NormalisedItem], source_key: str = "openalex",
                 error_on: int | None = None) -> None:
        self._items = items
        self.source_key = source_key
        self._error_on = error_on

    def fetch(self) -> Iterator[NormalisedItem]:
        for i, item in enumerate(self._items):
            if self._error_on is not None and i == self._error_on:
                raise RuntimeError("simulated fetch error")
            yield item


class TestIngestionPipeline:
    def test_creates_items(self, db_session):
        items = [_make_item("W001"), _make_item("W002")]
        result = IngestionPipeline(db_session).run(_FakeConnector(items))
        assert result.created == 2
        assert result.total_fetched == 2
        assert result.errors == 0

    def test_unchanged_on_reimport(self, db_session):
        items = [_make_item("W001")]
        pipeline = IngestionPipeline(db_session)
        pipeline.run(_FakeConnector(items))
        result = pipeline.run(_FakeConnector(items))
        assert result.unchanged == 1
        assert result.created == 0

    def test_updated_when_content_changes(self, db_session):
        pipeline = IngestionPipeline(db_session)
        pipeline.run(_FakeConnector([_make_item("W001", content_hash="a" * 64)]))
        result = pipeline.run(_FakeConnector([_make_item("W001", title="New", content_hash="b" * 64)]))
        assert result.updated == 1

    def test_unknown_source_key_returns_error(self, db_session):
        connector = _FakeConnector([], source_key="unknown_source")
        result = IngestionPipeline(db_session).run(connector)
        assert result.errors == 1
        assert result.created == 0

    def test_partial_failure_does_not_abort_remaining_items(self, db_session):
        """A failure on item 1 (index 1) must not prevent item 2 from being saved."""
        items = [_make_item("W001"), _make_item("W002"), _make_item("W003")]
        pipeline = IngestionPipeline(db_session)

        # Simulate upsert failure on the second item only
        original_upsert = upsert_item
        call_count = [0]

        def patched_upsert(session, source, item):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("forced upsert error")
            return original_upsert(session, source, item)

        import app.services.ingestion.pipeline as pipeline_mod
        original = pipeline_mod.upsert_item
        pipeline_mod.upsert_item = patched_upsert
        try:
            result = pipeline.run(_FakeConnector(items))
        finally:
            pipeline_mod.upsert_item = original

        # Items 1 and 3 should succeed; item 2 should error
        assert result.created == 2
        assert result.errors == 1

    def test_result_str_contains_counts(self, db_session):
        items = [_make_item("W001")]
        result = IngestionPipeline(db_session).run(_FakeConnector(items))
        s = str(result)
        assert "created=1" in s
        assert "openalex" in s

    def test_github_source_key(self, db_session):
        item = _make_item("123", source_key="github", item_type="repository")
        connector = _FakeConnector([item], source_key="github")
        result = IngestionPipeline(db_session).run(connector)
        assert result.created == 1


# ---------------------------------------------------------------------------
# Integration tests (Postgres, auto-skipped without DB)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _pg_engine_with_schema(pg_engine):
    """Re-apply migrations to head before ingestion integration tests.

    test_migrations_integration.py (which runs earlier in the suite) downgrades
    to 001_initial in its module-level teardown.  This fixture ensures the
    schema is back at head before our integration tests run.
    """
    import os
    from alembic.config import Config
    from alembic import command

    # Locate alembic.ini relative to this file (apps/api/alembic.ini)
    alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    alembic_cfg = Config(os.path.abspath(alembic_ini))
    alembic_cfg.set_main_option(
        "sqlalchemy.url", str(pg_engine.url)
    )
    command.upgrade(alembic_cfg, "head")
    yield pg_engine


@pytest.fixture()
def _pg_session_ingestion(_pg_engine_with_schema):
    """Transactional Postgres session; rolls back after each test."""
    from sqlalchemy.orm import sessionmaker

    connection = _pg_engine_with_schema.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    try:
        transaction.rollback()
    except Exception:
        pass
    connection.close()


class TestIngestionPersistenceIntegration:
    """Postgres-level tests — auto-skipped when TEST_DATABASE_URL is absent."""

    @pytest.mark.integration
    def test_create_and_reimport_no_duplicate(self, _pg_session_ingestion):
        source = _make_source(_pg_session_ingestion)
        item = _make_item()
        r1 = upsert_item(_pg_session_ingestion, source, item)
        r2 = upsert_item(_pg_session_ingestion, source, item)
        assert r1 == "created"
        assert r2 == "unchanged"

        from sqlalchemy import select, func
        count = _pg_session_ingestion.execute(
            select(func.count()).select_from(AcademicItem).where(
                AcademicItem.external_id == "W001"
            )
        ).scalar()
        assert count == 1

    @pytest.mark.integration
    def test_update_preserves_original_captured_at(self, _pg_session_ingestion):
        source = _make_source(_pg_session_ingestion)
        item_v1 = _make_item(content_hash="a" * 64)
        item_v1.captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        upsert_item(_pg_session_ingestion, source, item_v1)

        item_v2 = _make_item(title="Updated Title", content_hash="b" * 64)
        upsert_item(_pg_session_ingestion, source, item_v2)

        from sqlalchemy import select
        row = _pg_session_ingestion.execute(
            select(AcademicItem).where(AcademicItem.external_id == "W001")
        ).scalar_one()
        assert "captured_at" in row.metadata_
        assert "2026-01-01" in row.metadata_["captured_at"]

    @pytest.mark.integration
    def test_provenance_preserved_after_update(self, _pg_session_ingestion):
        source = _make_source(_pg_session_ingestion)
        item = _make_item()
        upsert_item(_pg_session_ingestion, source, item)

        from sqlalchemy import select
        row = _pg_session_ingestion.execute(
            select(AcademicItem).where(AcademicItem.external_id == "W001")
        ).scalar_one()
        assert row.source_id == source.id
        assert row.metadata_["doi"] == "10.1/test"
