"""Tests for services.mail_utility.MailUtility.

The Gmail service is built lazily, on first use of `.service` (or the first
`send_email()` call), not at construction. googleapiclient.discovery.build is
also stubbed session-wide in tests/conftest.py so nothing here ever touches
the network; individual tests below attach their own fresh mock where they
need to assert on call details.
"""

import base64
from email import message_from_bytes, policy
from unittest.mock import MagicMock

import pytest

from services.mail_utility import MailUtility

pytestmark = pytest.mark.unit


def test_get_credentials_reads_from_environment(monkeypatch):
    monkeypatch.setenv("GMAIL_CLIENT_ID", "cid-123")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "secret-456")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "refresh-789")

    creds = MailUtility.get_credentials()

    assert creds.client_id == "cid-123"
    assert creds.client_secret == "secret-456"
    assert creds.refresh_token == "refresh-789"
    assert creds.token_uri == "https://oauth2.googleapis.com/token"
    assert creds.scopes == ["https://www.googleapis.com/auth/gmail.send"]
    assert creds.token is None


def test_init_does_not_build_service_eagerly(monkeypatch):
    fake_build = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("services.mail_utility.build", fake_build)

    MailUtility()

    fake_build.assert_not_called()


def test_service_is_built_lazily_on_first_use_and_then_cached(monkeypatch):
    fake_build = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("services.mail_utility.build", fake_build)

    mail_util = MailUtility()
    fake_build.assert_not_called()

    first = mail_util.service

    assert fake_build.call_count == 1
    args, kwargs = fake_build.call_args
    assert args[:2] == ("gmail", "v1")
    assert "credentials" in kwargs

    second = mail_util.service

    assert second is first
    assert fake_build.call_count == 1  # not rebuilt on repeat access


def test_send_email_sends_base64_encoded_message_to_configured_recipient(monkeypatch):
    monkeypatch.setenv("GMAIL_RECIPIENT", "recipient@example.com")

    fake_service = MagicMock()
    fake_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg-1"
    }
    monkeypatch.setattr("services.mail_utility.build", MagicMock(return_value=fake_service))

    mail_util = MailUtility()
    mail_util.send_email(subject="Test subject", body="Test body")

    send_mock = fake_service.users.return_value.messages.return_value.send
    send_mock.assert_called_once()
    call_kwargs = send_mock.call_args.kwargs
    assert call_kwargs["userId"] == "me"

    raw = call_kwargs["body"]["raw"]
    decoded = base64.urlsafe_b64decode(raw.encode())
    parsed = message_from_bytes(decoded, policy=policy.default)

    assert parsed["To"] == "recipient@example.com"
    assert parsed["Subject"] == "Test subject"
    assert parsed.get_content().strip() == "Test body"

    fake_service.users.return_value.messages.return_value.send.return_value.execute.assert_called_once()


def test_send_email_raises_clear_error_when_recipient_is_unset(monkeypatch):
    monkeypatch.delenv("GMAIL_RECIPIENT", raising=False)
    monkeypatch.setattr("services.mail_utility.build", MagicMock(return_value=MagicMock()))

    mail_util = MailUtility()

    with pytest.raises(RuntimeError, match="GMAIL_RECIPIENT"):
        mail_util.send_email(subject="Subj", body="Body")


def test_send_email_calls_execute_and_returns_none(monkeypatch, capsys):
    fake_service = MagicMock()
    fake_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg-42"
    }
    monkeypatch.setattr("services.mail_utility.build", MagicMock(return_value=fake_service))

    mail_util = MailUtility()
    result = mail_util.send_email(subject="Subj", body="Body")

    assert result is None
    captured = capsys.readouterr()
    assert "msg-42" in captured.out
