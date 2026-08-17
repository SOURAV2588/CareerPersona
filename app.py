from anthropic.types import TextBlockParam
from dotenv import load_dotenv
import anthropic
import json

import gradio as gr
from langfuse import get_client, observe
from openinference.instrumentation.anthropic import AnthropicInstrumentor

from services.profile import get_system_prompt_for_profile
from services.tools import record_user_details, record_unknown_question, tools
from services.digest import start_scheduler

load_dotenv(override=True)

# 1. Initialize the Langfuse client — this registers Langfuse as the global
# OTEL TracerProvider/exporter. Must happen before instrument() emits spans,
# otherwise they're created against a no-op provider and never get sent.
langfuse = get_client()

# 2. Activate automatic tracing — patches the Anthropic client so every
# messages.create() call emits an OTEL span that Langfuse picks up.
AnthropicInstrumentor().instrument()

# Native Anthropic client — resolves ANTHROPIC_API_KEY from the environment.
client = anthropic.Anthropic()

# Upper bound on tool-use round-trips within a single chat turn, in case the
# model keeps emitting tool calls instead of a final answer.
MAX_TOOL_ITERATIONS = 5

def handle_tool_calls(tool_use_blocks):
    results = []
    for tool_use in tool_use_blocks:
        tool_name = tool_use.name
        arguments = tool_use.input
        print(f"Tool called: {tool_name}", flush=True)

        if tool_name == "record_user_details":
            result = record_user_details(**arguments)
        elif tool_name == "record_unknown_question":
            result = record_unknown_question(**arguments)
        else:
            result = {"error": f"Tool not found: {tool_name}"}

        results.append({
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": json.dumps(result),
        })
    return results


@observe(name="chat_turn")
def chat(message, history):
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
        print(response.usage)

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
    # start_scheduler()
    gr.ChatInterface(fn=chat).launch()
