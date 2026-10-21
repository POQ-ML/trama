#!/usr/bin/env python
"""CLI entry point for the TRAMA ingestion pipeline.

Usage examples:
    # OpenAlex — filter by institution (e.g. UFC OpenAlex ID)
    python scripts/ingest.py openalex --filter "institution.id:I4390"

    # OpenAlex — free-text search, limit to 2 pages
    python scripts/ingest.py openalex --query "machine learning" --max-pages 2

    # GitHub — search query
    python scripts/ingest.py github --query "topic:fastapi language:python"

    # GitHub — explicit list of repos
    python scripts/ingest.py github --repos "fastapi/fastapi,tiangolo/sqlmodel"

    # GitHub — all public repos for an org or user
    python scripts/ingest.py github --org "tiangolo"

    # Run both sources
    python scripts/ingest.py all --query "neural networks" --max-pages 1

Environment variables required/optional (never pass secrets as CLI args):
    DATABASE_URL         — PostgreSQL connection string (required)
    OPENALEX_API_KEY     — optional; enables cursor paging
    OPENALEX_EMAIL       — optional; polite pool identification
    GITHUB_TOKEN         — optional; raises rate limit from 60 to 5000 req/h
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Direct execution puts scripts/, rather than the API root, on sys.path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("trama.ingest")


def _require_db() -> "Session":  # type: ignore[name-defined]  # noqa: F821
    """Return a SQLAlchemy Session or exit with a clear message."""
    import os
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error(
            "DATABASE_URL is not set. "
            "Set it to a PostgreSQL connection string before running ingest. "
            "Example: export DATABASE_URL=postgresql+psycopg2://trama:trama@localhost:5432/trama"
        )
        sys.exit(1)

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(db_url, pool_pre_ping=True, future=True)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        return Session()
    except Exception as exc:
        logger.error("Could not connect to database: %s", exc)
        sys.exit(1)


def _run_openalex(args: argparse.Namespace) -> int:
    from app.services.ingestion.openalex import OpenAlexConnector
    from app.services.ingestion.pipeline import IngestionPipeline

    connector = OpenAlexConnector(
        filter_str=getattr(args, "filter", None),
        query=getattr(args, "query", None),
        max_pages=args.max_pages,
        per_page=100,
    )
    session = _require_db()
    try:
        result = IngestionPipeline(session).run(connector)
        print(result)
        return 0 if result.errors == 0 else 1
    finally:
        session.close()


def _run_github(args: argparse.Namespace) -> int:
    from app.services.ingestion.github import GitHubConnector
    from app.services.ingestion.pipeline import IngestionPipeline

    repos_arg = getattr(args, "repos", None)
    repos = [r.strip() for r in repos_arg.split(",")] if repos_arg else []

    connector = GitHubConnector(
        query=getattr(args, "query", None),
        repos=repos or None,
        org_or_user=getattr(args, "org", None),
        max_pages=args.max_pages,
        per_page=100,
    )
    session = _require_db()
    try:
        result = IngestionPipeline(session).run(connector)
        print(result)
        return 0 if result.errors == 0 else 1
    finally:
        session.close()


def _run_all(args: argparse.Namespace) -> int:
    exit_code = 0
    exit_code |= _run_openalex(args)
    exit_code |= _run_github(args)
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="TRAMA ingestion pipeline — OpenAlex and GitHub.",
    )
    sub = parser.add_subparsers(dest="source", required=True)

    # Common options
    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--max-pages", type=int, default=None,
                       help="Maximum pages to fetch (default: no limit)")

    # OpenAlex sub-command
    oa = sub.add_parser("openalex", help="Ingest from OpenAlex")
    _add_common(oa)
    oa.add_argument("--filter", dest="filter", default=None,
                    help="OpenAlex filter expression (e.g. 'institution.id:I4390')")
    oa.add_argument("--query", default=None,
                    help="OpenAlex free-text search query")

    # GitHub sub-command
    gh = sub.add_parser("github", help="Ingest from GitHub")
    _add_common(gh)
    gh.add_argument("--query", default=None,
                    help="GitHub repository search query")
    gh.add_argument("--repos", default=None,
                    help="Comma-separated list of 'owner/repo' strings")
    gh.add_argument("--org", dest="org", default=None,
                    help="Org or user login — fetch all public repos")

    # All sub-command
    all_cmd = sub.add_parser("all", help="Ingest from all sources")
    _add_common(all_cmd)
    all_cmd.add_argument("--query", default=None,
                         help="Query used for both OpenAlex and GitHub")

    args = parser.parse_args()

    dispatch = {"openalex": _run_openalex, "github": _run_github, "all": _run_all}
    fn = dispatch.get(args.source)
    if fn is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(fn(args))


if __name__ == "__main__":
    main()
