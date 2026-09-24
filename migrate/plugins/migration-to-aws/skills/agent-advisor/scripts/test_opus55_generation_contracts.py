"""Execute the shipped generation/evaluation examples against typed responses."""

import ast
import copy
import importlib.util
import io
import json
import re
import sys
import types
from pathlib import Path

import pytest


PLUGIN = Path(__file__).resolve().parents[3]
SKILLS = PLUGIN / "skills"
REWRITER = PLUGIN / "agents/llm2bedrock-code-rewriter.md"
EVALUATOR = PLUGIN / "agents/llm2bedrock-prompt-evaluator.md"
BDD = SKILLS / "llm-to-bedrock/references/helpers/behavior-delta-detection/references"
REASONING = {"reasoningContent": {"reasoningText": {"text": "Private reasoning", "signature": "opaque-signature"}}}
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def response(blocks, stop="end_turn"):
    return {"output": {"message": {"role": "assistant", "content": blocks}}, "stopReason": stop}


def block(path, marker):
    text = path.read_text()
    sources = re.findall(r"```python\n(.*?)\n```", text, re.S)
    sources += re.findall(r"python - <<'PY'\n(.*?)\nPY", text, re.S)
    matches = [code for code in sources if marker in code]
    assert len(matches) == 1, (path, marker, len(matches))
    return matches[0]


def after_call(code, method):
    nodes = ast.parse(code).body
    start = next(i for i, node in enumerate(nodes) if
                 isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and
                 isinstance(node.value.func, ast.Attribute) and node.value.func.attr == method)
    return compile(ast.fix_missing_locations(ast.Module(body=nodes[start:], type_ignores=[])), "<template>", "exec")


class Bedrock:
    def __init__(self, replies=(), events=()):
        self.replies = list(replies)
        self.events = events
        self.requests = []

    def converse(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return self.replies.pop(0)

    def converse_stream(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return {"stream": iter(self.events)}


def poc_runner(reply):
    code = block(SKILLS / "agent-advisor/references/phases/poc/poc.md", "def run_prompt(")
    function = next(node for node in ast.parse(code).body if isinstance(node, ast.FunctionDef) and node.name == "run_prompt")
    namespace = {"_bedrock": Bedrock([reply]), "MODEL_ID": "global.anthropic.claude-opus-5-5", "SYSTEM_PROMPT": "Test"}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "<poc>", "exec"), namespace)
    return namespace["run_prompt"]


@pytest.mark.parametrize("leading", [[], [REASONING]])
def test_poc_and_nonstreaming_rewrite_read_all_visible_text(leading):
    reply = response(copy.deepcopy(leading) + [{"text": "Hello "}, {"text": "world"}])
    original = copy.deepcopy(reply)
    assert poc_runner(reply)("prompt") == "Hello world"
    code = block(REWRITER, 'output = response.choices[0].message.content')
    namespace = {"bedrock": Bedrock([reply])}
    exec(after_call(code, "converse"), namespace)
    assert namespace["output"] == "Hello world"
    assert namespace["assistant_message"] is reply["output"]["message"]
    assert reply == original


@pytest.mark.parametrize("blocks,stop", [
    ([REASONING], "end_turn"),
    ([REASONING, {"text": "Partial"}], "max_tokens"),
    ([{"text": "Refused"}], "refusal"),
    ([{"text": "Filtered"}], "content_filtered"),
])
def test_text_only_templates_report_incomplete_or_missing_answers(blocks, stop):
    reply = response(copy.deepcopy(blocks), stop)
    with pytest.raises(ValueError, match="No complete text response"):
        poc_runner(reply)("prompt")
    code = block(REWRITER, 'output = response.choices[0].message.content')
    with pytest.raises(ValueError, match="No complete text response"):
        exec(after_call(code, "converse"), {"bedrock": Bedrock([reply])})


def test_streaming_preserves_reasoning_events_but_emits_only_text():
    events = [
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"reasoningContent": {"text": "Private"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"reasoningContent": {"signature": "opaque"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"text": "Hello "}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"text": "world"}}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]
    original = copy.deepcopy(events)
    namespace = {"bedrock": Bedrock(events=events), "messages_bedrock_format": []}
    exec(after_call(block(REWRITER, "bedrock.converse_stream("), "converse_stream"), namespace)
    assert namespace["output"] == "Hello world"
    assert namespace["stream_events"] == original
    assert events == original


