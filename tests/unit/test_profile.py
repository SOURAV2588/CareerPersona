"""Tests for services.profile — persona system-prompt construction."""

import pytest

from services import profile

pytestmark = pytest.mark.unit


def test_get_summary_reads_resources_summary_md():
    """get_summary() reads the real SUMMARY.md and returns non-empty content mentioning the persona."""
    content = profile.get_summary()
    assert "Sourav Ghosh" in content
    assert content.strip() != ""


def test_get_career_profile_details_reads_career_profile_md():
    """get_career_profile_details() reads the real career profile Markdown and returns non-empty content."""
    content = profile.get_career_profile_details()
    assert content.strip() != ""


def test_get_current_preferences_reads_current_status_md():
    """get_current_preferences() reads the real current-status Markdown and returns non-empty content."""
    content = profile.get_current_preferences()
    assert content.strip() != ""


def test_get_system_prompt_includes_name_summary_and_career_details(monkeypatch):
    """The assembled prompt includes the persona name, summary, career details, preferences, and both tool names."""
    monkeypatch.setattr(profile, "get_summary", lambda: "SUMMARY_MARKER")
    monkeypatch.setattr(profile, "get_career_profile_details", lambda: "CAREER_MARKER")
    monkeypatch.setattr(profile, "get_current_preferences", lambda: "PREFS_MARKER")

    prompt = profile.get_system_prompt_for_profile()

    assert "Sourav Ghosh" in prompt
    assert "SUMMARY_MARKER" in prompt
    assert "CAREER_MARKER" in prompt
    assert "PREFS_MARKER" in prompt
    assert "record_unknown_question" in prompt
    assert "record_user_details" in prompt


def test_get_system_prompt_orders_summary_before_career_details(monkeypatch):
    """The summary section appears before the career-details section in the assembled prompt."""
    monkeypatch.setattr(profile, "get_summary", lambda: "SUMMARY_MARKER")
    monkeypatch.setattr(profile, "get_career_profile_details", lambda: "CAREER_MARKER")
    monkeypatch.setattr(profile, "get_current_preferences", lambda: "PREFS_MARKER")

    prompt = profile.get_system_prompt_for_profile()

    assert prompt.index("SUMMARY_MARKER") < prompt.index("CAREER_MARKER")
    assert prompt.index("CAREER_MARKER") < prompt.index("PREFS_MARKER")
