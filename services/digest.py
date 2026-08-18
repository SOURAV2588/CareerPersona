"""Daily email digest of unanswered questions.

A background scheduler fires :func:`send_daily_digest` at 9:30 PM IST. If
any questions were recorded since the last successful send, they are
emailed via the Gmail API and marked sent; if there are none, no email is
sent. The scheduler itself (:func:`start_scheduler`) is started from
``app.py``'s ``__main__`` block, but that call is commented out by default —
see ``CLAUDE.md``.
"""

from datetime import datetime

from dotenv import load_dotenv

from services.mail_utility import mail_util
from services.question_store_db import fetch_pending, mark_sent

load_dotenv(override=True)
_scheduler = None


def send_daily_digest() -> None:
    """Email and archive any questions still pending, if there are any.

    Fetches pending questions via
    :func:`services.question_store_db.fetch_pending`. If none are pending,
    returns without sending an email. Otherwise builds the digest message,
    sends it through :data:`services.mail_utility.mail_util`, and only then
    marks the sent questions via
    :func:`services.question_store_db.mark_sent` — if sending raises, no
    question is marked sent, so nothing is lost.

    :return: None
    """
    pending = fetch_pending()
    if not pending:
        return

    subject, body = _build_message_subject_and_body(pending)

    mail_util.send_email(subject, body)      # raises on failure → nothing marked
    mark_sent([q["id"] for q in pending])


def _build_message_subject_and_body(entries):
    """Format pending questions into a digest email subject and body.

    :param entries: Pending question records, each with at least a
        ``question`` key and optionally a ``timestamp`` key.
    :type entries: list[dict]
    :return: A ``(subject, body)`` tuple. The subject includes the entry
        count and today's date; the body is a numbered plain-text list.
    :rtype: tuple[str, str]
    """
    lines = ["Unanswered questions from your Career Persona:\n"]
    for i, entry in enumerate(entries, 1):
        lines.append(f"{i}. {entry['question']}  ({entry.get('timestamp', 'unknown time')})")
    body = "\n".join(lines)

    today = datetime.now().strftime("%d %b %Y")
    subject = f"Career Persona — {len(entries)} unanswered question(s) [{today}]"
    return subject, body


def start_scheduler():
    """Start the background scheduler that emails the digest at 9:30 PM IST.

    Creates an :class:`apscheduler.schedulers.background.BackgroundScheduler`
    with a single cron job (id ``"daily_digest"``, 21:30 ``Asia/Kolkata``)
    running :func:`send_daily_digest`, and starts it. Idempotent: guarded by
    the module-level ``_scheduler`` singleton, so calling this more than
    once is a no-op after the first call.

    :return: None
    """
    global _scheduler
    if _scheduler is not None:
        return

    from apscheduler.schedulers.background import BackgroundScheduler
    import pytz

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        send_daily_digest,
        trigger="cron",
        hour=21,
        minute=30,
        timezone=pytz.timezone("Asia/Kolkata"),
        id="daily_digest",
        replace_existing=True,
    )
    _scheduler.start()
    print("Daily digest scheduler started (9:30 PM IST).", flush=True)


if __name__ == "__main__":
    # Manual test: send (or skip) the digest immediately.
    send_daily_digest()
