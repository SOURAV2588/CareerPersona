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
    def test_noop_when_no_pending_questions(self, monkeypatch, capsys):
        monkeypatch.setattr(digest, "read_pending", MagicMock(return_value=[]))
        mail_util_cls = MagicMock()
        monkeypatch.setattr(digest, "MailUtility", mail_util_cls)
        clear_pending = MagicMock()
        monkeypatch.setattr(digest, "clear_pending", clear_pending)

        digest.send_daily_digest()

        mail_util_cls.assert_not_called()
        clear_pending.assert_not_called()
        assert "skipping digest" in capsys.readouterr().out

    def test_sends_email_and_archives_on_success(self, monkeypatch):
        entries = [{"question": "Q1", "timestamp": "t1"}]
        monkeypatch.setattr(digest, "read_pending", MagicMock(return_value=entries))
        clear_pending = MagicMock()
        monkeypatch.setattr(digest, "clear_pending", clear_pending)

        fake_instance = MagicMock()
        mail_util_cls = MagicMock(return_value=fake_instance)
        monkeypatch.setattr(digest, "MailUtility", mail_util_cls)

        digest.send_daily_digest()

        fake_instance.send_email.assert_called_once()
        kwargs = fake_instance.send_email.call_args.kwargs
        assert "1 unanswered question(s)" in kwargs["subject"]
        assert "Q1" in kwargs["body"]
        clear_pending.assert_called_once_with(entries)

    def test_leaves_pending_entries_when_send_fails(self, monkeypatch, capsys):
        entries = [{"question": "Q1", "timestamp": "t1"}]
        monkeypatch.setattr(digest, "read_pending", MagicMock(return_value=entries))
        clear_pending = MagicMock()
        monkeypatch.setattr(digest, "clear_pending", clear_pending)

        fake_instance = MagicMock()
        fake_instance.send_email.side_effect = RuntimeError("SMTP down")
        monkeypatch.setattr(digest, "MailUtility", MagicMock(return_value=fake_instance))

        digest.send_daily_digest()

        clear_pending.assert_not_called()
        assert "Failed to send digest email" in capsys.readouterr().out


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
