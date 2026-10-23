"""Discovery contract: stable article/project identities, runs and evidence snapshots.

No legacy rows are deleted/merged. Ambiguous preexisting item identities stop
upgrade transactionally. Downgrade refuses new data or labels unrepresentable
by 004 rather than silently destroying data.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "005_discovery_contract"
down_revision = "004_add_repository_item_type"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM entities WHERE entity_type='project' AND origin_item_id IS NOT NULL
                 GROUP BY origin_item_id HAVING count(*)>1) THEN
        RAISE EXCEPTION 'Ambiguous legacy project item identity; resolve explicitly before migration 005';
      END IF;
    END $$;
    """)
    op.drop_constraint("ck_entity_type_valid", "entities", type_="check")
    op.create_check_constraint(
        "ck_entity_type_valid",
        "entities",
        "entity_type IN ('person','project','topic','event','source','article')",
    )
    op.create_check_constraint(
        "ck_article_origin",
        "entities",
        "entity_type <> 'article' OR origin_item_id IS NOT NULL",
    )
    op.drop_constraint("uq_entity_type_label", "entities", type_="unique")
    op.create_index(
        "uq_entity_legacy_label",
        "entities",
        ["entity_type", "label"],
        unique=True,
        postgresql_where=sa.text(
            "entity_type NOT IN ('project','article') OR origin_item_id IS NULL"
        ),
    )
    op.create_index(
        "uq_entity_item_identity",
        "entities",
        ["entity_type", "origin_item_id"],
        unique=True,
        postgresql_where=sa.text(
            "entity_type IN ('project','article') AND origin_item_id IS NOT NULL"
        ),
    )
    op.drop_constraint("ck_relationship_type_valid", "relationships", type_="check")
    op.create_check_constraint(
        "ck_relationship_type_valid",
        "relationships",
        "relationship_type IN ('topic_source','project_event','project_topic','project_article')",
    )
    op.add_column("evidences", sa.Column("snapshot_key", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_evidence_snapshot", "evidences", ["relationship_id", "snapshot_key"]
    )
    op.create_table(
        "discovery_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column(
            "project_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','partial','failed')",
            name="ck_discovery_status",
        ),
        sa.CheckConstraint("deadline_at > created_at", name="ck_discovery_deadline"),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN ('source_unavailable','timeout','invalid_evidence','internal_error')",
            name="ck_discovery_error_code",
        ),
        sa.CheckConstraint(
            "(status IN ('partial','failed')) = (error_code IS NOT NULL)",
            name="ck_discovery_error_state",
        ),
        sa.CheckConstraint(
            "(status IN ('completed','partial','failed')) = (finished_at IS NOT NULL)",
            name="ck_discovery_finished",
        ),
    )
    op.create_table(
        "discovery_suggestions",
        sa.Column(
            "run_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "relationship_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("relationships.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "repo_evidence_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("evidences.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "article_evidence_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("evidences.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("topics", pg.JSONB(), nullable=False),
    )
    op.execute("""
    CREATE FUNCTION discovery_entity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='UPDATE' AND OLD.entity_type IN ('project','article') AND OLD.origin_item_id IS NOT NULL
         AND (NEW.origin_item_id IS DISTINCT FROM OLD.origin_item_id OR NEW.entity_type <> OLD.entity_type) THEN
        RAISE EXCEPTION 'Canonical item identity is immutable';
      END IF;
      IF NEW.entity_type='article' AND NOT EXISTS(SELECT 1 FROM academic_items WHERE id=NEW.origin_item_id AND item_type='article') THEN
        RAISE EXCEPTION 'Article entity requires an article item';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER discovery_entity_guard BEFORE INSERT OR UPDATE ON entities
      FOR EACH ROW EXECUTE FUNCTION discovery_entity_guard();

    CREATE FUNCTION discovery_pair_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.relationship_type='project_article' AND NOT EXISTS(
        SELECT 1 FROM entities p JOIN entities a ON a.id=NEW.target_id
        WHERE p.id=NEW.source_id AND p.entity_type='project' AND a.entity_type='article'
      ) THEN RAISE EXCEPTION 'project_article requires project -> article'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER discovery_pair_guard BEFORE INSERT OR UPDATE ON relationships
      FOR EACH ROW EXECUTE FUNCTION discovery_pair_guard();

    CREATE FUNCTION discovery_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.snapshot_key IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Discovery evidence snapshots are immutable';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER discovery_evidence_guard BEFORE UPDATE ON evidences
      FOR EACH ROW EXECUTE FUNCTION discovery_evidence_guard();
    """)


def downgrade():
    # All refusal checks run BEFORE DDL. Alembic also wraps PostgreSQL DDL in a transaction.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM discovery_runs) OR EXISTS(SELECT 1 FROM discovery_suggestions)
         OR EXISTS(SELECT 1 FROM entities WHERE entity_type='article')
         OR EXISTS(SELECT 1 FROM relationships WHERE relationship_type='project_article')
         OR EXISTS(SELECT 1 FROM evidences WHERE snapshot_key IS NOT NULL)
         OR EXISTS(SELECT 1 FROM entities GROUP BY entity_type,label HAVING count(*)>1) THEN
        RAISE EXCEPTION 'Cannot downgrade discovery contract without loss; export/archive new data explicitly first';
      END IF;
    END $$;
    DROP TRIGGER discovery_evidence_guard ON evidences;
    DROP FUNCTION discovery_evidence_guard();
    DROP TRIGGER discovery_pair_guard ON relationships;
    DROP FUNCTION discovery_pair_guard();
    DROP TRIGGER discovery_entity_guard ON entities;
    DROP FUNCTION discovery_entity_guard();
    """)
    op.drop_table("discovery_suggestions")
    op.drop_table("discovery_runs")
    op.drop_constraint("uq_evidence_snapshot", "evidences", type_="unique")
    op.drop_column("evidences", "snapshot_key")
    op.drop_constraint("ck_relationship_type_valid", "relationships", type_="check")
    op.create_check_constraint(
        "ck_relationship_type_valid",
        "relationships",
        "relationship_type IN ('topic_source','project_event','project_topic')",
    )
    op.drop_index("uq_entity_item_identity", table_name="entities")
    op.drop_index("uq_entity_legacy_label", table_name="entities")
    op.create_unique_constraint(
        "uq_entity_type_label", "entities", ["entity_type", "label"]
    )
    op.drop_constraint("ck_article_origin", "entities", type_="check")
    op.drop_constraint("ck_entity_type_valid", "entities", type_="check")
    op.create_check_constraint(
        "ck_entity_type_valid",
        "entities",
        "entity_type IN ('person','project','topic','event','source')",
    )
