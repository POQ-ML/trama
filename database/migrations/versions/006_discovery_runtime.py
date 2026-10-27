"""Durable discovery queue, one monitor per source, occurrence notifications.

Downgrade refuses populated runtime state; it never drops user observations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "006_discovery_runtime"
down_revision = "005_discovery_contract"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_monitors",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_url", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "source_item_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("academic_items.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column(
            "latest_run_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="RESTRICT"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "interval_seconds", sa.Integer(), nullable=False, server_default="300"
        ),
        sa.Column(
            "reanalyze_on_change", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("current_hash", sa.String(64)),
        sa.Column("analyzed_hash", sa.String(64)),
        sa.Column("etag_repo", sa.String(512)),
        sa.Column("etag_readme", sa.String(512)),
        *[
            sa.Column(n, sa.DateTime(timezone=True))
            for n in [
                "last_checked_at",
                "last_changed_at",
                "next_check_at",
                "lease_expires_at",
            ]
        ],
        sa.Column("lease_token", pg.UUID(as_uuid=True)),
        sa.Column("error_code", sa.String(32)),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "interval_seconds BETWEEN 60 AND 86400", name="ck_monitor_interval"
        ),
        sa.CheckConstraint(
            "failure_count >= 0 AND generation >= 0", name="ck_monitor_counts"
        ),
    )
    op.create_index(
        "ix_monitor_due",
        "source_monitors",
        ["next_check_at"],
        postgresql_where=sa.text("enabled = true"),
    )
    op.add_column("discovery_runs", sa.Column("monitor_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_run_monitor",
        "discovery_runs",
        "source_monitors",
        ["monitor_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "discovery_runs",
        sa.Column("warnings", pg.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("discovery_runs", sa.Column("context_hash", sa.String(64)))
    op.add_column("discovery_runs", sa.Column("claim_token", pg.UUID(as_uuid=True)))
    op.add_column(
        "discovery_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_discovery_queue",
        "discovery_runs",
        ["created_at"],
        postgresql_where=sa.text("status='queued'"),
    )
    op.create_index(
        "uq_discovery_active_monitor",
        "discovery_runs",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text(
            "monitor_id IS NOT NULL AND status IN ('queued','running')"
        ),
    )
    op.create_table(
        "source_changes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "monitor_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("source_monitors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("current_hash", sa.String(64), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column(
            "latest_run_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="RESTRICT"),
        ),
        sa.UniqueConstraint(
            "monitor_id", "generation", name="uq_source_change_occurrence"
        ),
    )
    op.create_table(
        "discovery_requests",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column(
            "run_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.drop_constraint("ck_discovery_error_code", "discovery_runs", type_="check")
    op.create_check_constraint(
        "ck_discovery_error_code",
        "discovery_runs",
        "error_code IS NULL OR error_code IN ('source_unavailable','timeout','invalid_evidence','internal_error','insufficient_context','analysis_warning')",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM source_monitors) OR EXISTS(SELECT 1 FROM source_changes)
         OR EXISTS(SELECT 1 FROM discovery_requests)
         OR EXISTS(SELECT 1 FROM discovery_runs WHERE monitor_id IS NOT NULL OR error_code IN ('insufficient_context','analysis_warning') OR warnings <> '[]'::jsonb) THEN
        RAISE EXCEPTION 'Cannot downgrade runtime state without loss; export/archive explicitly';
      END IF;
    END $$;""")
    op.drop_constraint("ck_discovery_error_code", "discovery_runs", type_="check")
    op.create_check_constraint(
        "ck_discovery_error_code",
        "discovery_runs",
        "error_code IS NULL OR error_code IN ('source_unavailable','timeout','invalid_evidence','internal_error')",
    )
    op.drop_table("discovery_requests")
    op.drop_table("source_changes")
    op.drop_index("uq_discovery_active_monitor", table_name="discovery_runs")
    op.drop_index("ix_discovery_queue", table_name="discovery_runs")
    op.drop_constraint("fk_run_monitor", "discovery_runs", type_="foreignkey")
    for name in [
        "monitor_id",
        "context_hash",
        "claim_token",
        "lease_expires_at",
        "warnings",
    ]:
        op.drop_column("discovery_runs", name)
    op.drop_table("source_monitors")
