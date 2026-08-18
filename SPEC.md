# SPEC.md — Career Persona

Technical specification for the "Career Persona" project. This document reflects
the codebase as of 2026-08-18 (post error-handling, richer-persona-prompt,
resource-file rename, judged eval suite, inbound rate-limiting/spend-cap, the
Postgres-backed question-store migration — write and read sides now
reconnected, see §2, §9 — plus MIT licensing, see §16, the judged eval
dataset's context/criteria fixes that produced its first clean full run, see
§12/§15, and a full reStructuredText docstring pass over `app.py`,
`services/`, and `tests/`, see §17).

## 1. Purpose

Career Persona is a conversational AI chatbot that acts *as* Sourav Ghosh —
answering questions about his career, background, skills, and experience on his
behalf (e.g. embedded on a personal website). It is built on Anthropic's Claude
API with a Gradio chat UI, and includes light CRM-style side effects: capturing
visitor contact details and flagging questions the persona couldn't answer.

## 2. Architecture overview

```
┌────────────┐      ChatInterface       ┌───────────────┐
│  Gradio UI │ ───────────────────────▶ │   app.chat()  │  (catches API/tool
└────────────┘                          └───────┬───────┘   errors, §4)
                                                 │
                                     rate_limit.check_chat_turn()  (§7 — rejects
                                                 │                  before any API call)
                    system prompt (cached)       │ tool_use loop (capped at
                    ┌────────────────────────────┼─── MAX_TOOL_ITERATIONS = 5)
                    │                             ▼                     │
           services/profile.py            Anthropic Messages API   services/tools.py
        (builds prompt from summary +       (model: claude-        (record_user_details,
         career profile + prefs +           haiku-4-5)              record_unknown_question)
         LinkedIn PDF)                            │                 │            │
                                    rate_limit.record_usage()   immediate email ──┘            │
                                    (§7 — charges daily budget) (MailUtility, Gmail API) insert pending row
                                                                                   ▼
                                                        services/question_store_db.py store_question()
                                                                                   │
                                                                                   ▼
                                                        Postgres unknown_questions table (sent_at IS NULL = pending)

Background (started at process launch, independent of chat requests):

services/digest.py ── APScheduler cron (21:30 IST daily) — enabled by default
        │
        ▼
services/question_store_db.py fetch_pending()  (same Postgres table, read side)
        │
        ▼
services/mail_utility.py (Gmail API) ── daily digest email of unanswered questions
        │
        ▼
services/question_store_db.py mark_sent()  (sets sent_at on the rows just emailed)
```

**The write side and the read side of the pending-question store are now
the same store.** They previously weren't:
`record_unknown_question` wrote to a JSONL file while
`services/digest.py::send_daily_digest()` had been switched to read from a
new Postgres table, so nothing the app wrote was ever read and the digest
was permanently a no-op. Fixed — see §12, "Fixed since the last pass".
`services/tools.py::record_unknown_question` now calls
`services.question_store_db.store_question`, the same module
`services/digest.py` reads from via `fetch_pending()`/`mark_sent()`.
`app.py`'s `__main__` block also now calls `services.db.init_db()` before
`start_scheduler()`, so the `unknown_questions` table is created on startup
rather than only existing via a test fixture. The old JSONL implementation
(`services/question_store.py`, `data/unknown_questions.jsonl`,
`data/sent_questions.jsonl`) is no longer used anywhere in the app — see §11.

Both notification paths (`record_user_details`'s immediate email and the daily
digest) go through the **same shared instance** — `services.mail_utility.mail_util`
— of the `MailUtility` (Gmail API/OAuth) class, not two independent ones and
not two separately-constructed instances of the same class. The underlying
Gmail service client is built lazily, on first actual `send_email()` call,
not at import/construction time.

Tracing/observability is layered on via an explicitly-constructed Langfuse
client (`get_client()`) plus `AnthropicInstrumentor().instrument()`
(OpenInference), and `@observe(...)`-decorated entry points in `app.py` and
`services/tools.py` (§10).

Inbound rate limiting and spend caps (`services/rate_limit.py`, §7) sit in
front of everything else: `chat()` derives a per-visitor identity and checks
it *before* the system prompt is built or any Anthropic API call is made, so
a rejected turn costs nothing beyond the check itself.

## 3. Runtime & entry points

- **Language/runtime:** Python 3.10+ (uses `venv/`), no build step.
- **`app.py`** — the sole entry point. Defines `chat()`/`_chat()`, wires up
  tracing, initializes the Postgres schema, starts the digest scheduler, and
  launches the Gradio `ChatInterface`.
- **Run command:** `python app.py` (loads `.env`, calls `services.db.init_db()`,
  starts the digest scheduler, opens a local Gradio web server, default
  `http://127.0.0.1:7860`).
- **`DATABASE_URL` is now a hard startup requirement, not a soft one.**
  `init_db()` runs unconditionally in `__main__` before the Gradio server
  ever starts (§9), and it calls `services.db.get_pool()`, which raises
  `RuntimeError("DATABASE_URL is not set")` immediately if the env var is
  missing — unlike the Gmail env vars, which only fail lazily on the first
  actual send (§8). A fresh clone with a `.env` missing `DATABASE_URL` (or
  pointing at an unreachable Postgres instance) will crash on `python
  app.py` before the chat UI ever comes up.

## 4. Core chat flow (`app.py`)

1. Gradio's `ChatInterface` calls `chat(message, history, request)` per user
   turn — Gradio auto-injects the current visitor's `gr.Request` as the
   `request` keyword argument since `chat()`'s signature declares it
   (`request: gr.Request | None = None`). `chat()` first derives a caller
   identity via `rate_limit.caller_key(request)` and calls
   `rate_limit.check_chat_turn(caller, message)` (§7) **before** building the
   system prompt or making any Anthropic API call:
   - `rate_limit.MessageTooLong` → returns `FALLBACK_TOO_LONG` immediately;
     no budget is consumed.
   - Any other `rate_limit.RateLimited` (burst/sustained window, daily
     turn/token budget exhausted) → logs at `INFO` (`"Turn refused for %s:
     %s"`), returns `FALLBACK_RATE_LIMITED`.
   If the turn is allowed, `rate_limit.set_current_caller(caller)` stashes
   the caller identity in a `ContextVar` for the rest of the turn — reset in
   a `finally` block around the whole call — so `services/tools.py` can
   recover it later (§6) without the caller having to be threaded through
   every function signature down to the tool layer.