@pytest.mark.parametrize("events", [
    [{"messageStop": {"stopReason": "end_turn"}}],
    [{"contentBlockDelta": {"delta": {"text": "Partial"}}}],
    [{"contentBlockDelta": {"delta": {"text": "Partial"}}}, {"messageStop": {"stopReason": "max_tokens"}}],
])
def test_streaming_rejects_empty_truncated_or_unterminated_output(events):
    namespace = {"bedrock": Bedrock(events=events), "messages_bedrock_format": []}
    with pytest.raises(ValueError, match="No complete text stream"):
        exec(after_call(block(REWRITER, "bedrock.converse_stream("), "converse_stream"), namespace)


@pytest.mark.parametrize("marker,label", [("print(\"OK:\"", "OK:"), ("print(\"VISION_OK:\"", "VISION_OK:")])
@pytest.mark.parametrize("blocks,stop", [([REASONING, {"text": "Answer"}], "end_turn"), ([REASONING], "max_tokens")])
def test_access_and_vision_smoke_probes_distinguish_invocation_from_answer_quality(marker, label, blocks, stop, capsys):
    bodies = re.findall(r"python - <<'PY'\n(.*?)\nPY", EVALUATOR.read_text(), re.S)
    code = next(body for body in bodies if marker in body)
    node = next(node for node in ast.parse(code).body if isinstance(node, ast.Try) and
                any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "converse"
                    for n in ast.walk(node)))
    namespace = {"c": Bedrock([response(copy.deepcopy(blocks), stop)]), "img": b"image", "sys": sys}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "<probe>", "exec"), namespace)
    output = capsys.readouterr().out
    assert label in output and f"stopReason={stop}" in output
    assert "Private reasoning" not in output
    assert ("Answer" in output) if stop == "end_turn" else ("no text" in output)


@pytest.mark.parametrize("blocks,stop,expected", [
    ([REASONING, {"text": "Answer"}], "end_turn", "success"),
    ([{"text": "Answer"}], "end_turn", "success"),
    ([REASONING], "end_turn", "error: no_text_response"),
    ([{"text": "Partial"}], "max_tokens", "error: non_final_response"),
    ([{"text": "Refused"}], "refusal", "error: non_final_response"),
])
def test_complete_evaluator_script_handles_typed_output(tmp_path, monkeypatch, blocks, stop, expected):
    code = block(EVALUATOR, 'gd_path = "<repo>/.saws-migrate/golden-dataset/prompts.jsonl"')
    fake_boto = types.ModuleType("boto3")
    fake_boto.client = lambda *args, **kwargs: Bedrock([response(copy.deepcopy(blocks), stop)])
    fake_core = types.ModuleType("botocore")
    fake_exceptions = types.ModuleType("botocore.exceptions")
    fake_exceptions.ClientError = type("ClientError", (Exception,), {})
    fake_core.exceptions = fake_exceptions
    monkeypatch.setitem(sys.modules, "boto3", fake_boto)
    monkeypatch.setitem(sys.modules, "botocore", fake_core)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_exceptions)
    data = tmp_path / ".saws-migrate/golden-dataset"
    data.mkdir(parents=True)
    (tmp_path / ".saws-migrate/eval-results").mkdir()
    (data / "prompts.jsonl").write_text(json.dumps({"id": "case", "user_prompt": "Prompt", "assistant_response": "Answer"}) + "\n")
    exec(compile(code.replace("<repo>", str(tmp_path)), "<evaluator>", "exec"), {})
    result = json.loads((tmp_path / ".saws-migrate/eval-results/raw_results.jsonl").read_text())
    assert result["status"].startswith(expected)
    assert "Private reasoning" not in result["bedrock_response"]
    if expected == "success":
        assert result["bedrock_response"] == "Answer"


def structured_namespace(replies):
    return {
        "bedrock": Bedrock(replies),
        "source_schema": SCHEMA,
        "target_model_id": "global.anthropic.claude-opus-5-5",
        "messages_bedrock": [{"role": "user", "content": [{"text": "Return an answer"}]}],
        "inference_config": {"maxTokens": 4096},
    }


def structured_code():
    return block(BDD / "openai-to-bedrock.md", "for attempt in range(3):")


