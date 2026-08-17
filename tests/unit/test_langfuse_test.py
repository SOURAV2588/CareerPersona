"""Tests for services.langfuse_test — the manual Langfuse connectivity check."""

from unittest.mock import MagicMock

from services import langfuse_test


def test_test_generation_returns_expected_greeting():
    assert langfuse_test.test_generation() == "Hello World from Langfuse"


def test_verify_connection_flushes_the_langfuse_client(monkeypatch, capsys):
    fake_client = MagicMock()
    monkeypatch.setattr(langfuse_test, "get_client", MagicMock(return_value=fake_client))
    generation_spy = MagicMock(wraps=langfuse_test.test_generation)
    monkeypatch.setattr(langfuse_test, "test_generation", generation_spy)

    langfuse_test.verify_connection()

    generation_spy.assert_called_once()
    fake_client.flush.assert_called_once()
    out = capsys.readouterr().out
    assert "successfully" in out