2. `chat()` then calls the real implementation, `_chat()`, inside a
   `try`/`except` (`@observe(name="chat_turn")` on both):
   - `anthropic.RateLimitError`, `anthropic.InternalServerError`,
     `anthropic.APIConnectionError` (transient) → logs a warning, returns
     `FALLBACK_BUSY`.
   - `anthropic.APIError` (e.g. 400/401/403 — misconfiguration) → logs an
     error, returns `FALLBACK_GENERIC`.
   - Any other `Exception` (tool failures, resource-file read failures,
     etc.) → logs the full traceback server-side, returns `FALLBACK_GENERIC`
     to the visitor.
   All four fallback strings are defined in `services/profile.py`. This
   means an API hiccup, a downstream tool exception, or a rate-limit refusal
   all surface to the visitor as a short, in-character sentence, never a raw
   traceback in the Gradio window.
3. `_chat()` normalizes `history` to `{role, content}` (Gradio's dict format
   carries extra keys like `metadata`/`options` that the Anthropic API
   rejects), builds the system prompt via
   `services.profile.get_system_prompt_for_profile()` (with `cache_control:
   {"type": "ephemeral"}` for prompt caching), and enters a
   `for iteration in range(MAX_TOOL_ITERATIONS)` loop (`MAX_TOOL_ITERATIONS
   = 5`) calling `client.messages.create(model="claude-haiku-4-5",
   max_tokens=1024, system=..., messages=..., tools=tools)`. Immediately
   after each call, `rate_limit.record_usage(response.usage)` charges the
   global daily token budget (§7) — this runs on **every** round trip inside
   the loop, not just the one that produces the final answer, so a
   multi-step tool-use chain is charged for all of it.
4. The Anthropic client itself is constructed with `max_retries=4,
   timeout=30.0` — transient errors get an SDK-level retry with backoff
   before ever reaching the `try`/`except` in `chat()`.
5. If `response.stop_reason == "tool_use"`, all `tool_use` blocks are
   dispatched via `handle_tool_calls()`, results are appended to the message
   list as a `tool_result` user turn, and the loop repeats. Otherwise the
   loop `break`s.
6. If the loop runs all `MAX_TOOL_ITERATIONS` iterations without a `break`,
   the `for...else` clause logs a warning and the turn ends using whatever
   the last response was — this bounds the number of round-trips (and Claude
   API calls) per chat turn.
7. `handle_tool_calls()` dispatches by `tool_name`, wrapping the call in its
   own `try`/`except Exception as e: result = {"error": str(e)}` — a
   downstream failure (e.g. Gmail send throws) degrades to an error result
   for that one tool call rather than crashing the turn. An unrecognized
   `tool_name` similarly returns `{"error": f"Tool not found: {tool_name}"}`.
   In both cases the error is returned as a plain string inside the
   `tool_result`'s `content` field, **not** via the Anthropic tool_result
   envelope's `is_error` field — see §12, item 2.
8. The final assistant text blocks are concatenated into the reply. If a turn
   ends with only a tool call and no visible text, a canned acknowledgement
   ("Thanks — I've noted that down...") is returned instead of an empty
   string.
9. `gr.ChatInterface(fn=chat).launch(show_error=False)` — Gradio's own
   error-surfacing UI is suppressed, consistent with `chat()` already
   converting every failure into a visitor-facing sentence itself.

## 5. Persona / system prompt (`services/profile.py`)

- Hardcoded persona name: `"Sourav Ghosh"`.
- `FALLBACK_BUSY`, `FALLBACK_GENERIC`, `FALLBACK_RATE_LIMITED`, and
  `FALLBACK_TOO_LONG` — the four canned strings `chat()` returns on error or
  rate-limit refusal (§4, §7) — are defined here alongside the prompt
  builder.
- The system prompt is substantially more detailed than a simple "answer
  from the résumé" instruction. It defines:
  - **In-scope vs. out-of-scope.** Career/background/skills/projects/
    education/experience questions are answered directly. Availability
    (notice period, relocation, role type) is answered from a dedicated
    resource file. Compensation and reasons-for-leaving are explicitly
    *not* answered or estimated — the model is told to decline and invite
    an email instead, asked at most once per conversation.
  - **Two distinct "can't answer" cases:** (1) in-scope but not covered by
    the background material → call `record_unknown_question`; (2)
    genuinely out-of-scope (current events, unrelated coding help, trivia,
    private matters) → decline in character, no tool call. Ambiguous cases
    default to (1) (record rather than silently drop).
  - **Technology-claim discipline:** check abbreviations/aliases (K8s ↔
    Kubernetes, Postgres ↔ PostgreSQL) before answering; a straight "no" is
    preferred over hedging or inferring experience from an adjacent
    technology.
  - **Contact capture rules:** only record a volunteered email address,
    never invent or complete one, ask at most once.
  - **Prompt-injection resistance:** visitor text is always treated as a
    question, never as an instruction that changes the rules above; the
    model is told to decline briefly if asked to ignore instructions,
    reveal the prompt, or record something using visitor-dictated wording.
