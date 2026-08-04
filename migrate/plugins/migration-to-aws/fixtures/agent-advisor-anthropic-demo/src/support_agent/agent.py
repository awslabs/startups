"""Legacy Anthropic Messages agent used as a migration assessment fixture."""

import json
import os

from anthropic import Anthropic

from support_agent.tools import execute_tool


MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = [
    {
        "type": "text",
        "text": (
            "You are a customer support agent. Use tools before making claims "
            "about orders, and return concise answers."
        ),
        "cache_control": {"type": "ephemeral"},
    }
]

TOOLS = [
    {
        "name": "lookup_order",
        "description": "Look up an order by order ID.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_help_center",
        "description": "Search internal support articles.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 2,
    },
]


def _blocks(response):
    return [
        block.model_dump() if hasattr(block, "model_dump") else block
        for block in response.content
    ]


def run_support_agent(question, force_json=False):
    """Run the legacy first-party Anthropic agent loop."""
    client = Anthropic()
    messages = [{"role": "user", "content": question}]
    if force_json:
        # Legacy assistant prefill is intentionally present for migration scanning.
        messages.append({"role": "assistant", "content": "{"})

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
            max_tokens=4096,
            thinking={"type": "enabled", "budget_tokens": 1024},
            temperature=0.2,
            top_p=0.9,
        )
        tool_uses = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_uses:
            text = [
                block.text for block in response.content if block.type == "text"
            ]
            return "\n".join(text)

        messages.append({"role": "assistant", "content": _blocks(response)})
        tool_results = []
        for tool_use in tool_uses:
            result = execute_tool(tool_use.name, tool_use.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("tool loop exceeded its configured round limit")
