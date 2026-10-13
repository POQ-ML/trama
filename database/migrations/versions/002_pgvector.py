"""Enable pgvector extension.

Revision ID: 002_pgvector
Revises: 001_initial
Create Date: 2026-10-12

Enables the pgvector extension in PostgreSQL. The docker-compose service
uses pgvector/pgvector:pg16, which ships the shared library; this migration
makes the extension available in the target database.

The embedding dimension and model are NOT decided yet (ADR-0004 open Q).
This migration only ensures the extension is present so that a future
migration can add vector columns without a separate infra step.

Downgrade: DROP EXTENSION is intentionally left as a no-op comment because
removing pgvector after data exists would require dropping all vector columns
first. A safe downgrade requires a dedicated decision; log the intent only.
"""

revision = "002_pgvector"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    # CREATE EXTENSION IF NOT EXISTS is idempotent and safe on re-runs.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Intentionally not dropping the extension on downgrade: dropping vector
    # after data exists requires all vector columns to be removed first.
    # If a clean teardown is needed, drop vector columns in a later migration
    # before running this downgrade.
    pass
