"""Executable contracts for source-SDK-preserving Runtime rewrite lanes."""
import sys
import types

import preflight_bedrock as lanes


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(output_text="responses output")


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = types.SimpleNamespace(content="chat output")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text="messages output")])


def test_runtime_openai_responses_lane_preserves_shape_and_refreshing_token(monkeypatch):
    created = []
    responses = FakeResponses()

    class OpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.responses = responses

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))
    tokens = iter(["token-1", "token-2"])
    client = lanes.runtime_openai_client("us-west-2", token_provider=lambda: next(tokens))
    response = client.responses.create(
        model="global.openai.gpt-5.4", input="ping", max_output_tokens=16, store=False)

    assert created[0]["base_url"] == "https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1"
    assert created[0]["api_key"]() == "token-1"
    assert created[0]["api_key"]() == "token-2"
    assert responses.calls[0]["input"] == "ping"
    assert response.output_text == "responses output"


def test_runtime_openai_chat_lane_preserves_shape_and_refreshing_token(monkeypatch):
    created = []
    completions = FakeCompletions()

    class OpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.chat = types.SimpleNamespace(completions=completions)

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))
    client = lanes.runtime_openai_client("us-east-1", token_provider=lambda: "fresh-token")
    response = client.chat.completions.create(
        model="us.openai.gpt-5.5",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=16,
    )

    assert created[0]["base_url"] == "https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1"
    assert created[0]["api_key"]() == "fresh-token"
    assert completions.calls[0]["messages"][0]["content"] == "ping"
    assert response.choices[0].message.content == "chat output"


def test_runtime_messages_lane_preserves_shape_and_refreshing_token(monkeypatch):
    created = []
    messages = FakeMessages()

    class Anthropic:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.messages = messages

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=Anthropic))
    client = lanes.runtime_messages_client("eu-west-1", token_provider=lambda: "fresh-token")
    response = client.messages.create(
        model="global.anthropic.claude-sonnet-5",
        max_tokens=16,
        messages=[{"role": "user", "content": "ping"}],
    )

    assert created[0]["base_url"] == "https://bedrock-runtime.eu-west-1.amazonaws.com/anthropic"
    assert created[0]["auth_token"]() == "fresh-token"
    assert messages.calls[0]["messages"][0]["content"] == "ping"
    assert response.content[0].text == "messages output"


def test_messages_clients_send_exact_anthropic_v1_messages_path():
    import httpx

    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "pong"}],
                "model": "anthropic.claude-sonnet-5",
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            request=request,
        )

    token = "test-token"
    for factory in (lanes.runtime_messages_client, lanes.mantle_messages_client):
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as http_client:
            client = factory("us-east-1", token_provider=token, http_client=http_client)
            response = client.messages.create(
                model="anthropic.claude-sonnet-5",
                max_tokens=16,
                messages=[{"role": "user", "content": "ping"}],
            )
            assert response.content[0].text == "pong"

    assert seen == ["/anthropic/v1/messages", "/anthropic/v1/messages"]