def test_auto_tool_validation_retries_with_signed_history_and_tool_results():
    first = response([copy.deepcopy(REASONING), {"toolUse": {"toolUseId": "one", "name": "Result", "input": {"answer": 42}}}], "tool_use")
    second = response([copy.deepcopy(REASONING), {"toolUse": {"toolUseId": "two", "name": "Result", "input": {"answer": "valid"}}}], "tool_use")
    original = copy.deepcopy(first)
    namespace = structured_namespace([first, second])
    exec(structured_code(), namespace)
    assert namespace["result"] == {"answer": "valid"}
    requests = namespace["bedrock"].requests
    assert len(requests) == 2
    assert all(request["toolConfig"]["toolChoice"] == {"auto": {}} for request in requests)
    assert all("thinking" not in request.get("additionalModelRequestFields", {}) for request in requests)
    assert requests[1]["messages"][1] == original["output"]["message"]
    assert requests[1]["messages"][2]["content"][0]["toolResult"]["toolUseId"] == "one"
    assert namespace["conversation"][-1]["content"][0]["toolResult"]["toolUseId"] == "two"
    assert first == original


def test_auto_tool_validation_accepts_schema_valid_text_and_bounds_failures():
    namespace = structured_namespace([response([copy.deepcopy(REASONING), {"text": '{"answer":"valid"}'}])])
    exec(structured_code(), namespace)
    assert namespace["result"] == {"answer": "valid"}
    namespace = structured_namespace([response([{"text": "not JSON"}])] * 3)
    with pytest.raises(ValueError, match="three attempts"):
        exec(structured_code(), namespace)
    assert len(namespace["bedrock"].requests) == 3


@pytest.mark.parametrize("stop", ["max_tokens", "refusal"])
def test_auto_tool_validation_does_not_retry_refusal_or_truncation(stop):
    namespace = structured_namespace([response([{"text": "Partial"}], stop)])
    with pytest.raises(ValueError, match=stop):
        exec(structured_code(), namespace)
    assert len(namespace["bedrock"].requests) == 1


def test_native_vision_template_and_source_baseline_skip_thinking_blocks():
    path = SKILLS / "llm-to-bedrock/references/helpers/bedrock-known-fixes/references/bedrock-vision.py.template"
    nodes = [node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name in {"analyze_image", "_parse_response"}]
    payload = {"content": [{"type": "thinking", "thinking": "Private", "signature": "opaque"}, {"type": "text", "text": '{"answer":"valid"}'}], "stop_reason": "end_turn"}
    client = types.SimpleNamespace(invoke_model=lambda **kwargs: {"body": io.BytesIO(json.dumps(payload).encode())})
    namespace = {"get_client": lambda: client, "_normalize_image": lambda data: "image", "PROMPT": "Prompt", "settings": types.SimpleNamespace(bedrock_model_id="us.anthropic.claude-opus-5-5"), "json": json}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), "<vision>", "exec"), namespace)
    assert namespace["analyze_image"](b"image") == {"answer": "valid"}
    path = SKILLS / "llm-to-bedrock/scripts/source_baseline.py"
    spec = importlib.util.spec_from_file_location("typed_source_baseline", path)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    assert baseline.extract_anthropic_text(payload) == '{"answer":"valid"}'
    payload["stop_reason"] = "max_tokens"
    with pytest.raises(ValueError, match="max_tokens"):
        baseline.extract_anthropic_text(payload)
    with pytest.raises(ValueError, match="max_tokens"):
        namespace["analyze_image"](b"image")
    payload["stop_reason"] = "end_turn"
    payload["content"] = [{"type": "thinking", "thinking": "Private", "signature": "opaque"}]
    with pytest.raises(ValueError, match="No complete"):
        namespace["analyze_image"](b"image")
    with pytest.raises(ValueError, match="No complete"):
        baseline.extract_anthropic_text(payload)


def test_shared_guide_and_gemini_adapter_read_typed_text():
    reply = response([copy.deepcopy(REASONING), {"text": "Answer"}])
    guide = SKILLS / "shared/ai/ai-anthropic-to-bedrock.md"
    namespace = {"response": reply}
    exec(block(guide, 'text = "".join'), namespace)
    assert namespace["text"] == "Answer"
    code = block(BDD / "gemini-to-bedrock.md", 'choice = "".join')
    namespace = {"bedrock": Bedrock([reply]), "messages_bedrock": []}
    exec(after_call(code, "converse"), namespace)
    assert namespace["choice"] == "Answer"
