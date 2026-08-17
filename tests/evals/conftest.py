"""Shared fixtures for the live eval suite (tests/evals/).

────────────────────────────────────────────────────────────────────────────
ADAPT THIS FILE FIRST
────────────────────────────────────────────────────────────────────────────
Everything here is written against the interfaces described in SPEC.md:

    app.chat(message, history)          -> str
    services.tools.record_user_details(email, name=None, notes=None)
    services.tools.record_unknown_question(question)

If your real names or signatures differ, change them HERE — in APP_MODULE,
TOOL_MODULE and the small adapters below — and the eval test files should
keep working untouched. That indirection is deliberate.

The scripted-fake-client / SDK-block-builder helpers that the old
tests/files/conftest.py also carried (for testing app.chat()'s tool-use loop
and app.handle_tool_calls() without hitting the network) now live directly
in tests/unit/test_app_chat.py and tests/unit/test_app_tool_dispatch.py —
this file only keeps what the *live* evals below still need: a way to spy on
tool calls without ever sending a real email.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable, Iterable

import pytest

APP_MODULE = "app"
TOOL_MODULE = "services.tools"
TOOL_NAMES = ("record_user_details", "record_unknown_question")


@dataclass
class ToolCall:
    name: str
    kwargs: dict


class ToolSpy:
    """Records every tool invocation and suppresses the real side effect.

    Critically this replaces the functions that actually send email, so the
    live evals never touch Gmail.
    """

    def __init__(self) -> None:
        self.calls: list[ToolCall] = []
        self.fail_on: set[str] = set()

    def names(self) -> list[str]:
        return [c.name for c in self.calls]

    def kwargs_for(self, name: str) -> dict:
        matches = [c.kwargs for c in self.calls if c.name == name]
        assert matches, f"{name} was never called; called: {self.names() or 'nothing'}"
        return matches[0]

    def _make(self, name: str) -> Callable[..., dict]:
        def _recorder(**kwargs) -> dict:
            self.calls.append(ToolCall(name=name, kwargs=kwargs))
            if name in self.fail_on:
                raise RuntimeError(f"simulated downstream failure in {name}")
            return {"recorded": "ok"}

        _recorder.__name__ = name
        return _recorder


def _patch_in_every_module(monkeypatch, attr: str, replacement, module_names: Iterable[str]) -> int:
    """Patch `attr` wherever it is bound.

    `from services.tools import record_user_details` in app.py creates a
    second binding; patching only services.tools would silently miss it and
    real emails would go out during the live evals. So patch both.
    """
    patched = 0
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, attr):
            monkeypatch.setattr(module, attr, replacement, raising=False)
            patched += 1
        # A module-level dispatch table (DISPATCH = {"record_user_details": fn})
        # captures the function object at import time, so patching the module
        # attribute above does not reach it. Rewrite any such entry in place.
        for dict_name, value in list(vars(module).items()):
            if dict_name.startswith("__") or not isinstance(value, dict):
                continue
            for key, entry in list(value.items()):
                if callable(entry) and getattr(entry, "__name__", None) == attr:
                    patched_dict = dict(value)
                    patched_dict[key] = replacement
                    monkeypatch.setattr(module, dict_name, patched_dict, raising=False)
                    patched += 1
    return patched


@pytest.fixture
def tool_spy(monkeypatch) -> ToolSpy:
    """Replaces both tool functions with recorders. No email is ever sent."""
    spy = ToolSpy()
    for name in TOOL_NAMES:
        _patch_in_every_module(monkeypatch, name, spy._make(name), (TOOL_MODULE, APP_MODULE))
    # Belt and braces: neutralise the mail layer itself in case a code path
    # reaches it another way.
    for module_name in ("services.mail_utility", "services.digest"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for attr in ("send_email", "send", "send_message", "send_daily_digest"):
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, lambda *a, **k: None, raising=False)
    return spy


@pytest.fixture
def app_module():
    """The app under test, imported lazily so collection errors are readable."""
    try:
        return importlib.import_module(APP_MODULE)
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"could not import {APP_MODULE!r}: {exc}")
