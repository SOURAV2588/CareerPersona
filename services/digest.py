# Daily email digest of unanswered questions.
#
# A background scheduler fires send_daily_digest() at 9:30 PM IST. If any
# questions were recorded since the last successful send, they are emailed via
# the Gmail API and marked sent; if there are none, no email is sent.

from datetime import datetime

from dotenv import load_dotenv

from services.mail_utility import mail_util
from services.question_store_db import fetch_pending, mark_sent

load_dotenv(override=True)
_scheduler = None


def send_daily_digest() -> None:
    pending = fetch_pending()
    if not pending:
        return

    subject, body = _build_message_subject_and_body(pending)

    mail_util.send_email(subject, body)      # raises on failure → nothing marked
    mark_sent([q["id"] for q in pending])


def _build_message_subject_and_body(entries):
    lines = ["Unanswered questions from your Career Persona:\n"]
    for i, entry in enumerate(entries, 1):
        lines.append(f"{i}. {entry['question']}  ({entry.get('timestamp', 'unknown time')})")
    body = "\n".join(lines)

    today = datetime.now().strftime("%d %b %Y")
    subject = f"Career Persona — {len(entries)} unanswered question(s) [{today}]"
    return subject, body


def start_scheduler():
    """Start the background scheduler that emails the digest at 9:30 PM IST.

    Safe to call more than once; the job is created only on the first call.
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
