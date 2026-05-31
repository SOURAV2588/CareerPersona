from dotenv import load_dotenv
from openai import OpenAI
import json

import gradio as gr

from services.profile import get_system_prompt_for_profile
from services.tools import record_user_details, record_unknown_question, tools

load_dotenv(override=True)
openai = OpenAI()


def handle_tool_calls(tool_calls):
    results = []
    result = None
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        print(f"Tool called: {tool_name}", flush=True)

        # THE BIG IF STATEMENT!!!
        if tool_name == "record_user_details":
            result = record_user_details(**arguments)
        elif tool_name == "record_unknown_question":
            result = record_unknown_question(**arguments)

        results.append({"role": "tool", "content": json.dumps(result), "tool_call_id": tool_call.id})
    return results


def chat(message, history):
    messages = [{"role": "system", "content": get_system_prompt_for_profile()}] + history + [{"role": "user", "content": message}]
    done = False
    while not done:

        # This is the call to the LLM - see that we pass in the tools json
        response = openai.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
        finish_reason = response.choices[0].finish_reason

        # If the LLM wants to call a tool, we do that!
        if finish_reason == "tool_calls":
            message = response.choices[0].message
            tool_calls = message.tool_calls
            results = handle_tool_calls(tool_calls)
            messages.append(message)
            messages.extend(results)
        else:
            done = True
    return response.choices[0].message.content


gr.ChatInterface(fn=chat).launch()
