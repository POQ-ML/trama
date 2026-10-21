"""Add 'repository' to academic_items.item_type CHECK constraint.

Revision ID: 004_add_repository_item_type
Revises: 003_persistence_layer
Create Date: 2026-10-19

Rationale
---------
The ingestion pipeline for GitHub produces repository records that do not fit
any of the existing item_type values ('article', 'course', 'opportunity',
'activity').  The vault (Integration Standards, GitHub Integration) does not
prescribe a type mapping; the closest existing value ('activity') was rejected
because it implies user-generated activity (commits, PRs), not the repository
artefact itself.

Adding 'repository' is the minimal change: it extends the closed enum without
removing any existing value and requires no data migration because the table
is empty at this point (no ingest has run).

The downgrade removes the 'repository' row (or raises if rows with that type
exist — dev/CI use only).

Compatibility: backwards-compatible for existing rows (none use 'repository').
Reversibility: reversible if no 'repository' rows exist; otherwise raises.
"""

revision = "004_add_repository_item_type"
down_revision = "003_persistence_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op

    # PostgreSQL does not support ALTER TABLE ... ADD CHECK with ALTER CONSTRAINT,
    # so we must drop the old check and add a new one.
    op.drop_constraint("ck_academic_item_type_valid", "academic_items", type_="check")
    op.create_check_constraint(
        "ck_academic_item_type_valid",
        "academic_items",
        "item_type IN ('article', 'course', 'opportunity', 'activity', 'repository')",
    )


def downgrade() -> None:
    from alembic import op

    # Guard: refuse downgrade if 'repository' rows exist to avoid silent data loss.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM academic_items WHERE item_type = 'repository') THEN
                RAISE EXCEPTION
                    'Cannot downgrade: academic_items contains rows with item_type=''repository''. '
                    'Remove or retype those rows before downgrading.';
            END IF;
        END $$;
        """
    )
    op.drop_constraint("ck_academic_item_type_valid", "academic_items", type_="check")
    op.create_check_constraint(
        "ck_academic_item_type_valid",
        "academic_items",
        "item_type IN ('article', 'course', 'opportunity', 'activity')",
    )
