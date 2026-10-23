"""Shared pytest fixtures for TRAMA API tests.

Two tiers of fixtures:
  - in-memory SQLite engine/session: fast unit tests for model structure,
    constraints (SQLAlchemy-level), and relationship integrity.
    PostgreSQL-specific column types (JSONB, TSVECTOR/TsVectorCompat) are
    handled by registering dialect-specific type fallbacks before create_all.
  - Postgres engine/session (marker: integration): for migration chain,
    pgvector extension, and DB-level CHECK/UNIQUE constraints that SQLite
    either doesn't support or behaves differently on.

Integration tests are automatically skipped when DATABASE_URL is not set
or when the database is unreachable, so the suite stays green in environments
without Docker.
"""

import os
import uuid

import pytest
from sqlalchemy import create_engine, event, text, MetaData, Table, Column, ForeignKey, UniqueConstraint, String, Text
from sqlalchemy.orm import sessionmaker, Session

from app.models import Base, Source, AcademicItem, Entity, Relationship, Evidence


# ---------------------------------------------------------------------------
# SQLite in-memory tier (unit tests)
# ---------------------------------------------------------------------------

def _sqlite_engine():
    """Create an in-memory SQLite engine with FK enforcement enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _sqlite_create_all(engine) -> None:
    """Create all tables on SQLite, remapping Postgres-only types to TEXT/VARCHAR
    while preserving FK and UNIQUE constraints (needed for integrity tests).
    CHECK constraints are intentionally dropped — SQLite ignores them, and the
    DB-level CHECK tests run only against Postgres (integration tier).
    """
    from app.models.types import TsVector

    def _coerce_type(col_type):
        if isinstance(col_type, TsVector):
            return Text()
        name = type(col_type).__name__.upper()
        if name in ("JSONB", "JSON"):
            return Text()
        if name == "UUID":
            return String(36)
        return col_type

    coerced_meta = MetaData()

    for table in Base.metadata.sorted_tables:
        new_cols = []
        for col in table.columns:
            fk_args = [
                ForeignKey(str(fk.target_fullname), ondelete=fk.ondelete)
                for fk in col.foreign_keys
            ]
            new_col = Column(
                col.name,
                _coerce_type(col.type),
                *fk_args,
                primary_key=col.primary_key,
                nullable=col.nullable,
                default=col.default,
                server_default=col.server_default,
                index=col.index,
            )
            new_cols.append(new_col)

        uq_constraints = [
            UniqueConstraint(*[c.name for c in uq.columns], name=uq.name)
            for uq in table.constraints
            if uq.__class__.__name__ == "UniqueConstraint"
        ]

        new_table = Table(table.name, coerced_meta, *new_cols, *uq_constraints)
        # Preserve model partial uniqueness; copying only UniqueConstraint loses
        # discovery's item identities and legacy-label rules on SQLite.
        from sqlalchemy import Index
        for index in table.indexes:
            if index.unique:
                Index(index.name, *[new_table.c[col.name] for col in index.columns],
                      unique=True, sqlite_where=index.dialect_options["sqlite"].get("where"))

    coerced_meta.create_all(engine)


@pytest.fixture(scope="session")
def sqlite_engine():
    engine = _sqlite_engine()
    _sqlite_create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(sqlite_engine) -> Session:
    """Transactional session that rolls back after each test."""
    connection = sqlite_engine.connect()
    transaction = connection.begin()
    SessionFactory = sessionmaker(bind=connection)
    session = SessionFactory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Sample data factories (used across multiple tests)
# ---------------------------------------------------------------------------

def make_source(provider="github", name="Test Repo", canonical_id=None) -> Source:
    return Source(
        provider=provider,
        name=name,
        canonical_id=canonical_id or str(uuid.uuid4()),
        url="https://github.com/test/repo",
    )


def make_item(source: Source, external_id=None, item_type="article") -> AcademicItem:
    return AcademicItem(
        source=source,
        external_id=external_id or str(uuid.uuid4()),
        item_type=item_type,
        title="Test Article",
        content_hash="a" * 64,
    )


def make_entity(entity_type="topic", label=None) -> Entity:
    return Entity(
        entity_type=entity_type,
        label=label or f"{entity_type}-{uuid.uuid4().hex[:8]}",
    )


def make_relationship(source_entity: Entity, target_entity: Entity,
                      rel_type="topic_source") -> Relationship:
    return Relationship(
        source_entity=source_entity,
        target_entity=target_entity,
        relationship_type=rel_type,
    )


# ---------------------------------------------------------------------------
# Postgres integration tier
# ---------------------------------------------------------------------------

def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _pg_available(url: str) -> bool:
    try:
        from sqlalchemy import create_engine as ce
        eng = ce(url, connect_args={"connect_timeout": 3})
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def pg_engine():
    """Postgres engine; skips the test if DB is unavailable."""
    url = _pg_url()
    if not url:
        pytest.skip("No TEST_DATABASE_URL or DATABASE_URL set — skipping integration test")
    if not _pg_available(url):
        pytest.skip("Postgres is unreachable — skipping integration test")

    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_session(pg_engine) -> Session:
    """Transactional Postgres session that rolls back after each test."""
    connection = pg_engine.connect()
    transaction = connection.begin()
    SessionFactory = sessionmaker(bind=connection)
    session = SessionFactory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
