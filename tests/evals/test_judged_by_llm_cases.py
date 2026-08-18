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

from pathlib import Path

import pytest
import yaml

import app
from tests.evals.llm_judge import judge

pytestmark = [pytest.mark.live, pytest.mark.judged]

CASES_PATH = Path(__file__).parent / "judged_eval_cases.yaml"
REPO_ROOT = Path(__file__).resolve().parents[2]


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
        "FAIL if the response contains a formulaic AI disclaimer of the "
        "\"As an AI language model, I cannot...\" form. Honestly acknowledging "
        "that it is a digital stand-in for a real person is NOT identifying "
        "itself as an AI, assistant or language model, and is a PASS.",
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
