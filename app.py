"""Application entry point for the Career Persona chatbot.

Wires together the Gradio chat UI, the Anthropic Messages API, Langfuse
tracing, inbound rate limiting, and the two model-callable tools
(``record_user_details``, ``record_unknown_question``). The module-level
``chat()`` function is the callable passed to :class:`gradio.ChatInterface`;
``_chat()`` implements the bounded tool-use loop that ``chat()`` wraps with
rate limiting and API-error handling.
"""

import json
import logging

import anthropic
import gradio as gr
import psycopg
from anthropic.types import TextBlockParam
from dotenv import load_dotenv
from langfuse import get_client, observe
from openinference.instrumentation.anthropic import AnthropicInstrumentor

from services import rate_limit, resource_store
from services.db import init_db
from services.digest import start_scheduler
from services.profile import get_system_prompt_for_profile, FALLBACK_BUSY, FALLBACK_GENERIC, FALLBACK_TOO_LONG, \
    FALLBACK_RATE_LIMITED
from services.tools import record_user_details, record_unknown_question, tools

load_dotenv(override=True)

# 1. Initialize the Langfuse client — this registers Langfuse as the global
# OTEL TracerProvider/exporter. Must happen before instrument() emits spans,
# otherwise they're created against a no-op provider and never get sent.
langfuse = get_client()

# 2. Activate automatic tracing — patches the Anthropic client so every
# messages.create() call emits an OTEL span that Langfuse picks up.
AnthropicInstrumentor().instrument()

# Native Anthropic client — resolves ANTHROPIC_API_KEY from the environment.
client = anthropic.Anthropic(max_retries=4, timeout=30.0)

# Upper bound on tool-use round-trips within a single chat turn, in case the
# model keeps emitting tool calls instead of a final answer.
MAX_TOOL_ITERATIONS = 5

logger = logging.getLogger(__name__)


def handle_tool_calls(tool_use_blocks):
    """Execute a batch of model-requested tool calls and format the results.

    Dispatches each ``tool_use`` content block to the matching function in
    :mod:`services.tools` by name. A tool that raises, or a name that does
    not match a known tool, is converted into an ``{"error": ...}`` payload
    rather than propagating, so one bad tool call cannot abort the turn.

    :param tool_use_blocks: The ``tool_use`` content blocks from an
        Anthropic ``Message`` response (``response.content`` filtered to
        ``type == "tool_use"``).
    :type tool_use_blocks: list[anthropic.types.ToolUseBlock]
    :return: One ``tool_result`` content block per input block, in the same
        order, each with the JSON-encoded tool return value (or error) as
        its ``content``.
    :rtype: list[dict]
    """
    results = []
    for tool_use in tool_use_blocks:
        tool_name = tool_use.name
        arguments = tool_use.input
        print(f"Tool called: {tool_name}", flush=True)

        try:
            if tool_name == "record_user_details":
                result = record_user_details(**arguments)
            elif tool_name == "record_unknown_question":
                result = record_unknown_question(**arguments)
            else:
                result = {"error": f"Tool not found: {tool_name}"}
        except Exception as e:
            result = {"error": str(e)}

        results.append({
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": json.dumps(result),
        })
    return results


