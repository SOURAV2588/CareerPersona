"""Tests for services.profile — persona system-prompt construction.

get_summary()/get_career_profile_details()/get_current_preferences() are
thin wrappers around services.resource_store.get_resource(), which — when
RESOURCES_DATASET_REPO is set in the environment — fetches from the real
Hugging Face Hub. The tests below mock profile.get_resource (the name bound
into this module's namespace) rather than calling through to it, so the
unit layer stays hermetic regardless of what's in the environment/.env.
Real readability of the background files (local or Hub-backed) is checked
by tests/sanity_checks/resource_store_test.py instead.
"""

from unittest.mock import MagicMock

import pytest

from services import profile

pytestmark = pytest.mark.unit


def test_get_summary_fetches_summary_md(monkeypatch):
    """get_summary() fetches SUMMARY.md via the resource store."""
    mock_get_resource = MagicMock(return_value="SUMMARY_CONTENT")
    monkeypatch.setattr(profile, "get_resource", mock_get_resource)

    assert profile.get_summary() == "SUMMARY_CONTENT"
    mock_get_resource.assert_called_once_with("SUMMARY.md")


def test_get_career_profile_details_fetches_career_profile_md(monkeypatch):
    """get_career_profile_details() fetches CAREER_PROFILE.md via the resource store."""
    mock_get_resource = MagicMock(return_value="CAREER_CONTENT")
    monkeypatch.setattr(profile, "get_resource", mock_get_resource)

    assert profile.get_career_profile_details() == "CAREER_CONTENT"
    mock_get_resource.assert_called_once_with("CAREER_PROFILE.md")


def test_get_current_preferences_fetches_current_status_md(monkeypatch):
    """get_current_preferences() fetches CURRENT_STATUS_AND_PREFERENCES.md via the resource store."""
    mock_get_resource = MagicMock(return_value="PREFS_CONTENT")
    monkeypatch.setattr(profile, "get_resource", mock_get_resource)

    assert profile.get_current_preferences() == "PREFS_CONTENT"
    mock_get_resource.assert_called_once_with("CURRENT_STATUS_AND_PREFERENCES.md")


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
