import os
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS unknown_questions (
    id         BIGSERIAL   PRIMARY KEY,
    question   TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS unknown_questions_pending_idx
    ON unknown_questions (created_at)
    WHERE sent_at IS NULL;
"""


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=4,
            timeout=10,
            max_idle=300,
            check=ConnectionPool.check_connection,
            open=True,
        )
    return _pool


def init_db() -> None:
    """Idempotent. Called once from app.py's __main__ block."""
    with get_pool().connection() as conn:
        conn.execute(SCHEMA_SQL)