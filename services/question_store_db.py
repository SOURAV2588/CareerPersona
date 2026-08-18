from services.db import get_pool


def store_question(question: str) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO unknown_questions (question) VALUES (%s)",
            (question,),
        )


def fetch_pending() -> list[dict]:
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
    if not ids:
        return
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE unknown_questions SET sent_at = now() WHERE id = ANY(%s)",
            (ids,),
        )