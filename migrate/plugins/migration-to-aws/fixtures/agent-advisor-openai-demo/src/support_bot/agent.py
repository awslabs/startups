"""Existing OpenAI support bot (static fixture; never invokes OpenAI in tests).

Deliberately exercises the migration-sensitive surfaces the OpenAI-to-Bedrock
advisor must detect: Chat Completions with tools + structured output + n,
a tool-result continuation turn, and a Responses API reasoning call with a
hosted web_search tool.
"""

from openai import OpenAI

CLASSIFY_MODEL = "gpt-4o"
REASONING_MODEL = "gpt-5.4"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up an order by id",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    }
]

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "ticket_class",
        "schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "urgency": {"type": "string"},
            },
            "required": ["category", "urgency"],
        },
    },
}


def _client():
    return OpenAI()


def classify_ticket(text):
    """Chat Completions + structured output + tools + n + small budget."""
    return _client().chat.completions.create(
        model=CLASSIFY_MODEL,
        messages=[
            {"role": "system", "content": "You triage support tickets."},
            {"role": "user", "content": text},
        ],
        tools=TOOLS,
        tool_choice="auto",
        response_format=RESPONSE_FORMAT,
        temperature=0.2,
        top_p=0.9,
        max_tokens=256,
        n=2,
    )


def continue_with_tool_result(tool_call_id, result_json):
    """Chat Completions tool-result turn (function role)."""
    return _client().chat.completions.create(
        model=CLASSIFY_MODEL,
        messages=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": tool_call_id}],
            },
            {"role": "tool", "tool_call_id": tool_call_id, "content": result_json},
        ],
    )


def deep_reason(question):
    """Responses API call on a reasoning model with a hosted web_search tool."""
    return _client().responses.create(
        model=REASONING_MODEL,
        input=question,
        reasoning={"effort": "high"},
        tools=[{"type": "web_search"}],
        max_output_tokens=512,
    )
