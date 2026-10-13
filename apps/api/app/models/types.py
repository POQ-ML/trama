"""Custom SQLAlchemy column types shared across models.

These are infrastructure types — not domain types. They exist to bridge
PostgreSQL-specific column types with SQLite for unit tests.
"""

from sqlalchemy.types import UserDefinedType


class TsVector(UserDefinedType):
    """Renders as TSVECTOR on PostgreSQL, TEXT on SQLite (unit-test compat).

    Usage:
        search_vector: Mapped[object | None] = mapped_column(TsVector, nullable=True)

    On Postgres this produces a real TSVECTOR column with GIN index support.
    On SQLite (tests) it degrades to TEXT, which is enough to validate
    model structure and ORM behaviour without requiring a live DB.
    """

    cache_ok = True

    def get_col_spec(self, **kw) -> str:  # type: ignore[override]
        return "TSVECTOR"

    def result_processor(self, dialect, coltype):
        return None
