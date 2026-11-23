"""Academic projects, separate from repository diagnosis entities.

Additive deterministic backfill. Populated downgrade refuses implicit data loss.
"""

import re
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "007_academic_projects"
down_revision = "006_discovery_runtime"
branch_labels = None
depends_on = None


def identity(kind, value):
    return uuid5(NAMESPACE_URL, "trama:academic-projects:007:" + kind + ":" + str(value))


def canonical(raw):
    try:
        url = urlsplit(raw or "")
        if (
            url.scheme == "https" and url.netloc == "github.com"
            and not url.query and not url.fragment
            and re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", url.path)
            and all(part not in {".", ".."} for part in url.path.split("/")[1:])
        ):
            return raw.rstrip("/").lower()
    except ValueError:
        pass
    return None


def upgrade():
    op.create_table(
        "academic_projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_academic_project_owner", "academic_projects", ["owner_id", "created_at"])
    op.create_table(
        "project_sources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("academic_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("monitor_id", pg.UUID(as_uuid=True), sa.ForeignKey("source_monitors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="github"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source_type='github'", name="ck_project_source_type"),
    )
    op.create_index("ix_project_source_project", "project_sources", ["project_id"])
    op.create_index("ix_project_source_monitor", "project_sources", ["monitor_id"])
    conn = op.get_bind()
    monitors = {
        row.repo_url: row.id for row in conn.execute(
            sa.text("SELECT id,repo_url FROM source_monitors ORDER BY id")
        ).mappings()
    }
    item_monitors = {
        row.source_item_id: row.id for row in conn.execute(sa.text(
            "SELECT id,source_item_id FROM source_monitors WHERE source_item_id IS NOT NULL"
        )).mappings()
    }
    items = conn.execute(sa.text(
        "SELECT i.id,i.title,i.original_url,i.metadata FROM academic_items i "
        "JOIN sources s ON s.id=i.source_id "
        "WHERE i.item_type='repository' AND s.provider='github' ORDER BY i.id"
    )).mappings().all()
    for item in items:
        if item.id in item_monitors:
            continue
        slug = (item.metadata or {}).get("full_name") or item.title
        url = canonical("https://github.com/" + slug) or canonical(item.original_url)
        if not url:
            continue
        if url not in monitors:
            mid = identity("monitor", url)
            conn.execute(sa.text(
                "INSERT INTO source_monitors(id,repo_url,source_item_id) VALUES (:id,:url,:item)"
            ), {"id": mid, "url": url, "item": item.id})
            monitors[url] = mid
    for raw in conn.execute(sa.text(
        "SELECT DISTINCT repo_url FROM discovery_runs WHERE monitor_id IS NULL ORDER BY repo_url"
    )).scalars():
        url = canonical(raw)
        if url and url not in monitors:
            mid = identity("monitor", url)
            conn.execute(sa.text(
                "INSERT INTO source_monitors(id,repo_url) VALUES (:id,:url)"
            ), {"id": mid, "url": url})
            monitors[url] = mid
    if monitors:
        pid = identity("project", "legacy")
        conn.execute(sa.text(
            "INSERT INTO academic_projects(id,name) VALUES (:id,'Fontes anteriores')"
        ), {"id": pid})
        for mid in sorted(set(monitors.values()), key=str):
            conn.execute(sa.text(
                "INSERT INTO project_sources(id,project_id,monitor_id,source_type) "
                "VALUES (:id,:pid,:mid,'github')"
            ), {"id": identity("binding", mid), "pid": pid, "mid": mid})


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM academic_projects) OR EXISTS(SELECT 1 FROM project_sources) THEN
        RAISE EXCEPTION 'Cannot downgrade populated academic projects without loss; export/archive explicitly';
      END IF;
    END $$""")
    op.drop_table("project_sources")
    op.drop_table("academic_projects")
