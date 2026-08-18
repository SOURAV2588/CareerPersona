"""PostgreSQL connection pool and schema management.

Owns the single, lazily-created :class:`psycopg_pool.ConnectionPool` used
by :mod:`services.question_store_db` to persist unanswered questions, and
the DDL that creates the ``unknown_questions`` table on startup.
"""

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
    """Return the module-level connection pool, creating it on first use.

    The pool is built from the ``DATABASE_URL`` environment variable the
    first time this is called, then cached in the module-level ``_pool``
    for the lifetime of the process.

    :raises RuntimeError: If the ``DATABASE_URL`` environment variable is
        not set.
    :return: The shared connection pool.
    :rtype: psycopg_pool.ConnectionPool
    """
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
    """Create the ``unknown_questions`` table and its index if missing.

    Idempotent (``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT
    EXISTS``), so it is safe to call on every startup. Called once from
    ``app.py``'s ``__main__`` block.

    :return: None
    """
    with get_pool().connection() as conn:
        conn.execute(SCHEMA_SQL)