"""Tier 1 evals — deterministic, no LLM judge.

Every assertion here is a plain comparison: did the right tool fire, with the
right arguments, and did the reply avoid a forbidden claim. No judge, no
judge variance, no judge bill.

These DO hit the real model, so they are marked `live` and skipped by
default (see the root pytest.ini's `addopts = -m "not live"`):

    pytest                    # unit tests only, free, every push
    pytest -m live            # tier 1 evals, costs tokens, on demand

Emails are still stubbed by the `tool_spy` fixture, so running these will not
send anything to your inbox.

Tier 2 (`eval_cases.yaml`'s `tier2:` section, LLM-judged qualitative checks)
has no runner yet — out of scope here.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

CASES = yaml.safe_load((Path(__file__).parent / "eval_cases.yaml").read_text())
TIER1 = CASES["tier1"]

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set",
    ),
]


def _case_id(case: dict) -> str:
    return f"{case['category']}::{case['id']}"


@pytest.fixture
def live_chat(app_module, tool_spy):
    """Runs the real chat() against the real model, with tools stubbed.

    Returns (reply, spy) so a case can assert on both the visible answer and
    the invisible side effects.
    """

    def _run(case: dict) -> tuple[str, object]:
        turns = case.get("turns") or [case["input"]]
        history: list[dict] = []
        reply = ""
        for turn in turns:
            reply = app_module.chat(turn, list(history))
            history.append({"role": "user", "content": turn})
            history.append({"role": "assistant", "content": reply})
        return reply, tool_spy

    return _run


@pytest.mark.parametrize("case", TIER1, ids=[_case_id(c) for c in TIER1])
def test_tier1(case: dict, live_chat):
    reply, spy = live_chat(case)
    fired = spy.names()

    # 1. tools that must fire
    for expected in case.get("expect_tools", []):
        assert expected in fired, (
            f"[{case['id']}] expected {expected!r} to fire; got {fired or 'no tools'}\n"
            f"  input: {case['input']!r}\n  reply: {reply[:200]!r}"
        )

    # 2. tools that must NOT fire.
    #    `expect_tools: []` means "no tool at all" — the false-positive guard.
    #    Cheap to get wrong, and getting it wrong means an inbox full of noise.
    if case.get("expect_tools") == []:
        assert not fired, f"[{case['id']}] fired {fired} on an in-scope question"
    for forbidden in case.get("expect_not_tools", []):
        assert forbidden not in fired, f"[{case['id']}] {forbidden!r} fired but should not have"

    # 3. argument fidelity — a mangled email is a lead silently lost
    for tool_name, expected_args in (case.get("expect_args") or {}).items():
        actual = spy.kwargs_for(tool_name)
        for key, value in expected_args.items():
            assert actual.get(key) == value, (
                f"[{case['id']}] {tool_name}.{key}: expected {value!r}, got {actual.get(key)!r}"
            )

    # 4. forbidden claims — blunt substring guard, but it catches the worst
    #    hallucinations for free and never disagrees with itself
    lowered = reply.lower()
    for phrase in case.get("forbid_substrings", []):
        assert phrase.lower() not in lowered, (
            f"[{case['id']}] reply contained forbidden phrase {phrase!r}\n  reply: {reply[:300]!r}"
        )


def test_dataset_is_well_formed():
    """Guards the dataset itself — a typo'd key silently weakens a case,
    and a silently-weakened eval is worse than no eval."""
    seen: set[str] = set()
    allowed = {
        "id", "category", "input", "turns", "expect_tools",
        "expect_not_tools", "expect_args", "forbid_substrings",
    }
    for case in TIER1:
        assert case["id"] not in seen, f"duplicate case id: {case['id']}"
        seen.add(case["id"])
        assert case.get("input") or case.get("turns"), f"{case['id']} has no input"
        unknown = set(case) - allowed
        assert not unknown, f"{case['id']} has unrecognised keys: {unknown}"
        assert any(
            k in case for k in ("expect_tools", "expect_not_tools", "forbid_substrings")
        ), f"{case['id']} asserts nothing"
