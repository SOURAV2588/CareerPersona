"""Tests for services.question_store_db — the PostgreSQL-backed question store.

Marked `db` and skipped unless `TEST_DATABASE_URL` is set, since these hit a
real PostgreSQL database rather than mocking it.
"""

import os, pytest

pytestmark = [pytest.mark.db,
              pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),
                                 reason="TEST_DATABASE_URL not set")]


@pytest.fixture(autouse=True)
def clean_table(monkeypatch):
    """Point services.db at the test database and truncate unknown_questions before each test."""
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import services.db as db
    db._pool = None                      # force a fresh pool on the test DSN
    db.init_db()
    with db.get_pool().connection() as conn:
        conn.execute("TRUNCATE unknown_questions RESTART IDENTITY")
    yield