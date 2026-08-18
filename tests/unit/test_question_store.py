"""Tests for services.question_store_db — the PostgreSQL-backed question store.

Marked `db` and skipped unless `TEST_DATABASE_URL` is set, since these hit a
real PostgreSQL database rather than mocking it.
"""

import os
from unittest.mock import MagicMock

import pytest

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


def test_question_lifecycle_store_pending_send_marks_sent(monkeypatch):
    """A question stored via the real tool call is fetched as pending, then
    disappears from the pending list once the daily digest "sends" it.

    Exercises the real Postgres round trip end to end (store_question ->
    fetch_pending -> mark_sent, all against TEST_DATABASE_URL) — only the
    Gmail send itself is mocked, so no real email goes out.
    """
    from services import digest
    from services.question_store import fetch_pending
    from services.tools import record_unknown_question

    question = "What's your favorite database?"
    record_unknown_question(question)

    pending = fetch_pending()
    assert [q["question"] for q in pending] == [question]

    mock_send_email = MagicMock()
    monkeypatch.setattr(digest.mail_util, "send_email", mock_send_email)

    digest.send_daily_digest()

    mock_send_email.assert_called_once()
    assert fetch_pending() == []