- Background context is sourced from **four** files, read fresh on every
  request, in this order:
  1. `resources/summary.txt` — short free-text bio (`get_summary()`).
  2. `resources/SOURAV_GHOSH_CAREER_PROFILE.md` — a detailed, structured
     career profile (`get_career_profile_details()`).
  3. `resources/CURRENT_STATUS_AND_PREFERENCES.md` — notice period,
     relocation, role-type, and the compensation/reasons-for-leaving
     redirect policy (`get_current_preferences()`).
  4. `resources/SOURAV_GHOSH_LINKEDIN.pdf` — full LinkedIn export, text
     extracted page-by-page via `pypdf.PdfReader` (`get_linkedin_details()`).
  All four resource-reading helpers now consistently resolve their path from
  `base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`,
  so the app works regardless of the process's current working directory.
  (Earlier revisions of this project briefly dropped the LinkedIn PDF from
  the live prompt and had one resource path resolved relative to the cwd
  instead of `base_dir` — both have since been corrected; see git history if
  useful context, they're not current issues.)

## 6. Tools (`services/tools.py`)

Two tools are exposed to the model via the Anthropic `tools` parameter, each
wrapped with `@observe()` for Langfuse tracing:

| Tool | Required args | Optional args | Effect |
|---|---|---|---|
| `record_user_details` | `email` | `name`, `notes` | Sends an **immediate** email via `MailUtility`, subject `"Career Persona — interest received [<date>]"`. Capped per caller by `rate_limit.check_contact_email()` (§7) — see below. |
| `record_unknown_question` | `question` | — | Calls `store_question(...)` (`services.question_store_db.store_question`), inserting a row into the Postgres `unknown_questions` table for the nightly digest — see §9. |

`record_user_details` calls `rate_limit.check_contact_email(rate_limit.get_current_caller())`
(§7) before sending. If the caller has already triggered
`CHAT_EMAIL_MAX_PER_CALLER` (default 2) notification emails within
`CHAT_EMAIL_WINDOW_SECONDS` (default 3600), the `RateLimited` exception is
caught right there, logged at `INFO` (`"Suppressed contact email: %s"`), and
the function returns `{"recorded": "ok"}` without sending — the model and
the visitor never learn the email was suppressed, since the goal is to stop
`record_user_details` being usable as an open relay to the owner's inbox
without changing the model's perceived behavior.

Tool descriptions (`RECORD_USER_DETAILS_TOOL_DESCRIPTION`,
`UNKNOWN_QUESTION_TOOL_DESCRIPTION`) are deliberately detailed: they tell the
model not to invent/guess/complete an email address, not to copy
visitor-dictated wording into `notes` (a prompt-injection guard mirrored in
the system prompt, §5), and to reserve `record_unknown_question` strictly for
in-scope-but-uncovered questions.

Both tools return `{"recorded": "ok"}` to the caller regardless of downstream
success/failure — the model is not told a `send_email`/`store_question` call
actually failed (`handle_tool_calls()`'s `try`/`except` catches the raised
exception one layer up and turns it into an `{"error": ...}` tool result
instead, per §4 item 6, but the tool function itself has no concept of
partial failure).

`record_unknown_question` stores `f"Recording unknown question: {question}"`
— the literal prefix, not just the raw question — as the `question` column
value in the Postgres `unknown_questions` table (§9, §11). This is pinned by
`tests/unit/test_tools.py::TestRecordUnknownQuestion::
test_stores_question_with_recording_prefix`, i.e. it reads as
intentional/expected behavior rather than an unnoticed bug, though it still
means the eventual digest email reads "Recording unknown question:
<question>" rather than just the question text.

## 7. Rate limiting & spend caps (`services/rate_limit.py`)

Inbound rate limiting and spend caps for the public chat endpoint. The
Anthropic SDK already retries upstream 429s (`max_retries=4` on the app's
client, §4), and `chat()` degrades those to `FALLBACK_BUSY` — that's the
*outbound* direction (what the Anthropic API does to you). This module is
the *inbound* direction: limiting what an anonymous visitor can spend on
your behalf.

**Guards, checked cheapest-first inside `check_chat_turn(caller, message)`**
(`app.py` calls this before any Anthropic API call, §4) so a blocked turn
never touches the network or consumes global budget:

1. `MESSAGE_MAX_CHARS` (default 2,000, env `CHAT_MESSAGE_MAX_CHARS`) —
   reject oversized input before anything else. Raises `MessageTooLong`.
2. Daily token budget (`DAILY_TOKENS`, default 5,000,000/day, env
   `CHAT_GLOBAL_DAILY_TOKENS`) — hard ceiling on spend per day, checked via
   `ensure_available()` (raises `BudgetExhausted` without consuming).
3. Daily turn cap (`DAILY_TURNS`, default 750/day, env
   `CHAT_GLOBAL_DAILY_TURNS`) — a circuit breaker independent of token
   accounting; `record(1)` is called immediately after the check passes, so
   a turn counts against the cap even if the downstream API call later
   fails.
4. Per-caller sliding windows — `BURST` (default 5 turns/60s, env
   `CHAT_BURST_MAX_TURNS`/`CHAT_BURST_WINDOW_SECONDS`) and `SUSTAINED`
   (default 40 turns/3,600s, env `CHAT_SUSTAINED_MAX_TURNS`/
   `CHAT_SUSTAINED_WINDOW_SECONDS`) — both raise `CallerThrottled`.

A fifth, separate guard — `CONTACT_EMAILS` (default 2/3,600s, env
`CHAT_EMAIL_MAX_PER_CALLER`/`CHAT_EMAIL_WINDOW_SECONDS`) — caps outbound
notification emails per caller via `check_contact_email(caller)`, called
from `record_user_details` (§6) rather than from `check_chat_turn`, since it
guards a specific tool side effect, not the turn itself.

**Primitives:**

- `SlidingWindowLimiter(max_events, window_seconds, name, max_keys=10_000,
  clock=time.monotonic)` — thread-safe (`threading.Lock`), keyed by caller,
  backed by an `OrderedDict[str, deque[float]]` of hit timestamps. `clock`
  is injectable so tests can advance time without sleeping (§15). Caller
  state is bounded by `max_keys` (env `CHAT_MAX_TRACKED_CALLERS`, default
  10,000) and evicted least-recently-seen first — an attacker rotating
  source addresses can flush honest callers out of the table, which is what
  the global daily caps (2–3 above) are for. A rejected `check_and_record()`
  call does **not** record a hit, so a hammering client cannot extend its
  own lockout by retrying.
- `DailyBudget(max_units, name, clock=lambda: datetime.now(TIMEZONE))` —
  thread-safe counter that rolls over at local midnight in `TIMEZONE`
  (`Asia/Kolkata`, matching the digest scheduler, §9). `ensure_available()`
  checks without consuming; `record()` consumes and deliberately allows
  overshoot on the turn that pushes it over, since token cost is only known
  after the API call returns.

**Caller identity (`caller_key(request)`):** derived from the incoming
`gr.Request`. IP (`request.client.host`) is the best available signal for an
unauthenticated endpoint — imperfect (shared NAT lumps colleagues together,
a rotating client escapes it), which is why it's backed by the global daily
caps rather than relied on alone. Falls back to `request.session_hash`, then
`"unknown"`, if no client host is available (e.g. `request is None` in
tests). `X-Forwarded-For` is only trusted when `CHAT_TRUST_PROXY_HEADER=true`
(default `False`) — exposed directly to the internet, a client can forge
that header and mint itself a fresh quota on every request, so this must
only be enabled behind a proxy you control that overwrites/strips it.

**Context propagation:** `set_current_caller(key)` / `get_current_caller()`
/ `reset_current_caller(token)` wrap a module-level `ContextVar`, set by
`chat()` for the duration of a turn (§4) and read by
`record_user_details` (§6) — this lets the tool layer know who's calling
without the caller identity being threaded through every function signature
between `app.py` and `services/tools.py`.

**Entry points used elsewhere:**

| Function | Called from | Purpose |
|---|---|---|
| `check_chat_turn(caller, message)` | `app.chat()` | All four turn-level guards, in order (see above) |
| `check_contact_email(caller)` | `services.tools.record_user_details` | The per-caller email cap |
| `record_usage(usage)` | `app._chat()`, after every `client.messages.create()` | Sums `input_tokens + output_tokens + cache_creation_input_tokens + cache_read_input_tokens` (raw counts, not cost-weighted — cache reads bill at 0.1x input, cache writes at 1.25x, output is priced higher than input; a dollar cap would need to weight these) and charges `DAILY_TOKENS` |
| `reset_all()` | Tests only (`tests/conftest.py`, §15) | Clears every module-level counter |

**State is in-process and deliberately not persisted** — losing it on
restart is correct behavior for a limiter (unlike the pending-questions
store, §9), but it does mean the limits are *per worker*: run a single
process, or move the counters to Redis, before scaling out to multiple
workers.

## 8. Email notifications (`services/mail_utility.py`)

- `MailUtility` sends emails using the **Gmail API**
  (`googleapiclient` `gmail.v1`, scope `gmail.send`), authenticated via a
  stored OAuth refresh token (`google.oauth2.credentials.Credentials`, no
  access token cached — refreshed automatically on use).
- Construction is lazy: `MailUtility.__init__` does no credential/service
  work at all. The Gmail service is built (and cached on `self._service`)
  the first time `.service` is accessed — in practice, the first time
  `send_email()` is called. Importing/instantiating `MailUtility` never
  requires valid Gmail credentials or performs a client build for a process
  that never ends up sending an email.
- `mail_utility.py` constructs one module-level singleton,
  `mail_util = MailUtility()`, imported by both `services/tools.py` (immediate
  notifications) and `services/digest.py` (daily digest) — a single shared,
  lazily-initialized instance rather than each caller building its own.
- `send_email(subject, body)` takes an explicit subject; callers each
  construct their own dated subject line.
- The recipient is read from `os.getenv("GMAIL_RECIPIENT")`. `send_email()`
  validates it up front and raises `RuntimeError("GMAIL_RECIPIENT
  environment variable is not set")` if it's unset/empty, rather than
  letting a `None` header value fail later during message serialization.
  This check runs before the lazy `.service` property is ever touched, so a
  missing recipient never triggers a Gmail client build either.
- This is the single Gmail-sending mechanism used by both the immediate
  notification path (`tools.py`) and the daily digest (`digest.py`).

## 9. Daily digest (`services/digest.py`, `services/question_store_db.py`, `services/db.py`)

- `store_question` in `services/question_store_db.py` (called from
  `record_unknown_question`, §6) is now the sole producer for the pending
  store — it inserts a row into the Postgres `unknown_questions` table. This
  replaces the old JSONL-based `services/question_store.py::store_question`,
  which is no longer called anywhere in the app (§11, §12 "Fixed since the
  last pass").
- `app.py`'s `__main__` block calls `services.db.init_db()` before
  `start_scheduler()` (§3), so the `unknown_questions` table
  (`id BIGSERIAL PRIMARY KEY, question TEXT NOT NULL, created_at TIMESTAMPTZ
  DEFAULT now(), sent_at TIMESTAMPTZ`, plus a partial index on `created_at
  WHERE sent_at IS NULL`) is created on startup if it doesn't already exist.
  `init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS`).
- `start_scheduler()` is called unconditionally from `app.py`'s `__main__`
  block — **the digest scheduler runs by default**, not opt-in. It starts an
  **APScheduler** `BackgroundScheduler` with a cron trigger firing daily at
  **21:30 Asia/Kolkata**, idempotent (`id="daily_digest"`,
  `replace_existing=True`; a module-level `_scheduler` guard prevents
  double-start within one process).
- `send_daily_digest()` reads pending entries via
  `services.question_store_db.fetch_pending()` — a Postgres query
  (`SELECT id, question, created_at FROM unknown_questions WHERE sent_at IS
  NULL ORDER BY created_at`) against a connection pool built by
  `services/db.py::get_pool()` from the `DATABASE_URL` env var (§14). If
  `fetch_pending()` returns `[]`, the function returns immediately, with no
  log line either way — there is no "skipping digest" print on the empty
  path (unlike the old JSONL implementation).
- On a non-empty `fetch_pending()` result, `send_daily_digest()` builds the
  digest body (`_build_message_subject_and_body`, unchanged logic) and calls
  `mail_util.send_email(subject, body)` — through the same shared
  `services.mail_utility.mail_util` singleton `tools.py` uses. On success,
  `mark_sent([q["id"] for q in pending])` runs an `UPDATE ... SET sent_at =
  now() WHERE id = ANY(%s)` against the fetched ids — rows are marked sent,
  not deleted.
- **There is no try/except around the send call.** A `send_email()`
  exception propagates straight out of `send_daily_digest()`; nothing gets
  marked sent, so the same rows are retried on the next scheduled run.
  APScheduler's job executor catches and logs the exception itself rather
  than crashing the process, but there is no application-level log line
  marking the failure the way the old JSONL implementation had one
  (`"Failed to send digest email: {e}"`). This is exercised by
  `TestSendDailyDigest::test_send_failure_propagates_and_leaves_pending_unmarked`
  in `tests/unit/test_digest.py`, which asserts the exception propagates
  rather than being caught.
- **Not covered by any test that exercises a real Postgres round-trip.**
  `tests/unit/test_digest.py` mocks `digest.fetch_pending`/`digest.mark_sent`
  directly, so it verifies `send_daily_digest()`'s logic in isolation but
  never proves `question_store_db.store_question()` and
  `question_store_db.fetch_pending()` actually agree on schema/columns
  against a real database. `tests/unit/test_question_store_db.py` is the
  file meant to cover that and currently has no test functions at all — see
  §15.

## 10. Observability (Langfuse / OpenInference)

- `app.py` explicitly calls `langfuse = get_client()` **before**
  `AnthropicInstrumentor().instrument()` — this registers Langfuse as the
  global OTEL `TracerProvider`/exporter first, so the instrumentor's spans
  are captured rather than emitted against a no-op provider. Ordering here
  is load-bearing, per the inline comment.
- `chat()` and `_chat()` are both decorated `@observe(name="chat_turn")`;
  `record_user_details` and `record_unknown_question` are both decorated
  `@observe()`. Combined with `AnthropicInstrumentor`'s auto-instrumentation
  of every `client.messages.create()` call, a single chat turn's trace spans
  the model call(s), tool dispatch, and tool side effects.
- `tests/sanity_checks/langfuse_test.py` (moved here from
  `services/langfuse_test.py`) is a standalone connectivity check
  (`verify_connection()` / `@observe`-decorated `test_generation()`) run via
  `python -m tests.sanity_checks.langfuse_test`; not imported by the main
  app, and not collected by `pytest` (§15). It has an unused `Langfuse`
  import and a commented-out manual client construction block — harmless,
  but dead code.
- Langfuse client configuration (public/secret key, base URL) is expected via
  environment variables, resolved implicitly by the Langfuse SDK's default
  client (`get_client()`) rather than being passed explicitly in code.

## 11. Data storage

| Path / table | Format | Purpose | Lifecycle |
|---|---|---|---|
| `unknown_questions` (Postgres table, schema in `services/db.py`) | Postgres | Pending/archived unanswered questions — columns `id`, `question`, `created_at`, `sent_at` (NULL = pending) | Inserted by `services.question_store_db.store_question` (called from `record_unknown_question`, §6); read by `fetch_pending()` and marked sent by `mark_sent()` in `services/digest.py` (§9) — the live, single store |
| `data/unknown_questions.jsonl` | JSON Lines | Legacy pending-questions file from the pre-Postgres implementation | **Orphaned.** `services/question_store.py::store_question` still writes here if called, but nothing in the app calls it any more; `read_pending`/`clear_pending` are unused. Still covered by its own unit test (`tests/unit/test_question_store.py`), which tests the module in isolation, not as part of the app's live path |
| `data/sent_questions.jsonl` | JSON Lines | Legacy archive from the pre-Postgres digest flow | Orphaned along with the above — nothing writes to it any more |

Persistence for unanswered questions is now a single Postgres table
(`unknown_questions`, via `services/db.py`'s connection pool,
`DATABASE_URL`), with `services/question_store.py`'s JSONL implementation
left in the codebase but unused by the running app — see §12, "Fixed since
the last pass".

## 12. Known errors / issues (as observed in code)

Ordered roughly by how likely each is to bite in practice.

1. **`python app.py` now hard-fails on startup without a reachable
   `DATABASE_URL`.** `init_db()` runs unconditionally before the Gradio
   server starts (§3, §9); `services.db.get_pool()` raises `RuntimeError`
   immediately if `DATABASE_URL` is unset, and `psycopg`'s connect will
   raise if it's set but unreachable. This is a behavior change from every
   other external dependency in the app (Gmail, Langfuse, Anthropic), which
   fail lazily on first use rather than blocking startup. A fresh clone
   following only the Gmail/Langfuse setup steps in `README.md`, without
   also standing up Postgres and setting `DATABASE_URL`, will not start.
   Not covered by any test (`tests/unit/test_app_chat.py` etc. never invoke
   `app.py`'s `__main__` block). See §3, §14.

2. **Tool failures are reported via a plain `{"error": ...}` string, not the
   SDK's `is_error` field.** `handle_tool_calls()` (§4, item 6) prevents a
   downstream exception from crashing the turn, but the model is not told
   the call failed in the way the Anthropic tool-use API is designed for
   (the `tool_result` block's `is_error: true` flag). A visitor can still be
   told "I've noted that down" by the model even when the underlying
   `send_email`/`store_question` call actually raised. This is deliberately
   pinned as an accepted, tracked gap by two `xfail(strict=True)` tests in
   `tests/unit/test_app_tool_dispatch.py::TestKnownBugs`:
   `test_tool_failure_is_not_reported_as_success` and
   `test_unknown_tool_is_reported_with_the_sdks_is_error_field`. These are
   the *only* two non-green results in a plain `pytest` run — see §15.

3. **Stale bug narratives in test docstrings
   (`tests/unit/test_app_chat.py`, `tests/unit/test_app_tool_dispatch.py`).**
   `TestFailureHandling::test_api_error_does_not_surface_a_traceback`'s
   docstring says the test "Currently, fails" because `chat()` allegedly has
   no `try`/`except` around `client.messages.create()`. It does now (§4),
   and the test actually **passes** — a generic `RuntimeError` is caught by
   `chat()`'s final `except Exception` clause. Likewise
   `TestKnownBugs::test_dispatch_does_not_raise_on_tool_failure`'s docstring
   claims `handle_tool_calls()` "does not catch exceptions raised by the
   dispatched tool function," but it does now (§4, item 6), and this test
   also passes. Both fixes landed without the corresponding test comments
   being updated, so reading the test file alone currently gives an
   inaccurate picture of what's broken — the actual `pytest` run (§15) is
   the source of truth, not these docstrings.

4. **`services/question_store.py` (the JSONL implementation) is now dead
   code from the app's perspective.** Nothing calls `store_question`,
   `read_pending`, or `clear_pending` any more — `record_unknown_question`
   was repointed at `services.question_store_db.store_question` (§6, §9,
   §11). The module and `data/unknown_questions.jsonl`/
   `data/sent_questions.jsonl` are still present, and
   `tests/unit/test_question_store.py` still exercises the module directly,
   which can read as "this is load-bearing" to someone skimming the test
   suite when it no longer is. Not deleted as part of this fix; worth a
   follow-up decision (delete vs. keep as a documented fallback).

5. **The judged suite's judge client is constructed without the retry/timeout
   tuning the app's own client uses (`tests/evals/llm_judge.py::judge`).**
   `anthropic.Anthropic()` is called bare, unlike `app.py`'s
   `anthropic.Anthropic(max_retries=4, timeout=30.0)`. Minor and test-only —
   a flaky judge call fails the eval run rather than degrading gracefully —
   but worth aligning if judged runs start showing transient-error noise.

Fixed since the last pass:
- **The judged eval dataset had two context/criteria gaps that made the judge
  fail correct answers.** `faith_001`'s and `avail_001`'s `context:` lists in
  `tests/evals/judged_eval_cases.yaml` didn't match what the real system
  prompt (`services/profile.py`) actually feeds the model: `faith_001` named
  only `resources/summary.txt`/`resources/SOURAV_GHOSH_LINKEDIN.pdf`, and
  `avail_001` named `resources/current_status.md`, a path that doesn't
  exist — the real file is `resources/CURRENT_STATUS_AND_PREFERENCES.md`.
  Neither case's context included `resources/SOURAV_GHOSH_CAREER_PROFILE.md`,
  which is where the "4+ years" AWS claim, the DVA-C02 certification, and the
  Kolkata/Bangalore relocation detail actually come from. The judge, shown a
  narrower context than the app itself, failed the persona for stating facts
  it had no way to verify. `avail_001`'s bug was worse in practice: because
  the named context file didn't exist, `load_context()`
  (`tests/evals/test_judged_by_llm_cases.py`) silently `pytest.skip()`-ped
  the case on every run instead of failing loudly, so it went unnoticed until
  the full suite was run and a live response happened to include the
  relocation detail. Fixed by adding
  `resources/SOURAV_GHOSH_CAREER_PROFILE.md` to both cases' `context:` lists
  and correcting `avail_001`'s path. Separately, tightened the
  `known_good_ai_disclaimer` calibration case's criteria (in
  `test_judged_by_llm_cases.py`) — it was ambiguous enough that the judge
  treated an honest "I'm a digital stand-in" answer as identifying itself as
  an AI-like entity; added an explicit carve-out mirroring `persona_002`'s
  wording (acknowledging a digital stand-in is not the same as identifying as
  an AI/assistant/language model). `pytest -m live
  tests/evals/test_judged_by_llm_cases.py` now reports `15 passed` — the
  judged layer's first clean full run (§15).
- **The daily digest's producer and consumer now use the same store.**
  `record_unknown_question` (`services/tools.py`) was switched from
  `services.question_store.store_question` (JSONL) to
  `services.question_store_db.store_question` (Postgres) — the same module
  `services/digest.py`'s `fetch_pending()`/`mark_sent()` already read
  from/wrote to. Previously these were pointed at two different stores, so
  `fetch_pending()` always returned `[]` and the digest was a permanent
  no-op regardless of how many unanswered questions accumulated. `app.py`'s
  `__main__` block now also calls `services.db.init_db()` before
  `start_scheduler()`, so the `unknown_questions` table is created on
  startup rather than only via a test fixture. See §2, §9, §11. Not yet
  covered by a dedicated test that exercises a real Postgres round-trip —
  see §9's last bullet and §15.
- `services/digest.py`'s module docstring is now accurate — it describes
  sending via the Gmail API and marking rows sent, rather than the old
  "Gmail SMTP ... archived" language that no longer matched either the
  transport or the read path. The commented-out legacy JSONL
  `send_daily_digest()` and its now-dead imports (`read_pending`,
  `clear_pending`, `date`) were removed from the file at the same time.
- `GMAIL_RECIPIENT` is now validated — `MailUtility.send_email()` raises a
  clear `RuntimeError` up front if it's unset/empty, instead of failing later
  with an opaque `EmailMessage` serialization error (see §8). Pinned by
  `tests/unit/test_mail_utility.py::test_send_email_raises_clear_error_when_recipient_is_unset`.
- `MailUtility` construction is now lazy (the Gmail service is built on first
  use, not at `__init__`), and `services/digest.py` now sends through the
  same shared `mail_util` singleton `services/tools.py` uses instead of
  constructing its own `MailUtility()` on every scheduled run (see §8, §9).
  Pinned by
  `tests/unit/test_mail_utility.py::test_init_does_not_build_service_eagerly`,
  `test_service_is_built_lazily_on_first_use_and_then_cached`, and the
  updated `tests/unit/test_digest.py::TestSendDailyDigest` cases.
- `pytest.ini`'s `--strict-markers` flag, briefly dropped in the same change
  that added the `db` marker, has been restored (§15) — an
  unregistered/misspelled marker is a hard collection error again, not a
  silent no-op.

## 13. External dependencies

From `requirements.txt`:

| Package | Role |
|---|---|
| `anthropic` (0.117.0) | Claude Messages API client (app client constructed with `max_retries=4, timeout=30.0`) |
| `gradio` (6.3.0) | Chat web UI (`ChatInterface`) |
| `python-dotenv` (1.2.1) | Loads `.env` into process environment |
| `pypdf` (6.6.0) | Extracts text from the LinkedIn PDF export, used in the live prompt (§5) and by the judged suite's `load_context()` for PDF-backed eval cases |
| `requests` (2.32.5) | HTTP client — no active call site in `services/` or `app.py`; likely an unused direct dependency now that the legacy Pushover notifier has been removed |
| `google-auth`, `google-auth-oauthlib`, `google-api-python-client` | Gmail API OAuth client + service build |
| `apscheduler` (3.11.0), `pytz` (2025.2) | Cron-style background scheduling for the daily digest; `pytz` is also used by `services/rate_limit.py`'s `DailyBudget` for the same Asia/Kolkata midnight rollover (§7) |
| `psycopg[binary]` (3.2.10), `psycopg-pool` (3.2.6) | Postgres client + connection pooling for `services/db.py`'s `unknown_questions` table (§9, §11) — used by both `record_unknown_question`'s write path and the digest's read path, plus `tests/unit/test_question_store_db.py`'s fixture |
| `langfuse` | LLM tracing/observability backend client |
| `openinference-instrumentation-anthropic` | Auto-instruments the Anthropic SDK for Langfuse/OpenTelemetry tracing |

Model used: `claude-haiku-4-5` (hardcoded in `app.py`). The judged eval suite
uses a separate, configurable model (`EVAL_JUDGE_MODEL`, default
`claude-sonnet-5` — see §15).

**Dev/test dependencies** (`requirements-dev.txt`, layered on top of
`requirements.txt` via `-r requirements.txt`): `pytest==9.1.1`,
`pytest-cov==7.1.0`, `pyyaml==6.0.3` (the last one for parsing
`tests/evals/deterministic_eval_cases.yaml` and
`tests/evals/judged_eval_cases.yaml`). See §15.

## 14. Configuration (environment variables)

Loaded from a gitignored `.env` file via `python-dotenv`:

| Variable | Used by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `app.py` (implicit, via `anthropic.Anthropic()`) | Claude API auth |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | `mail_utility.py` | OAuth credentials for the Gmail API (used by both immediate notifications and the daily digest) |
| `GMAIL_RECIPIENT` | `mail_utility.py` | Recipient address for all outgoing notification/digest emails — **required**; `send_email()` raises a clear `RuntimeError` if it's unset (§8) |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Langfuse SDK (implicit, via `get_client()`) | Tracing backend auth/endpoint |
| `CHAT_MESSAGE_MAX_CHARS` | `rate_limit.py` | Max chars per chat message before `MessageTooLong` (default `2000`) — optional, tuning only (§7) |
| `CHAT_BURST_MAX_TURNS`, `CHAT_BURST_WINDOW_SECONDS` | `rate_limit.py` | Per-caller burst window (default `5` turns / `60`s) — optional (§7) |
| `CHAT_SUSTAINED_MAX_TURNS`, `CHAT_SUSTAINED_WINDOW_SECONDS` | `rate_limit.py` | Per-caller sustained window (default `40` turns / `3600`s) — optional (§7) |
| `CHAT_GLOBAL_DAILY_TURNS` | `rate_limit.py` | Global daily turn cap, circuit breaker independent of token accounting (default `750`) — optional (§7) |
| `CHAT_GLOBAL_DAILY_TOKENS` | `rate_limit.py` | Global daily token budget, raw (not cost-weighted) token count (default `5_000_000`) — optional (§7) |
| `CHAT_EMAIL_MAX_PER_CALLER`, `CHAT_EMAIL_WINDOW_SECONDS` | `rate_limit.py` | Per-caller cap on `record_user_details` notification emails (default `2` / `3600`s) — optional (§6, §7) |
| `CHAT_MAX_TRACKED_CALLERS` | `rate_limit.py` | Bound on tracked caller keys per sliding-window limiter, LRU-evicted beyond it (default `10_000`) — optional (§7) |
| `CHAT_TRUST_PROXY_HEADER` | `rate_limit.py` | Whether `caller_key()` trusts `X-Forwarded-For` (default `false`) — **only enable behind a proxy you control**; otherwise a visitor can forge it to mint a fresh quota (§7) |
| `DATABASE_URL` | `services/db.py` (`get_pool()`), called from `app.py`'s `__main__` via `init_db()` | Postgres connection string for the `unknown_questions` table (§9, §11) — **required to start the app at all**: `init_db()` runs unconditionally before the Gradio server launches (§3) and raises `RuntimeError("DATABASE_URL is not set")` immediately if missing (§12, item 1). Also required at runtime by `record_unknown_question` (write path) and `services/digest.py::send_daily_digest()` (read path) |
| `TEST_DATABASE_URL` | `tests/unit/test_question_store_db.py` | Points the `db`-marked test file at a real (throwaway) Postgres instance; those tests are skipped via `pytest.mark.skipif` when unset, and excluded from a plain `pytest` run regardless via `addopts` (§15) |
| `EVAL_JUDGE_MODEL` | `tests/evals/llm_judge.py` | Overrides the judge model (default `claude-sonnet-5`) — test-only, not needed to run the app |
| `EVAL_JUDGE_SAMPLES` | `tests/evals/llm_judge.py` | Number of judge calls per judged case, majority-vote (default `1`) — test-only |

All `CHAT_*` rate-limit variables are optional — every one has a code-level
default, read via `rate_limit.py`'s `_int_env`/`_bool_env` helpers, which
fall back to the default (and log a warning) on a non-integer value rather
than raising.

No other environment variables are referenced anywhere in the current code
(beyond `DATABASE_URL`/`TEST_DATABASE_URL` above).

There is no `client_secret.json` or other OAuth secret file in the working
tree at this point — if one is (re)introduced, it should be added to
`.gitignore` immediately, as it would contain sensitive credential material.

## 15. Testing

Two layers under `tests/`, plus a third, currently-empty one, all run with
`pytest` from the repo root. There is exactly one `pytest.ini` in the repo
(at the root); it registers the `unit`/`live`/`judged`/`db` markers, sets
`--strict-markers` (an unregistered marker fails collection rather than
being silently accepted), and defaults `addopts` to `-m "not live and not
db"`, so a plain `pytest` run never makes a real API call, never touches a
real Postgres database, and never costs tokens. `--strict-markers` was
briefly dropped in the same change that added the `db` marker, and has
since been restored (§12, "Fixed since the last pass").

- **`tests/unit/`** — fast, deterministic, no network, marked
  `pytest.mark.unit`. Every module under `services/` has a matching test
  file (`test_digest.py`, `test_mail_utility.py`, `test_profile.py`,
  `test_question_store.py`, `test_tools.py`, `test_rate_limit.py`);
  `app.py` is split by function rather than given one file —
  `test_app_chat.py` covers `chat()`/`_chat()`, `test_app_tool_dispatch.py`
  covers `handle_tool_calls()`. All external calls (Anthropic, Gmail,
  Langfuse) are mocked. `test_rate_limit.py` (22 cases, §7) instead injects a
  fake clock (`FakeClock`/`FakeDayClock`) into `SlidingWindowLimiter`/
  `DailyBudget` per test, so the suite stays deterministic and fast — no
  sleeping, no wall-clock dependence, no flake at midnight IST.
  `tests/conftest.py` seeds dummy credential env vars, stubs
  `googleapiclient.discovery.build` for the whole session (so even a real
  `.env` sitting in the working directory, as it does in this repo, can't
  cause a real network call from the unit layer), and — as of the rate-limit
  changes — runs an autouse `_reset_rate_limits` fixture around every test.
  This last one matters because `rate_limit.py`'s counters (`BURST`,
  `CONTACT_EMAILS`, `DAILY_TURNS`, etc., §7) are module-level singletons
  keyed by caller and backed by the real wall clock; without resetting them,
  tests elsewhere in the suite that call `app.chat()` or
  `tools.record_user_details()` more than a couple of times with the default
  `"unknown"` caller (no `gr.Request` passed) would trip the burst/email
  limiters against each other, causing order-dependent failures unrelated to
  what those tests are actually checking.
  `services/langfuse_test.py` (the standalone Langfuse connectivity check,
  §10) has moved to `tests/sanity_checks/langfuse_test.py`, run via
  `python -m tests.sanity_checks.langfuse_test`; its old unit test,
  `tests/unit/test_langfuse_test.py`, was removed rather than updated to the
  new location. `tests/sanity_checks/` is not collected by `pytest` — the
  `python_files = test_*.py` setting in `pytest.ini` only matches
  `test_*.py`, not `*_test.py`, so this manual-run script is safely excluded
  from every automated run despite its `test_generation()` function name.
- **`tests/unit/test_question_store_db.py`** — marked `pytest.mark.db`,
  skipped via `pytest.mark.skipif` unless `TEST_DATABASE_URL` is set, and
  excluded from a plain `pytest` run by `addopts` either way. Its
  `clean_table` fixture points `DATABASE_URL` at `TEST_DATABASE_URL`, forces
  a fresh connection pool, calls `services.db.init_db()`, and truncates the
  `unknown_questions` table before each test. As of this writing the file
  defines only that fixture — **no test functions exist yet** — so `pytest
  -m db` currently collects and runs zero tests regardless of whether
  `TEST_DATABASE_URL` is set (verified: `pytest -m db -v` reports `0
  selected`). This gap matters more than it used to: `question_store_db.py`
  is now the live pending-question store for both the write path
  (`record_unknown_question`) and the read path (the digest, §9) rather than
  unused scaffolding, and nothing currently proves `store_question()` and
  `fetch_pending()`/`mark_sent()` actually round-trip correctly against a
  real Postgres schema. Run it (once tests are added) with:
  `TEST_DATABASE_URL=postgresql://... pytest -m db`.
- **`tests/evals/`** — behavioral evals against the real model, marked
  `pytest.mark.live`, run explicitly with `pytest -m live`. Two layers:
  - **Deterministic** (`test_deterministic_cases.py` + `deterministic_eval_cases.yaml`'s
    `deterministic:` section, 31 cases) makes real `client.messages.create()` calls
    through `app.chat()` and asserts deterministically: did the right tool
    fire, with the right arguments, and did the reply avoid a forbidden
    substring. No judge, no variance in the assertion itself.
  - **Judged** (`test_judged_by_llm_cases.py` + `judged_eval_cases.yaml`'s
    `judged:` section, 12 cases) runs the same kind of `app.chat()` conversation, then hands the
    transcript to a separate, stronger judge model (`EVAL_JUDGE_MODEL`,
    default `claude-sonnet-5`) that grades it PASS/FAIL against the case's
    free-text `criteria` field. The grading logic itself (`judge()`, the
    judge system prompt, majority-vote sampling) lives in `tests/evals/llm_judge.py`
    — a plain helper module, not a test file, so pytest never collects it
    directly; it's imported by `test_judged_by_llm_cases.py`, which owns the
    actual tests. Marked `pytest.mark.judged` in addition to `live`, so
    `pytest -m live` runs both layers and `pytest -m judged` runs the judged
    layer only. `test_judge_calibration` (in `test_judged_by_llm_cases.py`)
    grades three hand-labeled transcripts (no `app.chat()` call) against
    known-good/known-bad output to catch a miscalibrated judge before
    trusting it on real cases.

  A `tool_spy` fixture (`tests/evals/conftest.py`), shared by both layers,
  stubs both tools and the mail layer, so live runs — deterministic or
  judged — cannot send a real email.

Run: `pip install -r requirements-dev.txt`, then `pytest` (unit only, every
push) or `pytest -m live` (adds the deterministic and judged layers, on
demand — costs tokens; the judged layer costs tokens on two models per case).

**Current state (verified by running `pytest -q` against this checkout):**
`69 passed, 47 deselected, 2 xfailed`. The 47 deselected are all `live`
(the two eval layers) — the `db`-marked file contributes zero collected
tests either way (see above), so it doesn't change this count. The 2
`xfail(strict=True)` are the accepted, still-open `is_error` gap described
in §12, item 2 — `strict=True` means the run would break (turn red) if
either were ever fixed without removing its marker, so a fix can't silently
go unnoticed. That's the whole non-green surface of the default test run:
nothing is currently failing unexpectedly. (The unit-test count rose from 49 to 69
mainly on the addition of `test_rate_limit.py`'s 22 cases, net of a handful
of file moves/removals around the Langfuse sanity check described above.)

A one-off live deterministic run (`pytest -m live tests/evals/test_deterministic_cases.py`)
against `claude-haiku-4-5` previously returned `4 failed, 14 passed` on an
earlier, smaller version of the dataset — not harness bugs but
persona-behavior gaps (the model sometimes answers an out-of-scope question
in character instead of calling `record_unknown_question`, and once echoed
an injected note back to the visitor); see `tests/evals/README.md` for the
full breakdown. Model outputs aren't deterministic and both the system
prompt and the dataset have changed materially since that run (§5), so a
re-run of the deterministic layer may look quite different.

The judged layer has since had its first full run. Getting a clean run
required fixing two dataset bugs first — incomplete/incorrect `context:`
lists on `faith_001` and `avail_001` in `judged_eval_cases.yaml`, plus an
ambiguous `known_good_ai_disclaimer` calibration criteria — see §12, "Fixed
since the last pass," for the detail. With those fixed,
`pytest -m live tests/evals/test_judged_by_llm_cases.py` reports
`15 passed` (12 judged cases + 3 calibration cases). The eval suite is
unaffected by the rate-limit changes in
practice: `tests/evals` calls `app.chat()` directly rather than through
Gradio, so no `gr.Request` is passed and every eval turn uses the default
`"unknown"` caller key, but the root `tests/conftest.py`'s autouse
`_reset_rate_limits` fixture (function-scoped, applies to every test under
`tests/`, including `tests/evals`) clears `rate_limit`'s counters before and
after each test — so a single test making one or two `app.chat()` calls
never accumulates state across tests or trips the burst/sustained limiters,
regardless of dataset size. Only a single test that itself makes more than
`CHAT_BURST_MAX_TURNS` (default 5) `app.chat()` calls in quick succession
would need to be aware of the limiter.

## 16. Licensing

The repository is split into two licensing zones, because the code and the
personal content it ships with have different reuse intentions.

| Scope | Terms |
|---|---|
| Source code — `app.py`, `services/`, `tests/`, config files, documentation | MIT License (`LICENSE` at repo root) |
| `resources/` — `summary.txt`, `SOURAV_GHOSH_CAREER_PROFILE.md`, `CURRENT_STATUS_AND_PREFERENCES.md`, `SOURAV_GHOSH_LINKEDIN.pdf` | © 2026 Sourav Ghosh, all rights reserved. Not licensed for reuse. |
| Runtime data — `data/` (gitignored), the `unknown_questions` Postgres table (§9, §11) | Not licensed; may contain visitor-submitted contact details |

The `LICENSE` file deliberately contains the canonical, unmodified MIT text
and nothing else, so GitHub's license detection (`licensee`) matches it
cleanly — appended preamble or carve-out text is a common cause of a repo
being reported as "Other". The `resources/` carve-out therefore lives in
`README.md`'s License section rather than in `LICENSE` itself.

All third-party runtime dependencies (§13) are MIT, BSD or Apache-2.0. None
carry copyleft obligations, so MIT on this project's own code creates no
conflict. Worth re-checking with `pip-licenses` if the pinned versions in
`requirements.txt` are ever bumped.

## 17. Documentation conventions

Every module, class, and function under `app.py`, `services/`, and `tests/`
now carries a docstring in reStructuredText (reST) field-list style —
`:param:`/`:type:` for arguments, `:return:`/`:rtype:` for return values,
`:raises:` for exceptions the caller should expect. This is a documentation-
only pass: no runtime behavior changed, and the plain `pytest` run still
reports `69 passed, 47 deselected, 2 xfailed` (§15), unchanged from before it.

- **`app.py`, `services/*.py`** — module-level docstrings describe each
  file's role in the architecture (§2); function/method docstrings document
  parameters, return values, and side effects (e.g. `services/tools.py`'s
  `record_user_details` now documents the silent-suppression behavior
  described in §6, and `services/rate_limit.py`'s classes/methods carry full
  field lists alongside the prose already there, §7).
- **`services/question_store.py`** picked up a module-level `.. note::`
  pointing at `services/question_store_db.py` as the live store — a docs-only
  flag for the dead-code situation tracked in §12, item 4, not a functional
  change.
- **`tests/`** — every test module has a module docstring (added where
  missing, e.g. `tests/unit/test_question_store_db.py`,
  `tests/sanity_checks/langfuse_test.py`); test classes and fixtures document
  what they group or set up; individual test functions carry a one-line
  docstring stating the behavior under test, rather than relying solely on
  the test name. Docstrings that already existed and described a known bug
  (e.g. the `xfail(strict=True)` cases in
  `tests/unit/test_app_tool_dispatch.py::TestKnownBugs`, and the stale
  narratives flagged in §12, item 3) were left as-is — narrowing or
  correcting those is a separate, deliberate edit, not a side effect of a
  documentation pass.
- Empty `__init__.py` files (`tests/__init__.py`, `tests/evals/__init__.py`,
  `tests/unit/__init__.py`) were left empty — there is nothing to document.
- `venv/` (vendored third-party packages) and the top-level `*.md` files are
  out of scope for this convention; it applies to first-party Python source
  only.
