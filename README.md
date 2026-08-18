# Career Persona

A conversational AI chatbot that answers questions about Sourav Ghosh's career, background, and experience, speaking in the first person as him.

The intended use is a personal website: a visitor asks about your work history, the bot answers from your background material, and two things happen quietly in the background. If the visitor shares an email address, you get notified immediately. If the bot is asked something in-scope it cannot answer, the question is saved and sent to you later in a daily summary. Out-of-scope questions (sport, general coding help, trivia) are declined in character and never recorded. Over time that unanswered-questions list tells you what people actually want to know that your material does not cover.

Built with Anthropic's Claude API, a Gradio chat interface, the Gmail API for notifications, and Langfuse for tracing.

## Contents

- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [Testing](#testing)
- [Design notes](#design-notes)
- [Rate limiting](#rate-limiting)
- [Known limitations](#known-limitations)
- [Further documentation](#further-documentation)
- [License](#license)

## How it works

```
   Visitor
      |
      v
  Gradio ChatInterface
      |
      v
  app.chat()  ---> rate_limit.check_chat_turn() --> app._chat() --> Anthropic Messages API
      |   (catches API/tool          (rejects before any            |          (claude-haiku-4-5)
      |    errors -> fallback         API call is made)              |   ^
      |    message, see below)                                      |   +------ tool results ----------+
      |                                 |                                  |
      |                                 |                          model requests a tool
      |                                 v                                  |
      |                         app.handle_tool_calls()  <-----------------+
      |                                 |
      |                                 +--> record_user_details    --> immediate email (Gmail API,
      |                                 |                                 capped per caller)
      |                                 +--> record_unknown_question --> Postgres unknown_questions table
      v
  reply text

  Daily digest (separate, scheduled path, same table as above):

  services/digest.py --> fetch_pending() (Postgres) --> daily digest email (Gmail API) --> mark_sent()
  (APScheduler, 21:30 IST)                                                                (rows marked sent_at)
```

Each chat turn works like this:

1. `rate_limit.check_chat_turn()` runs first, before anything else touches the network: an oversized message, a caller sending turns too fast, or a global daily turn/token budget being exhausted all get rejected here with a short in-character reply — no Anthropic API call, no cost. See [Rate limiting](#rate-limiting).
2. The system prompt is rebuilt from your background files and sent as a top-level `system` parameter with prompt caching enabled.
3. Claude answers, or asks to call one of two tools.
4. If a tool is requested, it runs, the result is fed back, and Claude is called again. This repeats up to `MAX_TOOL_ITERATIONS` (5) times so a misbehaving model cannot loop indefinitely. Every model response's token usage is charged against the daily spend budget as it comes back, including intermediate tool-use round trips, not just the final one.
5. The final text is returned to the chat window.
6. If the Anthropic API call fails, or a tool's downstream side effect (email send, database write) raises, `chat()` catches it and returns a short in-character fallback message instead of a crash or a raw traceback. See [Design notes](#design-notes).

The two tools available to the model:

| Tool | Purpose | Effect |
|---|---|---|
| `record_user_details` | A visitor shared contact details | Sends you an email right away, capped per visitor so it can't become an open relay to your inbox |
| `record_unknown_question` | The bot could not answer an in-scope question | Inserts the question into a Postgres table for the daily digest |

Out-of-scope questions (not about Sourav's professional life at all) are declined in character without calling either tool, so they never reach the digest.

## Tech stack

| Area | Choice |
|---|---|
| Language | Python 3.10+ |
| Model | Claude Haiku 4.5 (`claude-haiku-4-5`) via the Anthropic Messages API |
| UI | Gradio `ChatInterface` |
| Email | Gmail API with OAuth refresh-token auth |
| Scheduling | APScheduler cron trigger |
| Storage | Postgres, for unanswered questions pending/archived by the daily digest (a legacy JSON Lines implementation is still in the repo but unused, see [Known limitations](#known-limitations)) |
| Tracing | Langfuse with OpenInference auto-instrumentation |
| Rate limiting | In-process sliding-window/daily-budget limiter, no external dependency |
| Testing | pytest, with a separate two-tier live evaluation suite (deterministic + LLM-judged) |

## Project structure

```
career-persona/
├── app.py                                     Entry point: chat loop, error handling, tool dispatch, Gradio launch
├── services/
│   ├── profile.py                             Builds the system prompt from background files; fallback message strings
│   ├── tools.py                                The two model-callable tools and their schemas
│   ├── rate_limit.py                           Inbound rate limits and spend caps for the chat endpoint
│   ├── mail_utility.py                         Gmail API client wrapper
│   ├── db.py                                   Postgres connection pool + schema for the unknown_questions table
│   ├── question_store.py                       Postgres-backed pending-question store — used by both tools.py (write) and digest.py (read)
│   └── digest.py                               Daily digest email and its scheduler
├── resources/
│   ├── summary.txt                             Short bio
│   ├── SOURAV_GHOSH_CAREER_PROFILE.md          Detailed, structured career profile
│   ├── CURRENT_STATUS_AND_PREFERENCES.md       Notice period, relocation, role type, redirect policy
│   └── SOURAV_GHOSH_LINKEDIN.pdf               LinkedIn export, text extracted into the prompt at runtime
├── tests/
│   ├── conftest.py                             Session-wide test isolation (mail/API stubs, rate-limit reset)
│   ├── unit/                                   Fast, fully mocked tests, plus a db-marked end-to-end test (needs TEST_DATABASE_URL)
│   ├── evals/                                  Behavioral evaluations against the real model (deterministic + LLM-judged)
│   └── sanity_checks/                          Standalone connectivity checks, run manually, not collected by pytest
├── requirements.txt                            Runtime dependencies
├── requirements-dev.txt                        Runtime plus test dependencies
├── pytest.ini                                  Test configuration
└── LICENSE                                     MIT license, covering the source code
```

## Getting started

### Prerequisites

- Python 3.10 or later
- An Anthropic API key
- **A reachable Postgres database, for unanswered-question storage and the
  daily digest.** `app.py` calls `services.db.init_db()` on startup, before
  the Gradio server launches; if `DATABASE_URL` is unset or unreachable, the
  failure is logged and the app starts anyway — chat still works, but
  `record_unknown_question` and the daily digest will fail until Postgres is
  reachable. See [Configuration](#configuration).
- A Google Cloud project with the Gmail API enabled, if you want email notifications
- A Langfuse account, if you want tracing

### Install

```bash
git clone <repository-url>
cd career-persona

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

For development and testing, install the dev dependencies instead:

```bash
pip install -r requirements-dev.txt
```

### Add your own content

The persona is driven by four files in `resources/`, all read fresh on every chat turn:

- `summary.txt` — a short free-text bio.
- `SOURAV_GHOSH_CAREER_PROFILE.md` — a longer, structured career profile (roles, skills, domain experience).
- `CURRENT_STATUS_AND_PREFERENCES.md` — notice period, relocation, and the policy for redirecting compensation/reasons-for-leaving questions to email instead of answering them.
- `SOURAV_GHOSH_LINKEDIN.pdf` — a LinkedIn profile export; text is extracted from it page by page at runtime.

Replace all four with your own. If you rename any of them, update the filename in the matching `get_*()` function in `services/profile.py`. The persona name is currently hardcoded in the same file.

### Set up Gmail credentials

Email notifications use a stored OAuth refresh token rather than an interactive login, so the app can send mail without a browser prompt. To get one:

1. In Google Cloud Console, create a project and enable the Gmail API.
2. Create an OAuth 2.0 Client ID of type "Desktop app".
3. Complete the OAuth consent flow once for the `https://www.googleapis.com/auth/gmail.send` scope and keep the refresh token that is returned.
4. Put the client ID, client secret, and refresh token in your `.env` file.

You can skip this if you do not need email notifications, but any tool call that tries to send mail will then fail — degrading to a fallback chat reply rather than crashing the turn (see [Design notes](#design-notes)), but no notification will actually go out.

## Configuration

Create a `.env` file in the project root. It is git-ignored. Never commit real credentials.

```
ANTHROPIC_API_KEY=sk-ant-...

# Postgres — needed for unanswered-question storage and the daily digest;
# missing/unreachable is logged and non-fatal, chat still works (see Prerequisites)
DATABASE_URL=postgresql://user:password@host:5432/dbname

GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
GMAIL_RECIPIENT=you@example.com

LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com

# Rate limiting — all optional, shown with their defaults
# CHAT_MESSAGE_MAX_CHARS=2000
# CHAT_BURST_MAX_TURNS=5
# CHAT_BURST_WINDOW_SECONDS=60
# CHAT_SUSTAINED_MAX_TURNS=40
# CHAT_SUSTAINED_WINDOW_SECONDS=3600
# CHAT_GLOBAL_DAILY_TURNS=750
# CHAT_GLOBAL_DAILY_TOKENS=5000000
# CHAT_EMAIL_MAX_PER_CALLER=2
# CHAT_EMAIL_WINDOW_SECONDS=3600
# CHAT_MAX_TRACKED_CALLERS=10000
# CHAT_TRUST_PROXY_HEADER=false
```

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Authenticates calls to the Claude API |
| `DATABASE_URL` | Recommended | Postgres connection string for the pending-questions table — the app calls `init_db()` on startup, but a missing/unreachable value is logged and the app starts anyway; `record_unknown_question` and the daily digest just won't work until it's set (see [Prerequisites](#prerequisites)) |
| `GMAIL_CLIENT_ID` | For email | OAuth client ID |
| `GMAIL_CLIENT_SECRET` | For email | OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | For email | Long-lived token used to mint access tokens |
| `GMAIL_RECIPIENT` | For email | Where notifications and digests are sent — raises a clear error at send time if unset |
| `LANGFUSE_PUBLIC_KEY` | For tracing | Langfuse project key |
| `LANGFUSE_SECRET_KEY` | For tracing | Langfuse project secret |
| `LANGFUSE_BASE_URL` | For tracing | Langfuse endpoint |
| `CHAT_MESSAGE_MAX_CHARS` | Optional | Max chars per chat message (default `2000`) |
| `CHAT_BURST_MAX_TURNS` / `CHAT_BURST_WINDOW_SECONDS` | Optional | Per-visitor burst window (default `5` turns / `60`s) |
| `CHAT_SUSTAINED_MAX_TURNS` / `CHAT_SUSTAINED_WINDOW_SECONDS` | Optional | Per-visitor sustained window (default `40` turns / `3600`s) |
| `CHAT_GLOBAL_DAILY_TURNS` | Optional | Site-wide daily turn cap (default `750`) |
| `CHAT_GLOBAL_DAILY_TOKENS` | Optional | Site-wide daily token budget (default `5000000`) |
| `CHAT_EMAIL_MAX_PER_CALLER` / `CHAT_EMAIL_WINDOW_SECONDS` | Optional | Cap on `record_user_details` emails per visitor (default `2` / `3600`s) |
| `CHAT_MAX_TRACKED_CALLERS` | Optional | Max visitors tracked per limiter before oldest are evicted (default `10000`) |
| `CHAT_TRUST_PROXY_HEADER` | Optional | Trust `X-Forwarded-For` for caller identity (default `false`) — only enable behind a proxy you control, see [Rate limiting](#rate-limiting) |
| `TEST_DATABASE_URL` | For db tests only | Points `tests/unit/test_question_store.py`'s `db`-marked tests at a throwaway (separate) Postgres instance; those tests are skipped without it |
| `EVAL_JUDGE_MODEL` | For judged tests only | Judge model for the LLM-judged eval layer (default `claude-sonnet-5`) |
| `EVAL_JUDGE_SAMPLES` | For judged tests only | Judge calls per case, majority vote (default `1`) |

## Running the app

```bash
python app.py
```

Gradio serves the chat interface at `http://127.0.0.1:7860` by default.

### The daily digest

`services/digest.py` emails you a single summary of everything the bot could not answer, scheduled for 9:30 PM IST each day, and reads from the same Postgres table `record_unknown_question` writes to (`unknown_questions`, via `services/question_store.py`).

`app.py` calls `services.db.init_db()` on startup, before the scheduler starts, which creates the `unknown_questions` table if it doesn't already exist — so a fresh `DATABASE_URL` needs no manual schema setup.

A successful send marks the sent rows (`sent_at`) rather than deleting them. There's currently no error handling around the send call: a failed send raises, so the affected rows stay unmarked and get retried on the next scheduled run, but (unlike an earlier version of this code) nothing is logged locally when that happens beyond whatever APScheduler's own job executor logs.

**The scheduler runs by default.** `start_scheduler()` is called unconditionally from `app.py`'s `__main__` block, so it starts as soon as you run `python app.py`. It's a no-op background thread until 21:30 IST — nothing is sent immediately, and nothing is sent at all if there are no pending questions.

To send a digest manually at any time:

```bash
python -m services.digest
```

To verify your Langfuse connection:

```bash
python -m tests.sanity_checks.langfuse_test
```

## Testing

The suite has two layers with different costs, separated by pytest markers.

```bash
pytest                              # unit tests only: fast, free, no network
pytest -m live                      # adds both eval layers: calls the real model(s), costs tokens
pytest -m "live and not judged"     # deterministic only (one model)
pytest -m judged                    # judged only (LLM-judged, two models per case)
pytest -m db                        # Postgres-backed end-to-end test; needs TEST_DATABASE_URL
```

**Unit tests** (`tests/unit/`) cover every module. All external services are mocked. `tests/conftest.py` seeds dummy credentials and stubs the Gmail client for the whole session, so the unit layer cannot make a network call even when a real `.env` file is present.

A fourth marker, `db`, covers Postgres-backed tests in `tests/unit/test_question_store.py` — skipped without `TEST_DATABASE_URL`, and excluded from a plain `pytest` run either way. `test_question_lifecycle_store_pending_send_marks_sent` exercises the real round trip end to end: `record_unknown_question` stores a question, `fetch_pending()` confirms it's pending, `send_daily_digest()` runs for real (only the Gmail send is mocked) and marks it sent, and a final `fetch_pending()` confirms it's gone — proving `store_question`/`fetch_pending`/`mark_sent` actually agree on schema against a real Postgres instance, not just against each other's mocks.

**Evaluations** (`tests/evals/`) call the real model through `app.chat()`.
- **Deterministic** checks behavior deterministically: whether the right tool fired, whether arguments came through intact, and whether the reply avoided forbidden claims.
- **Judged** hands the transcript to a separate, stronger judge model that grades it against a free-text `criteria` field — for qualitative checks (persona consistency, tone, faithfulness to the background material) that a substring match can't capture. A handful of hand-labeled calibration cases run alongside it to catch a miscalibrated judge before trusting its verdicts.

Email is stubbed in both layers, so evaluation runs cannot send real mail. See `tests/evals/README.md` for details.

Coverage report:

```bash
pytest --cov=app --cov=services --cov-report=term-missing
```

### About the test results

A plain `pytest` run currently reports `62 passed, 48 deselected, 2 xfailed` — nothing unexpectedly red. The 2 `xfail(strict=True)` results (`tests/unit/test_app_tool_dispatch.py::TestKnownBugs`) are a deliberately accepted, tracked gap: tool failures are caught so the chat turn doesn't crash, but they're still reported to the model as plain `{"error": ...}` text rather than via the Anthropic SDK's `is_error` tool-result field. `strict=True` means the run would break again if this were ever fixed without removing the marker, so a fix can't silently go unnoticed.

Treating the test output as a live, up-to-date bug list is deliberate — see `SPEC.md` §12 and §15 for the full breakdown, including a couple of now-fixed bugs whose test docstrings haven't caught up with the fix yet (harmless, just misleading if read on their own).

## Design notes

**Prompt caching.** The system prompt contains the full background material and is rebuilt on every request. It is marked with `cache_control: ephemeral` so repeated turns reuse the cached prefix instead of paying for those tokens again.

**Bounded tool loop.** The model can request tools repeatedly. The loop is capped at five round trips, which bounds both latency and API spend for a single chat turn.

**Graceful degradation on failure.** `chat()` wraps the whole turn in a `try`/`except`: transient Anthropic errors (rate limit, overload, connection) get one canned "I'm busy" reply, other API errors and any unexpected exception (including a downstream tool failure) get a canned generic reply with a direct-contact fallback. Gradio's own error UI is disabled (`launch(show_error=False)`) since the app already turns every failure into a visitor-facing sentence itself. The Anthropic client is also constructed with `max_retries=4, timeout=30.0`, so many transient failures are retried by the SDK before `chat()` ever sees them.

**Unanswered questions are batched, not pushed.** An immediate email for every unanswered question would be noise. Batching them into one daily digest makes the list readable, and the questions survive restarts because they are written to Postgres rather than held in memory.

**Postgres for the pending-questions store.** Unanswered questions live in a single `unknown_questions` table (schema owned by `services/db.py`), written by `record_unknown_question` and read by the daily digest, both via `services/question_store.py`. An earlier version of this app used flat JSON Lines files for the same job under that same module path; the file was rewritten in place to the Postgres implementation rather than kept alongside a separate module, so there's no orphaned legacy store left in the repo.

**One email path.** Immediate notifications and the daily digest both go through the same shared `mail_util` instance of the `MailUtility` class — not just the same class, the same object — and it builds its Gmail service lazily on first send rather than at construction. An earlier version used two different mechanisms for the same job.

**Prompt-injection guardrails.** Visitor text is always treated as a question, never as an instruction that changes the system prompt's rules. Both the system prompt and the `record_user_details` tool description explicitly warn against copying visitor-dictated wording (e.g. a "note" telling the model what to say about them) into a tool call or a reply. Declining an instruction-override attempt doesn't excuse answering whatever else is bundled into the same message — that content still gets the normal in-scope/out-of-scope treatment, closing a gap a live eval run caught (`inject_003`, see [Known limitations](#known-limitations)).

**Two eval layers instead of one.** Deterministic assertions are cheap and catch clear-cut regressions (wrong tool, wrong argument, a banned phrase) but can't judge tone or nuance. An LLM judge can, but is itself fallible, so it's checked against hand-labeled calibration cases before its verdicts on real cases are trusted.

**Docstrings throughout.** Every module, class, and function in `app.py`, `services/`, and `tests/` carries a reStructuredText-style docstring (`:param:`, `:return:`, `:raises:`, etc.), not just the small subset that happened to need one for a docs tool. See `SPEC.md` §17.

## Rate limiting

`services/rate_limit.py` protects the public chat endpoint from both abuse and runaway API spend. `chat()` checks every turn against a stack of guards, cheapest first, so a rejected turn never reaches the Anthropic API:

| Guard | Default | What it stops |
|---|---|---|
| Message length | 2,000 chars | An oversized single message |
| Daily token budget | 5,000,000 tokens/day | Runaway total spend across all visitors |
| Daily turn cap | 750 turns/day | A circuit breaker independent of token accounting |
| Burst window | 5 turns/60s per visitor | Rapid-fire hammering from one visitor |
| Sustained window | 40 turns/hour per visitor | A visitor running up a long session |
| Contact-email cap | 2 emails/hour per visitor | `record_user_details` being used as an open relay to your inbox |

A visitor is identified by IP address (`request.client.host` from Gradio's `gr.Request`) — imperfect on its own (shared NAT, rotating clients), which is why it's backed by the site-wide daily caps rather than relied on alone. `X-Forwarded-For` is only trusted behind a proxy you control (`CHAT_TRUST_PROXY_HEADER=true`); left off by default, since a client exposed directly to the internet could otherwise forge that header to mint itself a fresh quota.

A rejected turn gets one of two short in-character replies — "that's a bit long" for an oversized message, or "I've hit my limit for now" for everything else — never a raw error.

All the numbers above are tunable via environment variables (see [Configuration](#configuration)) and every counter resets automatically: the per-visitor windows slide continuously, and the daily budgets roll over at local midnight (`Asia/Kolkata`). State lives in memory and is *not* persisted — that's intentional for a rate limiter, but it also means the limits apply per worker process; running more than one process (e.g. behind a load balancer) would need the counters moved to something shared, like Redis.

## Known limitations

- `app.py` calls `services.db.init_db()` before the Gradio server launches; a missing/unreachable `DATABASE_URL` is caught, logged, and does not stop the app from starting — matching the lazy-failure behavior of the Gmail/Langfuse env vars. `record_unknown_question` and the daily digest will still fail individually until Postgres is reachable, and there's no test covering the degrade-and-continue path (`SPEC.md` §12, item 1). See [Prerequisites](#prerequisites).
- `services/question_store.py` was rewritten in place from a JSON-Lines file store to the live Postgres implementation, and the separate `services/question_store_db.py` module it briefly lived alongside has been deleted — there's a single store module now, not an orphaned legacy one sitting next to a live one. See `SPEC.md` §12, "Fixed since the last pass".
- Tools always report `{"recorded": "ok"}` to the model even when the underlying send/store failed; `handle_tool_calls()` catches the exception one layer up but reports it as plain text, not the SDK's `is_error` field — so the model can still tell a visitor "I've noted that down" after a failed send. Tracked by two `xfail(strict=True)` tests (see [Testing](#testing)).
- The persona name and background-file filenames are hardcoded in `services/profile.py`.
- **Full live eval run, current dataset and system prompt:** the first `pytest -m live` run reported `46 passed, 1 failed` across all 47 tests (32 deterministic + 15 judged/calibration). The earlier known gap — the model not always calling `record_unknown_question` for out-of-scope questions — no longer reproduced; none of the `oos_*` cases failed. The one genuine gap found, **`inject_003`** — the persona correctly refused an injected instruction-override but then still answered the off-topic trivia questions bundled into the same message — has since been fixed with an explicit system-prompt sentence (`services/profile.py`) saying that declining the override doesn't excuse answering whatever else rides along with it. A follow-up run of the deterministic layer reports `32 passed, 0 failed`, `inject_003` included. See `SPEC.md` §5/§12/§15.
- The judged layer's `15 passed` (12 judged cases + 3 calibration cases) came from this same run and required fixing two dataset bugs first — see `SPEC.md` §12, "Fixed since the last pass" — where a case's `context:` list didn't match what the app's real system prompt actually feeds the model, so the judge failed correct, grounded answers (a real AWS-experience claim, a real relocation detail) that it had no way to verify against the narrower material it was shown.
- Rate-limit state is in-process only, so limits apply per worker and are lost on restart — see [Rate limiting](#rate-limiting).

`SPEC.md` section 12 tracks these in full, with file/line references and, where one exists, the test that pins each one.

## Further documentation

| File | Contents |
|---|---|
| `SPEC.md` | Full technical specification and the known-issues list |
| `tests/evals/README.md` | Evaluation suite design and observed results |
| `BUGS.md` | Bug and fix log |
| `DEVLOG.md` | Development log |

## License

The source code in this repository is released under the MIT License. See [`LICENSE`](LICENSE) for the full text.

The personal content in `resources/` is **not** covered by that license:

- `summary.txt`
- `SOURAV_GHOSH_CAREER_PROFILE.md`
- `CURRENT_STATUS_AND_PREFERENCES.md`
- `SOURAV_GHOSH_LINKEDIN.pdf`

These files are biographical material — © 2026 Sourav Ghosh, all rights reserved. They are included so the project runs as a working demonstration, not as reusable content. If you are reusing this project, replace all four with your own background material as described in [Add your own content](#add-your-own-content).

The same applies to the `unknown_questions` Postgres table, which may contain visitor-submitted contact details.
