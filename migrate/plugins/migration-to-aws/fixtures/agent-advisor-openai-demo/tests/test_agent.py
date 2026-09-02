"""Local tests for the OpenAI fixture. These never call OpenAI."""

import inspect

from support_bot import agent, extras


def test_uses_both_chat_and_responses_surfaces():
    chat_src = inspect.getsource(agent.classify_ticket)
    assert "chat.completions.create" in chat_src
    resp_src = inspect.getsource(agent.deep_reason)
    assert "responses.create" in resp_src


def test_declares_legacy_and_reasoning_models():
    src = inspect.getsource(agent)
    assert "gpt-4o" in src
    assert "gpt-5.4" in src


def test_exercises_migration_sensitive_surfaces():
    src = inspect.getsource(agent)
    for needle in ("response_format", "tool_choice", "n=2", "reasoning", "web_search"):
        assert needle in src


def test_extras_are_separate_modalities():
    src = inspect.getsource(extras)
    assert "audio.transcriptions" in src
    assert "embeddings.create" in src
    assert "file_search" in src
