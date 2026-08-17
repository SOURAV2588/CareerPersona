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
- [Known limitations](#known-limitations)
- [Further documentation](#further-documentation)

## How it works

```
   Visitor
      |
      v
  Gradio ChatInterface
      |
      v
  app.chat()  ------------------> app._chat() --> Anthropic Messages API
      |   (catches API/tool             |            (claude-haiku-4-5)
      |    errors -> fallback           |   ^
      |    message, see below)          |   +------ tool results ----------+
      |                                 |                                  |
      |                                 |                          model requests a tool
      |                                 v                                  |
      |                         app.handle_tool_calls()  <-----------------+
      |                                 |
      |                                 +--> record_user_details    --> immediate email (Gmail API)
      |                                 |
      |                                 +--> record_unknown_question --> data/unknown_questions.jsonl
      |                                                                         |
      |                                                                         v
      |                                                              daily digest email (Gmail API)
      |                                                                         |
      |                                                                         v
      |                                                              data/sent_questions.jsonl
      v
  reply text
```

Each chat turn works like this:

1. The system prompt is rebuilt from your background files and sent as a top-level `system` parameter with prompt caching enabled.
2. Claude answers, or asks to call one of two tools.
3. If a tool is requested, it runs, the result is fed back, and Claude is called again. This repeats up to `MAX_TOOL_ITERATIONS` (5) times so a misbehaving model cannot loop indefinitely.
4. The final text is returned to the chat window.
5. If the Anthropic API call fails, or a tool's downstream side effect (email send, file write) raises, `chat()` catches it and returns a short in-character fallback message instead of a crash or a raw traceback. See [Design notes](#design-notes).

The two tools available to the model:

| Tool | Purpose | Effect |
|---|---|---|
| `record_user_details` | A visitor shared contact details | Sends you an email right away |
| `record_unknown_question` | The bot could not answer an in-scope question | Appends the question to a local file for the daily digest |

Out-of-scope questions (not about Sourav's professional life at all) are declined in character without calling either tool, so they never reach the digest.

## Tech stack

| Area | Choice |
|---|---|
| Language | Python 3.10+ |
| Model | Claude Haiku 4.5 (`claude-haiku-4-5`) via the Anthropic Messages API |
| UI | Gradio `ChatInterface` |
| Email | Gmail API with OAuth refresh-token auth |
| Scheduling | APScheduler cron trigger |
| Storage | JSON Lines files (no database) |
| Tracing | Langfuse with OpenInference auto-instrumentation |
| Testing | pytest, with a separate live evaluation suite |

## Project structure

```
career-persona/
├── app.py                                Entry point: chat loop, error handling, tool dispatch, Gradio launch
├── services/
│   ├── profile.py                        Builds the system prompt from background files; fallback message strings
│   ├── tools.py                          The two model-callable tools and their schemas
│   ├── mail_utility.py                   Gmail API client wrapper
│   ├── question_store.py                 Read/write/archive unanswered questions
│   ├── digest.py                         Daily digest email and its scheduler
│   └── langfuse_test.py                  Standalone Langfuse connectivity check
├── resources/
│   ├── summary.txt                       Short bio
│   ├── Sourav-Ghosh-Career-Profile.md    Detailed, structured career profile
│   ├── current_status_and_preferences.md Notice period, relocation, role type, redirect policy
│   └── SOURAV_GHOSH_LINKEDIN.pdf         LinkedIn export (currently not read into the live prompt — see Known limitations)
├── tests/
│   ├── conftest.py                       Session-wide test isolation
│   ├── unit/                             Fast, fully mocked tests
│   └── evals/                            Behavioral evaluations against the real model
├── data/                                 Created at runtime, git-ignored
├── requirements.txt                      Runtime dependencies
├── requirements-dev.txt                  Runtime plus test dependencies
└── pytest.ini                            Test configuration
```

## Getting started

### Prerequisites

- Python 3.10 or later
- An Anthropic API key
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

The persona is driven by files in `resources/`:

- `summary.txt` — a short free-text bio.
- `Sourav-Ghosh-Career-Profile.md` — a longer, structured career profile (roles, skills, domain experience).
- `current_status_and_preferences.md` — notice period, relocation, and the policy for redirecting compensation/reasons-for-leaving questions to email instead of answering them.

Replace all three with your own. `SOURAV_GHOSH_LINKEDIN.pdf` is also present and its text-extraction helper (`get_linkedin_details()` in `services/profile.py`) is still there, but the line that adds its output to the live system prompt is currently commented out — the LinkedIn export is not part of what the model sees today. If you rename the career-profile or preferences files, update the filenames in `services/profile.py`. The persona name is currently hardcoded in the same file.

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

GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
GMAIL_RECIPIENT=you@example.com

LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Authenticates calls to the Claude API |
| `GMAIL_CLIENT_ID` | For email | OAuth client ID |
| `GMAIL_CLIENT_SECRET` | For email | OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | For email | Long-lived token used to mint access tokens |
| `GMAIL_RECIPIENT` | For email | Where notifications and digests are sent — not validated at startup; if unset, sends fail with an unhelpful error (see [Known limitations](#known-limitations)) |
| `LANGFUSE_PUBLIC_KEY` | For tracing | Langfuse project key |
| `LANGFUSE_SECRET_KEY` | For tracing | Langfuse project secret |
| `LANGFUSE_BASE_URL` | For tracing | Langfuse endpoint |

## Running the app

```bash
python app.py
```

Gradio serves the chat interface at `http://127.0.0.1:7860` by default.

### The daily digest

`services/digest.py` emails you a single summary of everything the bot could not answer, scheduled for 9:30 PM IST each day. Questions are archived after a successful send, and left in place if sending fails so nothing is lost.

**The scheduler runs by default.** `start_scheduler()` is called unconditionally from `app.py`'s `__main__` block, so it starts as soon as you run `python app.py`. It's a no-op background thread until 21:30 IST — nothing is sent immediately, and nothing is sent at all if there are no pending questions.

To send a digest manually at any time:

```bash
python -m services.digest
```

To verify your Langfuse connection:

```bash
python -m services.langfuse_test
```

## Testing

The suite has two layers with different costs, separated by pytest markers.

```bash
pytest              # unit tests only: fast, free, no network
pytest -m live      # adds the evaluation suite: calls the real model, costs tokens
```

**Unit tests** (`tests/unit/`) cover every module. All external services are mocked. `tests/conftest.py` seeds dummy credentials and stubs the Gmail client for the whole session, so the unit layer cannot make a network call even when a real `.env` file is present.

**Evaluations** (`tests/evals/`) call the real model through `app.chat()` and check its behavior against a YAML dataset: whether the right tool fired, whether arguments came through intact, and whether the reply avoided forbidden claims. Email is still stubbed here, so evaluation runs cannot send real mail. See `tests/evals/README.md` for details.

Coverage report:

```bash
pytest --cov=app --cov=services --cov-report=term-missing
```

### About the failing tests

A plain `pytest` run currently reports `2 failed, 45 passed, 32 deselected, 2 xfailed`, and that is *partly* intentional:

- **2 accepted, tracked failures** (`xfail(strict=True)` in `tests/unit/test_app_tool_dispatch.py::TestKnownBugs`) — tool failures are caught so the chat turn doesn't crash, but they're still reported to the model as plain `{"error": ...}` text rather than via the Anthropic SDK's `is_error` tool-result field. `strict=True` means the run breaks again if this is ever fixed without removing the marker, so a fix can't silently go unnoticed.
- **2 unmarked, genuine failures** (`tests/unit/test_profile.py`) — these are real test/code drift, not an accepted bug: the tests assert the LinkedIn PDF's text appears in the system prompt, but that line is currently commented out in `services/profile.py` in favor of the newer career-profile and preferences files. This needs a decision (update the tests, or restore the LinkedIn line) rather than being treated as known-and-fine.

Treating the test output as a live, up-to-date bug list is deliberate — see `SPEC.md` §11 and §14 for the full breakdown, including two now-fixed bugs (unhandled Anthropic API errors, uncaught tool exceptions) whose test docstrings haven't caught up with the fix yet.

## Design notes

**Prompt caching.** The system prompt contains the full background material and is rebuilt on every request. It is marked with `cache_control: ephemeral` so repeated turns reuse the cached prefix instead of paying for those tokens again.

**Bounded tool loop.** The model can request tools repeatedly. The loop is capped at five round trips, which bounds both latency and API spend for a single chat turn.

**Graceful degradation on failure.** `chat()` wraps the whole turn in a `try`/`except`: transient Anthropic errors (rate limit, overload, connection) get one canned "I'm busy" reply, other API errors and any unexpected exception (including a downstream tool failure) get a canned generic reply with a direct-contact fallback. Gradio's own error UI is disabled (`launch(show_error=False)`) since the app already turns every failure into a visitor-facing sentence itself. The Anthropic client is also constructed with `max_retries=4, timeout=30.0`, so many transient failures are retried by the SDK before `chat()` ever sees them.

**Unanswered questions are batched, not pushed.** An immediate email for every unanswered question would be noise. Batching them into one daily digest makes the list readable, and the questions survive restarts because they are written to disk rather than held in memory.

**Files instead of a database.** Two JSON Lines files handle all persistence. For the volume this application sees, a database would add operational overhead without solving a real problem.

**One email path.** Immediate notifications and the daily digest both go through the same `MailUtility` class. An earlier version used two different mechanisms for the same job.

**Prompt-injection guardrails.** Visitor text is always treated as a question, never as an instruction that changes the system prompt's rules. Both the system prompt and the `record_user_details` tool description explicitly warn against copying visitor-dictated wording (e.g. a "note" telling the model what to say about them) into a tool call or a reply.

## Known limitations

- `GMAIL_RECIPIENT` is not validated. If it is unset, the failure appears as an obscure error from the email encoding layer rather than a clear message — caught by `chat()`'s fallback handling in the live app, but still an opaque cause in the logs and in the daily digest job.
- `services/profile.py`'s `get_current_preferences()` reads its file with a path relative to the process's working directory, unlike the other resource-reading functions in the same module, which resolve an absolute path from `__file__`. Running the app from a directory other than the repo root will break this one specifically.
- Tools always report `{"recorded": "ok"}` to the model even when the underlying send/store failed; `handle_tool_calls()` catches the exception one layer up but reports it as plain text, not the SDK's `is_error` field — so the model can still tell a visitor "I've noted that down" after a failed send. Tracked by two `xfail(strict=True)` tests (see [Testing](#testing)).
- Two `tests/unit/test_profile.py` tests currently fail (not `xfail`-marked) because the system prompt no longer includes LinkedIn PDF text but the tests still expect it — real, unresolved test/code drift.
- The persona name and background-file filenames are hardcoded in `services/profile.py`.
- Evaluation runs (as of the last recorded run, before the current prompt was written) showed the model does not always call `record_unknown_question` for out-of-scope questions, so some unanswered questions never reach the digest. The system prompt has since been rewritten with more explicit in-scope/out-of-scope rules; this has not yet been re-verified with a fresh eval run.
- No `LICENSE` file.

`SPEC.md` section 11 tracks these in full, with file/line references and, where one exists, the test that pins each one.

## Further documentation

| File | Contents |
|---|---|
| `SPEC.md` | Full technical specification and the known-issues list |
| `tests/evals/README.md` | Evaluation suite design and observed results |
| `BUGS.md` | Bug and fix log |
| `DEVLOG.md` | Development log |

## License

No license is currently specified for this project.
