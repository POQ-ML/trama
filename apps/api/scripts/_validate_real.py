"""Validation script — runs real ingestion against OpenAlex and GitHub APIs."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.services.ingestion.openalex import OpenAlexConnector
from app.services.ingestion.github import GitHubConnector
from app.services.ingestion.pipeline import IngestionPipeline

DB_URL = os.environ["DATABASE_URL"]
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

# --- OpenAlex ---
print("=== OpenAlex RUN 1 ===")
session = Session()
c1 = OpenAlexConnector(filter_str="doi:10.7717/peerj.4375", max_pages=1, per_page=5, _env={})
r1 = IngestionPipeline(session).run(c1)
print(r1)
session.close()

print("=== OpenAlex RUN 2 (idempotence) ===")
session = Session()
c2 = OpenAlexConnector(filter_str="doi:10.7717/peerj.4375", max_pages=1, per_page=5, _env={})
r2 = IngestionPipeline(session).run(c2)
print(r2)
session.close()

# --- GitHub ---
print("=== GitHub RUN 1 ===")
session = Session()
c3 = GitHubConnector(repos=["octocat/Hello-World"], fetch_readme=True, _env={})
r3 = IngestionPipeline(session).run(c3)
print(r3)
session.close()

print("=== GitHub RUN 2 (idempotence) ===")
session = Session()
c4 = GitHubConnector(repos=["octocat/Hello-World"], fetch_readme=True, _env={})
r4 = IngestionPipeline(session).run(c4)
print(r4)
session.close()

# --- DB verification ---
print("=== DB verification ===")
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT ai.external_id, ai.item_type, ai.title, ai.original_url, ai.captured_at"
        " FROM academic_items ai ORDER BY ai.captured_at DESC LIMIT 5"
    )).fetchall()
    for row in rows:
        print(f"  id={row[0]} type={row[1]} title={str(row[2])[:50]} captured={row[4]}")

    art = conn.execute(text("SELECT COUNT(*) FROM academic_items WHERE item_type='article'")).scalar()
    rep = conn.execute(text("SELECT COUNT(*) FROM academic_items WHERE item_type='repository'")).scalar()
    src = conn.execute(text("SELECT COUNT(*) FROM sources")).scalar()
    print(f"  articles={art} repositories={rep} sources={src}")

print("=== DONE ===")
