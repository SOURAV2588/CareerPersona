"""Tests for services.digest — digest email formatting, sending, and scheduling."""

import datetime as real_datetime
from unittest.mock import MagicMock, patch

import pytest

from services import digest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_scheduler_singleton(monkeypatch):
    """Every test starts as if start_scheduler() had never run in this process."""
    monkeypatch.setattr(digest, "_scheduler", None)


class TestBuildMessageSubjectAndBody:
    def test_formats_single_entry(self):
        entries = [{"question": "What is your stack?", "timestamp": "2026-08-17T10:00:00+00:00"}]

        subject, body = digest._build_message_subject_and_body(entries)

        assert "1 unanswered question(s)" in subject
        assert "1. What is your stack?" in body
        assert "2026-08-17T10:00:00+00:00" in body

    def test_formats_multiple_entries_numbered_in_order(self):
        entries = [
            {"question": "Q1", "timestamp": "t1"},
            {"question": "Q2", "timestamp": "t2"},
            {"question": "Q3", "timestamp": "t3"},
        ]

        subject, body = digest._build_message_subject_and_body(entries)

        assert "3 unanswered question(s)" in subject
        lines = body.splitlines()
        assert any(line.startswith("1. Q1") for line in lines)
        assert any(line.startswith("2. Q2") for line in lines)
        assert any(line.startswith("3. Q3") for line in lines)

    def test_missing_timestamp_falls_back_to_unknown_time(self):
        entries = [{"question": "No timestamp here"}]

        _, body = digest._build_message_subject_and_body(entries)

        assert "(unknown time)" in body

    def test_subject_contains_todays_date(self):
        entries = [{"question": "Q", "timestamp": "t"}]

        subject, _ = digest._build_message_subject_and_body(entries)

        today = real_datetime.datetime.now().strftime("%d %b %Y")
        assert today in subject


class TestSendDailyDigest:
    def test_noop_when_no_pending_questions(self, monkeypatch):
        monkeypatch.setattr(digest, "fetch_pending", MagicMock(return_value=[]))
        fake_mail_util = MagicMock()
        monkeypatch.setattr(digest, "mail_util", fake_mail_util)
        mark_sent = MagicMock()
        monkeypatch.setattr(digest, "mark_sent", mark_sent)

        digest.send_daily_digest()

        fake_mail_util.send_email.assert_not_called()
        mark_sent.assert_not_called()

    def test_sends_email_and_archives_on_success(self, monkeypatch):
        entries = [{"id": 1, "question": "Q1", "timestamp": "t1"}]
        monkeypatch.setattr(digest, "fetch_pending", MagicMock(return_value=entries))
        mark_sent = MagicMock()
        monkeypatch.setattr(digest, "mark_sent", mark_sent)

        fake_mail_util = MagicMock()
        monkeypatch.setattr(digest, "mail_util", fake_mail_util)

        digest.send_daily_digest()

        fake_mail_util.send_email.assert_called_once()
        subject, body = fake_mail_util.send_email.call_args.args
        assert "1 unanswered question(s)" in subject
        assert "Q1" in body
        mark_sent.assert_called_once_with([1])

    def test_send_failure_propagates_and_leaves_pending_unmarked(self, monkeypatch):
        entries = [{"id": 1, "question": "Q1", "timestamp": "t1"}]
        monkeypatch.setattr(digest, "fetch_pending", MagicMock(return_value=entries))
        mark_sent = MagicMock()
        monkeypatch.setattr(digest, "mark_sent", mark_sent)

        fake_mail_util = MagicMock()
        fake_mail_util.send_email.side_effect = RuntimeError("SMTP down")
        monkeypatch.setattr(digest, "mail_util", fake_mail_util)

        with pytest.raises(RuntimeError, match="SMTP down"):
            digest.send_daily_digest()

        mark_sent.assert_not_called()


class TestStartScheduler:
    def test_creates_cron_job_with_expected_schedule(self, monkeypatch):
        fake_scheduler = MagicMock()
        fake_scheduler_cls = MagicMock(return_value=fake_scheduler)

        with patch("apscheduler.schedulers.background.BackgroundScheduler", fake_scheduler_cls):
            digest.start_scheduler()

        fake_scheduler_cls.assert_called_once()
        fake_scheduler.add_job.assert_called_once()
        _, kwargs = fake_scheduler.add_job.call_args
        assert kwargs["trigger"] == "cron"
        assert kwargs["hour"] == 21
        assert kwargs["minute"] == 30
        assert kwargs["id"] == "daily_digest"
        assert kwargs["replace_existing"] is True
        assert str(kwargs["timezone"]) == "Asia/Kolkata"
        fake_scheduler.start.assert_called_once()

    def test_second_call_is_a_noop(self, monkeypatch):
        fake_scheduler_cls = MagicMock(return_value=MagicMock())

        with patch("apscheduler.schedulers.background.BackgroundScheduler", fake_scheduler_cls):
            digest.start_scheduler()
            digest.start_scheduler()

        fake_scheduler_cls.assert_called_once()
