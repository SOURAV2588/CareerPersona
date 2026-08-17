"""Tests for services.profile — persona system-prompt construction."""

from unittest.mock import MagicMock

import pytest

from services import profile

pytestmark = pytest.mark.unit


def test_get_summary_reads_resources_summary_txt():
    content = profile.get_summary()
    assert "Sourav Ghosh" in content
    assert content.strip() != ""


def test_get_linkedin_details_concatenates_page_text(monkeypatch):
    page1 = MagicMock()
    page1.extract_text.return_value = "Page one text. "
    page2 = MagicMock()
    page2.extract_text.return_value = "Page two text."

    fake_reader = MagicMock()
    fake_reader.pages = [page1, page2]
    monkeypatch.setattr(profile, "PdfReader", MagicMock(return_value=fake_reader))

    result = profile.get_linkedin_details()

    assert result == "Page one text. Page two text."


def test_get_linkedin_details_skips_pages_with_no_extractable_text(monkeypatch):
    empty_page = MagicMock()
    empty_page.extract_text.return_value = None
    text_page = MagicMock()
    text_page.extract_text.return_value = "Only this page has text."

    fake_reader = MagicMock()
    fake_reader.pages = [empty_page, text_page]
    monkeypatch.setattr(profile, "PdfReader", MagicMock(return_value=fake_reader))

    result = profile.get_linkedin_details()

    assert result == "Only this page has text."


def test_get_system_prompt_includes_name_summary_and_linkedin(monkeypatch):
    monkeypatch.setattr(profile, "get_summary", lambda: "SUMMARY_MARKER")
    monkeypatch.setattr(profile, "get_linkedin_details", lambda: "LINKEDIN_MARKER")

    prompt = profile.get_system_prompt_for_profile()

    assert "Sourav Ghosh" in prompt
    assert "SUMMARY_MARKER" in prompt
    assert "LINKEDIN_MARKER" in prompt
    assert "record_unknown_question" in prompt
    assert "record_user_details" in prompt


def test_get_system_prompt_orders_summary_before_linkedin(monkeypatch):
    monkeypatch.setattr(profile, "get_summary", lambda: "SUMMARY_MARKER")
    monkeypatch.setattr(profile, "get_linkedin_details", lambda: "LINKEDIN_MARKER")

    prompt = profile.get_system_prompt_for_profile()

    assert prompt.index("SUMMARY_MARKER") < prompt.index("LINKEDIN_MARKER")
