"""Persistence layer — sources, academic_items, entities, relationships, evidences.

Revision ID: 003_persistence_layer
Revises: 002_pgvector
Create Date: 2026-10-12

Creates the five core tables for TRAMA's MVP persistence layer:

  sources          — integration instances (GitHub, Moodle, OpenAlex)
  academic_items   — normalised records imported from a source
  entities         — canonical map nodes (person/project/topic/event/source)
  relationships    — typed edges between entities (PD-0002: 3 types)
  evidences        — traceable material supporting a relationship

Design decisions reflected here:
- All PKs are UUIDs (gen_random_uuid() server-side default, pgcrypto already
  enabled by migration 001).
- All timestamps use TIMESTAMPTZ (timezone=True) for unambiguous comparison.
- CHECK constraints enforce closed enums for provider, item_type, entity_type,
  relationship_type, and status directly in the database.
- Self-referential edges (source_id = target_id) are blocked by CHECK.
- Unique constraints prevent semantic duplicates at the data layer.
- GIN index on academic_items.search_vector for full-text fallback (ADR-0004).
- sources.owner_id is a nullable FK to users — prepared for future auth
  association without enforcing it prematurely.
- No vector column added: embedding dimension is an open question (ADR-0004).
  A future migration will add it once the model/dimension is decided.

Downgrade drops tables in reverse dependency order (no data loss if empty;
downgrade is intended for dev/CI use only).
"""

revision = "003_persistence_layer"
down_revision = "002_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    # ------------------------------------------------------------------
    # sources
    # ------------------------------------------------------------------
    op.create_table(
        "sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("canonical_id", sa.String(512), nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('github', 'moodle', 'openalex')",
            name="ck_source_provider_valid",
        ),
        sa.UniqueConstraint("provider", "canonical_id", name="uq_source_provider_canonical"),
    )
    op.create_index("ix_sources_owner_id", "sources", ["owner_id"])

    # ------------------------------------------------------------------
    # academic_items
    # ------------------------------------------------------------------
    op.create_table(
        "academic_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(512), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("original_url", sa.Text, nullable=True),
        sa.Column("original_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        # tsvector column for full-text search fallback (ADR-0004).
        # Populated by the service layer or a DB trigger (not set here).
        sa.Column("search_vector", postgresql.TSVECTOR, nullable=True),
        sa.CheckConstraint(
            "item_type IN ('article', 'course', 'opportunity', 'activity')",
            name="ck_academic_item_type_valid",
        ),
        sa.UniqueConstraint(
            "source_id", "external_id", name="uq_academic_item_source_external"
        ),
    )
    op.create_index("ix_academic_items_source_id", "academic_items", ["source_id"])
    op.create_index(
        "ix_academic_items_fts",
        "academic_items",
        ["search_vector"],
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # entities
    # ------------------------------------------------------------------
    op.create_table(
        "entities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column(
            "origin_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('person', 'project', 'topic', 'event', 'source')",
            name="ck_entity_type_valid",
        ),
        sa.UniqueConstraint("entity_type", "label", name="uq_entity_type_label"),
    )
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])
    op.create_index("ix_entities_origin_item_id", "entities", ["origin_item_id"])

    # ------------------------------------------------------------------
    # relationships
    # ------------------------------------------------------------------
    op.create_table(
        "relationships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("justification", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # No self-loops.
        sa.CheckConstraint("source_id <> target_id", name="ck_relationship_no_self"),
        # Closed enums (PD-0002).
        sa.CheckConstraint(
            "relationship_type IN ('topic_source', 'project_event', 'project_topic')",
            name="ck_relationship_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_relationship_status_valid",
        ),
        # Semantic uniqueness: same typed edge cannot appear twice.
        sa.UniqueConstraint(
            "source_id",
            "target_id",
            "relationship_type",
            name="uq_relationship_source_target_type",
        ),
    )
    op.create_index("ix_relationships_source_id", "relationships", ["source_id"])
    op.create_index("ix_relationships_target_id", "relationships", ["target_id"])
    op.create_index("ix_relationships_status", "relationships", ["status"])

    # ------------------------------------------------------------------
    # evidences
    # ------------------------------------------------------------------
    op.create_table(
        "evidences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "relationship_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "origin_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reference_url", sa.Text, nullable=True),
        sa.Column("locator", sa.Text, nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("capture_version", sa.String(255), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_evidences_relationship_id", "evidences", ["relationship_id"])
    op.create_index("ix_evidences_origin_item_id", "evidences", ["origin_item_id"])


def downgrade() -> None:
    from alembic import op

    # Drop in reverse dependency order.
    op.drop_table("evidences")
    op.drop_table("relationships")
    op.drop_table("entities")
    op.drop_table("academic_items")
    op.drop_table("sources")
