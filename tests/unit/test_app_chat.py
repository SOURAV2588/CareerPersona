"""Tests for app.chat() — the tool-use chat loop.

app.client is a real anthropic.Anthropic() instance constructed at import
time; every test below replaces its .messages.create with a MagicMock so no
network call is ever made. The system-prompt builder is stubbed too, since it
otherwise reads the real résumé PDF/summary.txt on every call.

For app.handle_tool_calls() itself, see test_app_tool_dispatch.py.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app

pytestmark = pytest.mark.unit


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name, arguments, tool_id="tool_1"):
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=tool_id)


def fake_response(stop_reason, content):
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=SimpleNamespace())


@pytest.fixture(autouse=True)
def stub_system_prompt(monkeypatch):
    monkeypatch.setattr(app, "get_system_prompt_for_profile", lambda: "STUB SYSTEM PROMPT")


@pytest.fixture
def mock_create(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(app.client.messages, "create", mock)
    return mock


class TestSimpleReply:
    def test_returns_concatenated_text_from_final_response(self, mock_create):
        mock_create.return_value = fake_response("end_turn", [text_block("Hello, I'm Sourav.")])

        reply = app.chat("Hi there", [])

        assert reply == "Hello, I'm Sourav."
        mock_create.assert_called_once()

    def test_sends_only_role_and_content_for_history_entries(self, mock_create):
        mock_create.return_value = fake_response("end_turn", [text_block("ok")])
        history = [
            {"role": "user", "content": "Hi", "metadata": {"x": 1}, "options": {}},
            {"role": "assistant", "content": "Hello!", "metadata": None},
        ]

        app.chat("New message", history)

        sent_messages = mock_create.call_args.kwargs["messages"]
        assert sent_messages == [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "New message"},
        ]

    def test_passes_tools_and_cached_system_prompt(self, mock_create):
        mock_create.return_value = fake_response("end_turn", [text_block("ok")])

        app.chat("Hi", [])

        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] is app.tools
        assert kwargs["system"] == [
            {
                "type": "text",
                "text": "STUB SYSTEM PROMPT",
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def test_blank_final_reply_falls_back_to_canned_acknowledgement(self, mock_create):
        mock_create.return_value = fake_response("end_turn", [])

        reply = app.chat("Hi", [])

        assert reply == "Thanks — I've noted that down. Is there anything else I can help you with?"


class TestToolUseLoop:
    def test_dispatches_tool_call_and_returns_follow_up_reply(self, mock_create, monkeypatch):
        record_user_details_mock = MagicMock(return_value={"recorded": "ok"})
        monkeypatch.setattr(app, "record_user_details", record_user_details_mock)

        first = fake_response(
            "tool_use",
            [tool_use_block("record_user_details", {"email": "a@b.com"}, tool_id="tu_1")],
        )
        second = fake_response("end_turn", [text_block("Thanks, I'll be in touch!")])
        mock_create.side_effect = [first, second]

        reply = app.chat("my email is a@b.com", [])

        assert reply == "Thanks, I'll be in touch!"
        record_user_details_mock.assert_called_once_with(email="a@b.com")
        assert mock_create.call_count == 2

        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        assistant_turn = second_call_messages[-2]
        tool_result_turn = second_call_messages[-1]
        assert assistant_turn == {"role": "assistant", "content": first.content}
        assert tool_result_turn["role"] == "user"
        assert tool_result_turn["content"] == [
            {
                "type": "tool_result",
                "tool_use_id": "tu_1",
                "content": json.dumps({"recorded": "ok"}),
            }
        ]

    def test_stops_after_max_tool_iterations_and_falls_back(self, mock_create, monkeypatch, capsys):
        monkeypatch.setattr(app, "record_unknown_question", MagicMock(return_value={"recorded": "ok"}))
        always_tool_use = fake_response(
            "tool_use", [tool_use_block("record_unknown_question", {"question": "?"})]
        )
        mock_create.return_value = always_tool_use

        reply = app.chat("keep asking", [])

        assert mock_create.call_count == app.MAX_TOOL_ITERATIONS
        assert reply == "Thanks — I've noted that down. Is there anything else I can help you with?"
        assert f"Hit MAX_TOOL_ITERATIONS ({app.MAX_TOOL_ITERATIONS})" in capsys.readouterr().out


class TestFailureHandling:
    def test_api_error_does_not_surface_a_traceback(self, mock_create):
        """A 429 or 529 is routine. The visitor should see a sentence, not a
        stack trace in the Gradio chat window.

        Currently, fails: chat() has no try/except around
        client.messages.create(), so the exception propagates straight out
        into the UI. Left unmarked (not xfail) as a known, unfixed bug —
        see SPEC.md §4.
        """
        mock_create.side_effect = RuntimeError("overloaded_error: 529")

        try:
            reply = app.chat("hello", [])
        except Exception:
            pytest.fail("an API error propagated out of chat() into the Gradio UI")

        assert reply.strip()
        assert "Traceback" not in reply
