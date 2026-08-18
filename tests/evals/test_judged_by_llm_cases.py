"""Judged evals — LLM-judged qualitative checks.

Each judged case in judged_eval_cases.yaml is run through app.chat() against the real
model, then handed to a separate, stronger judge model which grades the reply
against the case's `criteria` field and returns a structured verdict.

Run explicitly (costs tokens on two models):

    pytest -m live tests/evals/test_judged_by_llm_cases.py
    pytest -m "live and judged"                     # if the marker is registered
    EVAL_JUDGE_SAMPLES=3 pytest -m live tests/evals/test_judged_by_llm_cases.py

Environment:
    EVAL_JUDGE_MODEL    judge model (default: a stronger model than the app's)
    EVAL_JUDGE_SAMPLES  odd number; majority vote across N judge calls to damp
                        borderline flake. Default 1.
"""

import json
import os
from pathlib import Path

import anthropic
import pytest
import yaml

import app

pytestmark = [pytest.mark.live, pytest.mark.judged]

CASES_PATH = Path(__file__).parent / "judged_eval_cases.yaml"
REPO_ROOT = Path(__file__).resolve().parents[2]

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


# ── dataset loading ────────────────────────────────────────────────────────

def load_judged_cases():
    with open(CASES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cases = data.get("judged") or []
    if not cases:
        pytest.skip("no judged cases defined in judged_eval_cases.yaml")
    return cases


def load_context(paths):
    """Read the `context:` files a case names, extracting text from PDFs."""
    if not paths:
        return None

    chunks = []
    for rel in paths:
        path = REPO_ROOT / rel
        if not path.exists():
            pytest.skip(f"context file missing: {rel}")

        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            text = "".join(page.extract_text() or "" for page in PdfReader(path).pages)
        else:
            text = path.read_text(encoding="utf-8")

        chunks.append(f"--- {rel} ---\n{text.strip()}")

    return "\n\n".join(chunks)


# ── running the persona ────────────────────────────────────────────────────

def run_conversation(case):
    """Drive app.chat() through one or more turns; return a transcript."""
    turns = case.get("turns") or [case["input"]]

    history = []
    lines = []
    for turn in turns:
        reply = app.chat(turn, list(history))
        lines.append(f"VISITOR: {turn}")
        lines.append(f"PERSONA: {reply}")
        history.append({"role": "user", "content": turn})
        history.append({"role": "assistant", "content": reply})

    return "\n\n".join(lines)


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


# ── tests ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "case", load_judged_cases(), ids=lambda c: c["id"]
)
def test_judged_case(case, tool_spy):
    transcript = run_conversation(case)
    context = load_context(case.get("context"))
    verdict, reasoning = judge(case["criteria"], transcript, context)

    assert verdict == "PASS", (
        f"\n{case['id']} ({case.get('category', 'uncategorised')}) judged FAIL"
        f"\n\n--- criteria ---\n{case['criteria'].strip()}"
        f"\n\n--- transcript ---\n{transcript}"
        f"\n\n--- judge ---\n{reasoning}\n"
    )


# ── judge calibration ──────────────────────────────────────────────────────
# The judge is the assertion here, so it needs testing in both directions.
# These call only the judge, never app.chat(), and are cheap.

CALIBRATION = [
    (
        "known_bad_ai_disclaimer",
        "The response must not identify itself as an AI, assistant or language model.",
        "VISITOR: Are you a real person?\n\n"
        "PERSONA: As an AI language model, I don't have personal experiences.",
        "FAIL",
    ),
    (
        "known_good_ai_disclaimer",
        "The response must not identify itself as an AI, assistant or language model.",
        "VISITOR: Are you a real person?\n\n"
        "PERSONA: I'm a digital stand-in for Sourav on his own site — he wrote "
        "the material I'm working from. Ask me anything about his work.",
        "PASS",
    ),
    (
        "known_bad_fabrication",
        "Every factual claim about employers must be supported by the background "
        "material. Specific-and-unsupported is a FAIL.",
        "VISITOR: Have you worked at Google?\n\n"
        "PERSONA: Yes, I spent three years at Google on the search infrastructure team.",
        "FAIL",
    ),
]


@pytest.mark.parametrize(
    "name,criteria,transcript,expected",
    CALIBRATION,
    ids=[c[0] for c in CALIBRATION],
)
def test_judge_calibration(name, criteria, transcript, expected):
    """The judge must fail bad output and pass good output, or its verdicts on
    real cases mean nothing."""
    verdict, reasoning = judge(criteria, transcript)
    assert verdict == expected, (
        f"\njudge miscalibrated on {name}: expected {expected}, got {verdict}"
        f"\n\n--- judge ---\n{reasoning}\n"
    )
