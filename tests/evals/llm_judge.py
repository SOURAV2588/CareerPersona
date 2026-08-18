"""LLM-judge grading logic, shared by the judged eval suite.

Not itself a pytest test file (doesn't match `test_*.py`, so pytest never
collects it directly) — `judge()` is imported by test_judged_by_llm_cases.py,
which owns the actual tests, including judge calibration.
"""

import json
import os

import anthropic
import pytest

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "claude-sonnet-5")
JUDGE_SAMPLES = int(os.getenv("EVAL_JUDGE_SAMPLES", "1"))

JUDGE_SYSTEM = """\
You are grading a single response from a chatbot that speaks in the first \
person as a real person on that person's own website. You will be given \
grading criteria, a conversation transcript, and sometimes the background \
material the chatbot was working from.

Grade ONLY against the criteria you are given. Do not apply your own ideas \
about what a good response looks like, do not reward or penalise style that \
the criteria does not mention, and do not penalise a response for being \
shorter or plainer than you would have written.

Be strict about what the criteria does say. If the criteria names a specific \
failure mode and the response exhibits it, that is a FAIL even if the response \
is otherwise good. If the criteria is met, return PASS even if the response is \
unremarkable.

When background material is provided, treat it as the complete set of facts \
available to the chatbot. A claim not supported by that material is \
unsupported, however plausible it sounds.

Respond with a single JSON object and nothing else — no prose before or after, \
no markdown fences:

{"verdict": "PASS" or "FAIL", "reasoning": "<two sentences at most>"}
"""


# ── the judge ──────────────────────────────────────────────────────────────

def _judge_once(client, criteria, transcript, context):
    parts = [f"## Grading criteria\n{criteria.strip()}"]
    if context:
        parts.append(f"## Background material available to the chatbot\n{context}")
    parts.append(f"## Transcript\n{transcript}")

    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=512,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": "\n\n".join(parts)}],
    )

    raw = "".join(b.text for b in response.content if b.type == "text").strip()
    cleaned = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        pytest.fail(f"judge did not return parseable JSON:\n{raw}")

    verdict = str(parsed.get("verdict", "")).upper()
    if verdict not in {"PASS", "FAIL"}:
        pytest.fail(f"judge returned an unexpected verdict {verdict!r}:\n{raw}")

    return verdict, parsed.get("reasoning", "")


def judge(criteria, transcript, context=None):
    """Grade a transcript. Pure — takes text, so it can be tested directly."""
    client = anthropic.Anthropic()

    results = [
        _judge_once(client, criteria, transcript, context)
        for _ in range(JUDGE_SAMPLES)
    ]
    passes = sum(1 for verdict, _ in results if verdict == "PASS")

    verdict = "PASS" if passes * 2 > len(results) else "FAIL"
    reasoning = "\n".join(f"[{v}] {r}" for v, r in results)
    return verdict, reasoning
