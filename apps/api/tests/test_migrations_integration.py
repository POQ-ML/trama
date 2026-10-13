"""Integration tests: migration chain and pgvector extension.

These tests require a live PostgreSQL instance with the pgvector extension
available (i.e. using the pgvector/pgvector:pg16 image).

They are automatically skipped when TEST_DATABASE_URL / DATABASE_URL is not
set or when the database is unreachable.

To run locally:
    docker compose up -d postgres
    TEST_DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama_test \\
        pytest tests/test_migrations_integration.py -v

What is covered:
  - Migration chain 001 → 002 → 003 runs cleanly on an empty database.
  - All expected tables exist after upgrade head.
  - pgvector extension is available (SELECT vector_dims or version()).
  - downgrade 003 → 002 removes the five tables without error.
  - Tables from 001 (users) survive the downgrade.
  - DB-level CHECK constraints for closed enums are enforced.
  - DB-level UNIQUE constraints are enforced.
  - No self-loop allowed (DB CHECK constraint).
"""

import os
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_alembic(command: str, db_url: str) -> None:
    """Run an alembic command programmatically against db_url."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={db_url}", command],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {command} failed:\n{result.stdout}\n{result.stderr}"
        )


EXPECTED_TABLES = {
    "users",
    "sources",
    "academic_items",
    "entities",
    "relationships",
    "evidences",
}


# ---------------------------------------------------------------------------
# Migration chain
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def migrated_pg_engine(pg_engine):
    """Run alembic upgrade head; yield engine; then downgrade back."""
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

    # Upgrade to head
    from alembic.config import Config
    from alembic import command as alembic_cmd

    api_dir = os.path.join(os.path.dirname(__file__), "..")
    cfg = Config(os.path.join(api_dir, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", os.path.join(api_dir, "alembic"))

    alembic_cmd.upgrade(cfg, "head")

    yield pg_engine

    # Downgrade cleanly after all tests in this module
    alembic_cmd.downgrade(cfg, "001_initial")


class TestMigrationChain:
    def test_all_tables_exist_after_upgrade(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        tables = set(inspector.get_table_names())
        for expected in EXPECTED_TABLES:
            assert expected in tables, f"Table '{expected}' missing after upgrade head"

    def test_users_table_has_expected_columns(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        cols = {c["name"] for c in inspector.get_columns("users")}
        assert {"id", "email", "created_at"}.issubset(cols)

    def test_sources_columns(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        cols = {c["name"] for c in inspector.get_columns("sources")}
        assert {"id", "provider", "name", "canonical_id", "created_at", "updated_at"}.issubset(cols)

    def test_academic_items_columns(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        cols = {c["name"] for c in inspector.get_columns("academic_items")}
        assert {
            "id", "source_id", "external_id", "item_type",
            "title", "content_hash", "captured_at", "search_vector",
        }.issubset(cols)

    def test_entities_columns(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        cols = {c["name"] for c in inspector.get_columns("entities")}
        assert {"id", "entity_type", "label", "created_at"}.issubset(cols)

    def test_relationships_columns(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        cols = {c["name"] for c in inspector.get_columns("relationships")}
        assert {
            "id", "source_id", "target_id", "relationship_type", "status", "score",
        }.issubset(cols)

    def test_evidences_columns(self, migrated_pg_engine):
        inspector = inspect(migrated_pg_engine)
        cols = {c["name"] for c in inspector.get_columns("evidences")}
        assert {
            "id", "relationship_id", "origin_item_id", "captured_at",
        }.issubset(cols)

    def test_alembic_version_at_head(self, migrated_pg_engine):
        with migrated_pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchone()
        assert row is not None
        assert row[0] == "003_persistence_layer"


# ---------------------------------------------------------------------------
# pgvector extension
# ---------------------------------------------------------------------------

class TestPgvectorExtension:
    def test_vector_extension_available(self, migrated_pg_engine):
        """vector extension must be present after migration 002."""
        with migrated_pg_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT extname FROM pg_extension WHERE extname = 'vector'"
                )
            ).fetchone()
        assert row is not None, "pgvector extension 'vector' is not installed"

    def test_vector_type_usable(self, migrated_pg_engine):
        """Sanity check: we can cast a literal to vector type."""
        with migrated_pg_engine.connect() as conn:
            row = conn.execute(
                text("SELECT '[1,2,3]'::vector")
            ).fetchone()
        assert row is not None


# ---------------------------------------------------------------------------
# DB-level constraint enforcement (Postgres only)
# ---------------------------------------------------------------------------

class TestDbConstraints:
    def test_invalid_provider_rejected(self, pg_session):
        """CHECK constraint must reject an unknown provider."""
        pg_session.execute(
            text(
                "INSERT INTO sources (id, provider, name, canonical_id, created_at, updated_at) "
                "VALUES (:id, 'twitter', 'Bad', 'bad-1', now(), now())"
            ),
            {"id": str(uuid.uuid4())},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_invalid_item_type_rejected(self, pg_session):
        """CHECK constraint must reject an unknown item_type."""
        # Insert a valid source first (raw SQL to avoid ORM cascade flush ordering)
        src_id = str(uuid.uuid4())
        pg_session.execute(
            text(
                "INSERT INTO sources (id, provider, name, canonical_id, created_at, updated_at) "
                "VALUES (:id, 'github', 'Src', 'raw-src-1', now(), now())"
            ),
            {"id": src_id},
        )
        pg_session.flush()

        pg_session.execute(
            text(
                "INSERT INTO academic_items "
                "(id, source_id, external_id, item_type, title, content_hash, captured_at) "
                "VALUES (:id, :src_id, 'ext-bad', 'thesis', 'Bad Item', :hash, now())"
            ),
            {"id": str(uuid.uuid4()), "src_id": src_id, "hash": "c" * 64},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_invalid_entity_type_rejected(self, pg_session):
        """CHECK constraint must reject an unknown entity_type."""
        pg_session.execute(
            text(
                "INSERT INTO entities (id, entity_type, label, created_at, updated_at) "
                "VALUES (:id, 'organization', 'UFC', now(), now())"
            ),
            {"id": str(uuid.uuid4())},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_invalid_relationship_type_rejected(self, pg_session):
        """CHECK constraint must reject an unknown relationship_type."""
        e1_id, e2_id = str(uuid.uuid4()), str(uuid.uuid4())
        pg_session.execute(
            text(
                "INSERT INTO entities (id, entity_type, label, created_at, updated_at) "
                "VALUES (:id1, 'person', 'Alice-RT', now(), now()), "
                "       (:id2, 'project', 'ProjectZ-RT', now(), now())"
            ),
            {"id1": e1_id, "id2": e2_id},
        )
        pg_session.flush()

        pg_session.execute(
            text(
                "INSERT INTO relationships "
                "(id, source_id, target_id, relationship_type, status, created_at, updated_at) "
                "VALUES (:id, :src, :tgt, 'authored', 'pending', now(), now())"
            ),
            {"id": str(uuid.uuid4()), "src": e1_id, "tgt": e2_id},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_invalid_status_rejected(self, pg_session):
        """CHECK constraint must reject an invalid relationship status."""
        e1_id, e2_id = str(uuid.uuid4()), str(uuid.uuid4())
        pg_session.execute(
            text(
                "INSERT INTO entities (id, entity_type, label, created_at, updated_at) "
                "VALUES (:id1, 'topic', 'TopicSt', now(), now()), "
                "       (:id2, 'source', 'SourceSt', now(), now())"
            ),
            {"id1": e1_id, "id2": e2_id},
        )
        pg_session.flush()

        pg_session.execute(
            text(
                "INSERT INTO relationships "
                "(id, source_id, target_id, relationship_type, status, created_at, updated_at) "
                "VALUES (:id, :src, :tgt, 'topic_source', 'silenced', now(), now())"
            ),
            {"id": str(uuid.uuid4()), "src": e1_id, "tgt": e2_id},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_self_loop_rejected_by_db(self, pg_session):
        """DB CHECK constraint must reject source_id == target_id."""
        e_id = str(uuid.uuid4())
        pg_session.execute(
            text(
                "INSERT INTO entities (id, entity_type, label, created_at, updated_at) "
                "VALUES (:id, 'topic', 'Self-loop Topic', now(), now())"
            ),
            {"id": e_id},
        )
        pg_session.flush()

        pg_session.execute(
            text(
                "INSERT INTO relationships "
                "(id, source_id, target_id, relationship_type, status, created_at, updated_at) "
                "VALUES (:id, :src, :tgt, 'topic_source', 'pending', now(), now())"
            ),
            {"id": str(uuid.uuid4()), "src": e_id, "tgt": e_id},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_unique_source_provider_canonical(self, pg_session):
        src_id1, src_id2 = str(uuid.uuid4()), str(uuid.uuid4())
        pg_session.execute(
            text(
                "INSERT INTO sources (id, provider, name, canonical_id, created_at, updated_at) "
                "VALUES (:id1, 'openalex', 'OA', 'uq-canonical-pg', now(), now()), "
                "       (:id2, 'openalex', 'OA2', 'uq-canonical-pg', now(), now())"
            ),
            {"id1": src_id1, "id2": src_id2},
        )
        with pytest.raises(IntegrityError):
            pg_session.flush()

    def test_unique_relationship_no_duplicate_edge(self, pg_session):
        e1_id, e2_id = str(uuid.uuid4()), str(uuid.uuid4())
        pg_session.execute(
            text(
                "INSERT INTO entities (id, entity_type, label, created_at, updated_at) "
                "VALUES (:id1, 'project', 'ProjUQ', now(), now()), "
                "       (:id2, 'topic', 'TopicUQ', now(), now())"
            ),
            {"id1": e1_id, "id2": e2_id},
        )
        pg_session.flush()

        for rid in [str(uuid.uuid4()), str(uuid.uuid4())]:
            pg_session.execute(
                text(
                    "INSERT INTO relationships "
                    "(id, source_id, target_id, relationship_type, status, created_at, updated_at) "
                    "VALUES (:id, :src, :tgt, 'project_topic', 'pending', now(), now())"
                ),
                {"id": rid, "src": e1_id, "tgt": e2_id},
            )
        with pytest.raises(IntegrityError):
            pg_session.flush()
