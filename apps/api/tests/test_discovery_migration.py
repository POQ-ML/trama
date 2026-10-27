"""Real PostgreSQL legacy/upgrade/downgrade checks in an explicitly disposable DB."""

from pathlib import Path
import os
from uuid import uuid4
from unittest.mock import patch

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError


@pytest.fixture
def migration_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Disposable TEST_DATABASE_URL required")
    assert make_url(url).database.startswith("qa_discovery_")
    engine = create_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with patch("logging.config.fileConfig"):
        command.upgrade(config, "head")
        command.downgrade(config, "004_add_repository_item_type")
    yield engine, config
    with patch("logging.config.fileConfig"):
        command.upgrade(config, "head")
    engine.dispose()


def test_legacy_rows_preserved_and_empty_downgrade_roundtrip(migration_engine):
    engine, config = migration_engine
    source, item, project, topic, rel, evidence = [uuid4() for _ in range(6)]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources(id,provider,name,canonical_id) VALUES(:id,'github','Legacy','legacy005')"
            ),
            {"id": source},
        )
        conn.execute(
            text(
                "INSERT INTO academic_items(id,source_id,external_id,item_type,title,content_hash) VALUES(:id,:src,'legacy','repository','old name',:hash)"
            ),
            {"id": item, "src": source, "hash": "a" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO entities(id,entity_type,label,origin_item_id) VALUES(:id,'project','legacy project',:item)"
            ),
            {"id": project, "item": item},
        )
        conn.execute(
            text(
                "INSERT INTO entities(id,entity_type,label) VALUES(:id,'topic','legacy topic')"
            ),
            {"id": topic},
        )
        conn.execute(
            text(
                "INSERT INTO relationships(id,source_id,target_id,relationship_type) VALUES(:id,:src,:dst,'project_topic')"
            ),
            {"id": rel, "src": project, "dst": topic},
        )
        conn.execute(
            text(
                "INSERT INTO evidences(id,relationship_id,origin_item_id,excerpt) VALUES(:id,:rel,:item,'legacy excerpt')"
            ),
            {"id": evidence, "rel": rel, "item": item},
        )
    try:
        with patch("logging.config.fileConfig"):
            command.upgrade(config, "head")
        with engine.begin() as conn:
            assert (
                conn.scalar(
                    text("SELECT excerpt FROM evidences WHERE id=:id"), {"id": evidence}
                )
                == "legacy excerpt"
            )
            assert (
                conn.scalar(
                    text("SELECT source_id FROM relationships WHERE id=:id"),
                    {"id": rel},
                )
                == project
            )
            conn.execute(
                text("UPDATE entities SET label='renamed legacy' WHERE id=:id"),
                {"id": project},
            )
        with patch("logging.config.fileConfig"):
            command.downgrade(config, "004_add_repository_item_type")
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT label FROM entities WHERE id=:id"), {"id": project}
                )
                == "renamed legacy"
            )
            assert (
                conn.scalar(
                    text("SELECT excerpt FROM evidences WHERE id=:id"), {"id": evidence}
                )
                == "legacy excerpt"
            )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM relationships WHERE id=:id"), {"id": rel})
            conn.execute(
                text("DELETE FROM entities WHERE id IN (:project,:topic)"),
                {"project": project, "topic": topic},
            )
            conn.execute(text("DELETE FROM academic_items WHERE id=:id"), {"id": item})
            conn.execute(text("DELETE FROM sources WHERE id=:id"), {"id": source})


def test_ambiguous_legacy_identity_refuses_without_modifications(migration_engine):
    engine, config = migration_engine
    source, item, one, two = [uuid4() for _ in range(4)]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources(id,provider,name,canonical_id) VALUES(:id,'github','Legacy','legacy005')"
            ),
            {"id": source},
        )
        conn.execute(
            text(
                "INSERT INTO academic_items(id,source_id,external_id,item_type,title,content_hash) VALUES(:id,:src,'legacy','repository','old',:hash)"
            ),
            {"id": item, "src": source, "hash": "a" * 64},
        )
        for identity, label in [(one, "legacy1"), (two, "legacy2")]:
            conn.execute(
                text(
                    "INSERT INTO entities(id,entity_type,label,origin_item_id) VALUES(:id,'project',:label,:item)"
                ),
                {"id": identity, "label": label, "item": item},
            )
    try:
        with pytest.raises(DBAPIError), patch("logging.config.fileConfig"):
            command.upgrade(config, "head")
        with engine.connect() as conn:
            assert (
                conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "004_add_repository_item_type"
            )
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM entities WHERE origin_item_id=:id"),
                    {"id": item},
                )
                == 2
            )
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM entities WHERE id IN (:one,:two)"),
                {"one": one, "two": two},
            )
            conn.execute(text("DELETE FROM academic_items WHERE id=:id"), {"id": item})
            conn.execute(text("DELETE FROM sources WHERE id=:id"), {"id": source})


def test_downgrade_refuses_new_data_without_loss(migration_engine):
    engine, config = migration_engine
    with patch("logging.config.fileConfig"):
        command.upgrade(config, "head")
    identity = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO discovery_runs(id,repo_url,deadline_at) VALUES(:id,'https://github.com/a/b',now()+interval '1 minute')"
            ),
            {"id": identity},
        )
    try:
        with pytest.raises(DBAPIError), patch("logging.config.fileConfig"):
            command.downgrade(config, "004_add_repository_item_type")
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM discovery_runs WHERE id=:id"),
                    {"id": identity},
                )
                == 1
            )
            assert (
                conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "006_discovery_runtime"
            )
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM discovery_runs WHERE id=:id"), {"id": identity}
            )
