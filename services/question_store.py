"""PostgreSQL-backed storage for unanswered questions.

The database-backed counterpart to :mod:`services.question_store` (which
uses a JSONL file). Questions are recorded via :func:`store_question` as
they come in from the chat handler, and read/cleared by the daily digest
job via :func:`fetch_pending` and :func:`mark_sent`. All access goes
through the connection pool from :mod:`services.db`.
"""

from services.db import get_pool


def store_question(question: str) -> None:
    """Insert a new unanswered question into the ``unknown_questions`` table.

    :param question: The unanswered question to store.
    :type question: str
    :return: None
    """
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO unknown_questions (question) VALUES (%s)",
            (question,),
        )


def fetch_pending() -> list[dict]:
    """Fetch all questions that have not yet been sent in a digest.

    Selects rows from ``unknown_questions`` where ``sent_at IS NULL``,
    ordered by ``created_at``.

    :return: One dict per pending question, with ``id``, ``question``, and
        ``timestamp`` (ISO-8601 string) keys.
    :rtype: list[dict]
    """
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, question, created_at"
            "  FROM unknown_questions"
            " WHERE sent_at IS NULL"
            " ORDER BY created_at"
        ).fetchall()
    return [
        {"id": r[0], "question": r[1], "timestamp": r[2].isoformat()}
        for r in rows
    ]


def mark_sent(ids: list[int]) -> None:
    """Mark the given questions as sent by setting their ``sent_at`` timestamp.

    :param ids: Primary keys of the ``unknown_questions`` rows to mark
        sent. If empty, no query is run.
    :type ids: list[int]
    :return: None
    """
    if not ids:
        return
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE unknown_questions SET sent_at = now() WHERE id = ANY(%s)",
            (ids,),
        )