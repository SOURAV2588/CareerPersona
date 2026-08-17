"""Tests for services.tools — the two model-callable tools and their JSON schemas."""

from unittest.mock import MagicMock

import pytest

from services import tools

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def fresh_mail_util(monkeypatch):
    """Replace the module-level MailUtility singleton with a clean mock per test."""
    mock_mail_util = MagicMock()
    monkeypatch.setattr(tools, "mail_util", mock_mail_util)
    return mock_mail_util


@pytest.fixture(autouse=True)
def fresh_store_question(monkeypatch):
    mock_store_question = MagicMock()
    monkeypatch.setattr(tools, "store_question", mock_store_question)
    return mock_store_question


class TestRecordUserDetails:
    def test_sends_email_with_provided_details(self, fresh_mail_util):
        result = tools.record_user_details(
            email="visitor@example.com", name="Ada Lovelace", notes="wants to collaborate"
        )

        fresh_mail_util.send_email.assert_called_once()
        call_args = fresh_mail_util.send_email.call_args
        subject, body = call_args.args
        assert "interest received" in subject
        assert "visitor@example.com" in body
        assert "Ada Lovelace" in body
        assert "wants to collaborate" in body
        assert result == {"recorded": "ok"}

    def test_uses_defaults_when_name_and_notes_omitted(self, fresh_mail_util):
        tools.record_user_details(email="visitor@example.com")

        _, body = fresh_mail_util.send_email.call_args.args
        assert "Name not provided" in body
        assert "not provided" in body

    def test_subject_contains_todays_date(self, fresh_mail_util):
        import datetime

        tools.record_user_details(email="visitor@example.com")

        subject, _ = fresh_mail_util.send_email.call_args.args
        today = datetime.datetime.now().strftime("%d %b %Y")
        assert today in subject


class TestRecordUnknownQuestion:
    def test_stores_question_with_recording_prefix(self, fresh_store_question):
        result = tools.record_unknown_question("What is the meaning of life?")

        fresh_store_question.assert_called_once_with(
            "Recording unknown question: What is the meaning of life?"
        )
        assert result == {"recorded": "ok"}


class TestToolSchemas:
    def test_tools_list_contains_both_schemas(self):
        names = {t["name"] for t in tools.tools}
        assert names == {"record_user_details", "record_unknown_question"}

    def test_record_user_details_schema_requires_only_email(self):
        schema = tools.record_user_details_json["input_schema"]
        assert schema["required"] == ["email"]
        assert set(schema["properties"]) == {"email", "name", "notes"}
        assert schema["additionalProperties"] is False

    def test_record_unknown_question_schema_requires_question(self):
        schema = tools.record_unknown_question_json["input_schema"]
        assert schema["required"] == ["question"]
        assert set(schema["properties"]) == {"question"}
        assert schema["additionalProperties"] is False