@observe(name="chat_turn")
def chat(message, history, request: gr.Request | None = None):
    """Top-level Gradio ``ChatInterface`` callback for one chat turn.

    Applies inbound rate limiting before any API call, then delegates to
    :func:`_chat` for the actual model interaction. Anthropic API errors and
    any other unhandled exception are caught here and converted to one of
    the ``FALLBACK_*`` strings from :mod:`services.profile`, so a visitor
    never sees a raw traceback or an empty reply.

    :param message: The visitor's new message for this turn.
    :type message: str
    :param history: Prior turns as passed by Gradio's ``ChatInterface``
        (a list of role/content dicts, possibly with extra Gradio-specific
        keys).
    :type history: list[dict]
    :param request: The inbound Gradio request, used to derive a caller
        identity for rate limiting. ``None`` when not available (e.g. in
        tests or non-HTTP invocations).
    :type request: gradio.Request or None
    :return: The assistant's reply text, or a fallback message if the turn
        was rate-limited or failed.
    :rtype: str
    """
    caller = rate_limit.caller_key(request)
    try:
        rate_limit.check_chat_turn(caller, message)
    except rate_limit.MessageTooLong:
        return FALLBACK_TOO_LONG
    except rate_limit.RateLimited as exc:
        logger.info("Turn refused for %s: %s", caller, exc.reason)
        return FALLBACK_RATE_LIMITED

    token = rate_limit.set_current_caller(caller)

    try:
        return _chat(message, history)
    except (anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.APIConnectionError) as exc:
        logger.warning("Transient Anthropic error", exc_info=exc)
        return FALLBACK_BUSY
    except anthropic.APIError as exc:
        # 400/401/403 — misconfiguration, not the visitor's problem
        logger.error("Anthropic API error", exc_info=exc)
        return FALLBACK_GENERIC
    except Exception as exc:
        # Tool failures, PDF read failures, anything else (§11 item 5)
        logger.exception("Unhandled error in chat turn")
        return FALLBACK_GENERIC
    finally:
        rate_limit.reset_current_caller(token)


@observe(name="chat_turn")
def _chat(message, history):
    """Run the bounded tool-use loop against the Anthropic Messages API.

    Rebuilds the system prompt (with prompt caching enabled) on each
    iteration, sends the conversation to ``claude-haiku-4-5``, and, while
    the model keeps requesting tool calls, dispatches them via
    :func:`handle_tool_calls` and loops again — up to
    :data:`MAX_TOOL_ITERATIONS` round trips. If the model exhausts that cap
    without producing a final answer, the loop stops and the last response
    is used as-is. A turn that ends with only a tool call and no visible
    text is given a short canned acknowledgement instead of an empty reply.

    :param message: The visitor's new message for this turn.
    :type message: str
    :param history: Prior turns as role/content dicts; Gradio-specific keys
        are stripped before sending to the API.
    :type history: list[dict]
    :return: The assistant's final reply text for this turn.
    :rtype: str
    """
    # System prompt is a top-level parameter, not a message. History and the new
    # user turn are the only entries in the messages array.
    # Gradio's ChatInterface passes history dicts with extra keys (e.g. "metadata",
    # "options") that the Anthropic API rejects — keep only role and content.
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})

    for iteration in range(MAX_TOOL_ITERATIONS):
        # This is the call to the LLM - see that we pass in the tools json
        system: list[TextBlockParam] = [
            {
                "type": "text",
                "text": get_system_prompt_for_profile(),
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=tools,
        )
        rate_limit.record_usage(response.usage)

        # If the LLM wants to call a tool, we do that and loop again!
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            results = handle_tool_calls(tool_use_blocks)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})
        else:
            break
    else:
        print(f"Hit MAX_TOOL_ITERATIONS ({MAX_TOOL_ITERATIONS}) without a final answer; "
              f"stopping tool-use loop.", flush=True)

    # Return the final text; concatenate any text blocks in the response.
    reply = "".join(block.text for block in response.content if block.type == "text")

    # If the turn ended with only a tool call and no visible text, the user would
    # otherwise see a blank reply — give them a short acknowledgement instead.
    if not reply.strip():
        reply = "Thanks — I've noted that down. Is there anything else I can help you with?"

    return reply


if __name__ == "__main__":
    try:
        init_db()
    except (RuntimeError, psycopg.Error):
        # Postgres unreachable/misconfigured at startup. Degrade instead of
        # crashing: chat still works; record_unknown_question and the daily
        # digest will error out individually until the DB comes back.
        logger.exception("Database initialization failed; unanswered-question "
                          "storage and the daily digest will be unavailable "
                          "until DATABASE_URL is reachable.")
    resource_store.warm_cache([
        "SUMMARY.md",
        "CAREER_PROFILE.md",
        "CURRENT_STATUS_AND_PREFERENCES.md",
    ])
    start_scheduler()
    gr.ChatInterface(fn=chat).launch(show_error=False)
