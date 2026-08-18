"""Tests for app.handle_tool_calls() — dispatching tool_use blocks to
services.tools functions and building tool_result blocks for the API.

For the surrounding app.chat() loop, see test_app_chat.py.

Two tests below are EXPECTED TO FAIL against the current code, on purpose —
they encode dispatcher bugs noted in SPEC.md §6. Watch them go red, fix the
dispatcher, watch them go green.

    xfail(strict=True) means: fail the run if they unexpectedly PASS, so you
    can't fix the bug and forget to flip the marker.

A third bug this suite used to pin — an unrecognized tool name silently
reusing the *previous* iteration's result, because handle_tool_calls() had
no `else` branch — is already fixed in app.py (it now returns
`{"error": f"Tool not found: {tool_name}"}`), so
test_unknown_tool_does_not_leak_previous_result below is a plain regression
test rather than an xfail.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app

pytestmark = pytest.mark.unit


def tool_use_block(name, arguments, tool_id="tool_1"):
    """Build a fake Anthropic ``tool_use`` content block.

    :param name: Name of the tool being called.
    :type name: str
    :param arguments: Arguments the model supplied for the call.
    :type arguments: dict
    :param tool_id: The block's ``id``, echoed back in the tool result.
    :type tool_id: str
    :rtype: types.SimpleNamespace
    """
    return SimpleNamespace(type="tool_use", name=name, input=arguments, id=tool_id)


class TestBasicContract:
    """Correct-path dispatch: each tool_use block is routed to the right function."""

    def test_record_user_details_tool_call(self, monkeypatch):
        """A record_user_details tool_use block is dispatched with its arguments as kwargs."""
        mock = MagicMock(return_value={"recorded": "ok"})
        monkeypatch.setattr(app, "record_user_details", mock)

        results = app.handle_tool_calls(
            [tool_use_block("record_user_details", {"email": "x@y.com"}, tool_id="id1")]
        )

        mock.assert_called_once_with(email="x@y.com")
        assert results == [
            {"type": "tool_result", "tool_use_id": "id1", "content": json.dumps({"recorded": "ok"})}
        ]

    def test_record_unknown_question_tool_call(self, monkeypatch):
        """A record_unknown_question tool_use block is dispatched with its arguments as kwargs."""
        mock = MagicMock(return_value={"recorded": "ok"})
        monkeypatch.setattr(app, "record_unknown_question", mock)

        results = app.handle_tool_calls(
            [tool_use_block("record_unknown_question", {"question": "huh?"}, tool_id="id2")]
        )

        mock.assert_called_once_with(question="huh?")
        assert results == [
            {"type": "tool_result", "tool_use_id": "id2", "content": json.dumps({"recorded": "ok"})}
        ]

    def test_unknown_tool_name_returns_error_result(self):
        """A name matching no known tool produces an {"error": ...} result instead of raising."""
        results = app.handle_tool_calls([tool_use_block("delete_everything", {}, tool_id="id3")])

        assert results == [
            {
                "type": "tool_result",
                "tool_use_id": "id3",
                "content": json.dumps({"error": "Tool not found: delete_everything"}),
            }
        ]

    def test_multiple_tool_calls_preserve_order(self, monkeypatch):
        """Results are returned in the same order as the input tool_use blocks."""
        monkeypatch.setattr(app, "record_user_details", MagicMock(return_value={"recorded": "ok"}))
        monkeypatch.setattr(app, "record_unknown_question", MagicMock(return_value={"recorded": "ok"}))

        blocks = [
            tool_use_block("record_user_details", {"email": "a@b.com"}, tool_id="first"),
            tool_use_block("record_unknown_question", {"question": "q"}, tool_id="second"),
        ]

        results = app.handle_tool_calls(blocks)

        assert [r["tool_use_id"] for r in results] == ["first", "second"]


class TestKnownBugs:
    """Regression and known-bug coverage for the dispatcher — see SPEC.md §6."""

    def test_unknown_tool_does_not_leak_previous_result(self, monkeypatch):
        """Regression test for a fixed bug: handle_tool_calls() now has an
        `else` branch, so an unrecognized tool name after a real one no
        longer reuses the previous iteration's `result` under the wrong
        tool_use_id.

        Was xfail(strict=True) — with no `else`, `result` kept whatever the
        *previous* loop iteration produced, and the model was handed
        another tool's output under the wrong tool_use_id with nothing
        crashing. Silent wrong answers are worse than loud failures, which
        is why this stays a named test rather than folding into the generic
        contract test above.
        """
        monkeypatch.setattr(app, "record_user_details", MagicMock(return_value={"recorded": "ok"}))

        calls = [
            tool_use_block("record_user_details", {"email": "c@example.com"}, "toolu_real"),
            tool_use_block("definitely_not_a_tool", {"x": 1}, "toolu_bogus"),
        ]

        results = app.handle_tool_calls(calls)

        real, bogus = results[0], results[1]
        assert bogus["tool_use_id"] == "toolu_bogus"
        assert bogus["content"] != real["content"], (
            "the unknown tool returned the previous tool's result — cross-contamination"
        )

    @pytest.mark.xfail(strict=True, reason="unknown tool names are currently not surfaced at all")
    def test_unknown_tool_is_reported_with_the_sdks_is_error_field(self):
        """Still a real gap: app.py reports the failure via a plain
        `{"error": ...}` string in the content payload, not the Anthropic
        tool_result envelope's `is_error` field. The model isn't told the
        call failed in the way the API is designed for — see SPEC.md §6."""
        results = app.handle_tool_calls([tool_use_block("definitely_not_a_tool", {}, "toolu_x")])

        assert len(results) == 1
        assert results[0].get("is_error") is True

    @pytest.mark.xfail(
        strict=True,
        reason='SPEC.md §6: tools return {"recorded": "ok"} regardless of downstream success',
    )
    def test_tool_failure_is_not_reported_as_success(self, monkeypatch):
        """If the Gmail send throws, the model says "I've noted that down",
        the visitor believes their details were captured, and the lead is
        gone. For an app whose whole point is capturing contact details,
        this is *the* failure mode worth a test."""
        monkeypatch.setattr(
            app,
            "record_user_details",
            MagicMock(side_effect=RuntimeError("simulated downstream failure")),
        )

        results = app.handle_tool_calls(
            [tool_use_block("record_user_details", {"email": "d@example.com"})]
        )

        assert results[0].get("is_error") is True, "a failed send was reported to the model as success"

    def test_dispatch_does_not_raise_on_tool_failure(self, monkeypatch):
        """Complement to the above: surfacing the error must not mean
        crashing the request. The visitor should still get a reply.

        Currently, fails: handle_tool_calls() does not catch exceptions
        raised by the dispatched tool function. Left unmarked (not xfail)
        as a known, unfixed bug.
        """
        monkeypatch.setattr(
            app,
            "record_unknown_question",
            MagicMock(side_effect=RuntimeError("simulated downstream failure")),
        )

        results = app.handle_tool_calls([tool_use_block("record_unknown_question", {"question": "?"})])

        assert len(results) == 1  # degraded, not dead
