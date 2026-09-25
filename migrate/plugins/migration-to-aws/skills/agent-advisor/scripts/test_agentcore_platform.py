"""Exercise the deploy helper with service responses, without AWS calls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
# Runs the authored template against test-owned fake CLIs.
import subprocess  # nosec B404
import sys
from unittest.mock import Mock

import pytest

import set_agentcore_platform as platform
import score_units


@pytest.fixture
def runtime():
    return {
        "agentRuntimeId": "poc-1234567890",
        "agentRuntimeVersion": "1",
        "status": "READY",
        "platformVersion": "V1",
        "agentRuntimeArtifact": {"containerConfiguration": {"containerUri": "example/image"}},
        "roleArn": "arn:aws:iam::123456789012:role/Poc",
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "description": "POC",
        "authorizerConfiguration": {"customJWTAuthorizer": {"allowedClients": ["client"]}},
        "requestHeaderConfiguration": {"requestHeaderAllowlist": ["X-Amzn-Bedrock-AgentCore-Runtime-Custom-User"]},
        "protocolConfiguration": {"serverProtocol": "HTTP"},
        "lifecycleConfiguration": {"maxLifetime": 28800},
        "environmentVariables": {"PRIVATE_VALUE": "must-not-be-printed"},
        "filesystemConfigurations": [],
        "metadataConfiguration": {"requireMMDSV2": True},
        "workloadIdentityDetails": {"workloadIdentityArn": "do-not-forward"},
        "ResponseMetadata": {"HTTPStatusCode": 200},
    }


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(platform.time, "sleep", lambda _: None)


def test_upgrade_preserves_configuration_and_waits_for_new_revision(runtime):
    upgraded = {**runtime, "platformVersion": "V2", "agentRuntimeVersion": "2"}
    client = Mock()
    client.get_agent_runtime.side_effect = [
        {**runtime, "status": "CREATING"}, runtime,
        runtime, {**upgraded, "status": "UPDATING"}, upgraded,
    ]
    client.update_agent_runtime.return_value = {"agentRuntimeVersion": "2", "status": "UPDATING"}
    before = deepcopy(runtime)
    result = platform.set_platform(client, runtime["agentRuntimeId"], "V2")
    request = client.update_agent_runtime.call_args.kwargs
    for key in platform.UPDATE_FIELDS:
        assert request[key] == before[key]
    assert set(request) == set(platform.UPDATE_FIELDS) | {"agentRuntimeId", "platformVersion"}
    assert request["platformVersion"] == "V2"
    assert result == {
        "agentRuntimeId": runtime["agentRuntimeId"], "agentRuntimeVersion": "2",
        "platformVersion": "V2", "status": "READY",
    }
    assert "must-not-be-printed" not in str(result)
    assert runtime == before


@pytest.mark.parametrize("version", ["V1", "V2"])
def test_matching_platform_only_reads(runtime, version):
    runtime["platformVersion"] = version
    client = Mock()
    client.get_agent_runtime.return_value = runtime
    assert platform.set_platform(client, runtime["agentRuntimeId"], version)["platformVersion"] == version
    client.update_agent_runtime.assert_not_called()


@pytest.mark.parametrize("status", ["CREATE_FAILED", "UPDATE_FAILED", "DELETING"])
def test_failure_never_updates_or_falls_back(runtime, status):
    client = Mock()
    client.get_agent_runtime.return_value = {**runtime, "status": status}
    with pytest.raises(RuntimeError, match=status):
        platform.set_platform(client, runtime["agentRuntimeId"], "V2")
    client.update_agent_runtime.assert_not_called()


def test_failed_upgrade_never_retries_v1(runtime):
    client = Mock()
    client.get_agent_runtime.side_effect = [runtime, {**runtime, "status": "UPDATE_FAILED"}]
    client.update_agent_runtime.return_value = {"agentRuntimeVersion": "2"}
    with pytest.raises(RuntimeError, match="UPDATE_FAILED"):
        platform.set_platform(client, runtime["agentRuntimeId"], "V2")
    assert client.update_agent_runtime.call_count == 1
    assert client.update_agent_runtime.call_args.kwargs["platformVersion"] == "V2"


def test_ready_with_wrong_platform_is_not_success(runtime):
    client = Mock()
    client.get_agent_runtime.side_effect = [runtime, {**runtime, "agentRuntimeVersion": "2"}]
    client.update_agent_runtime.return_value = {"agentRuntimeVersion": "2"}
    with pytest.raises(RuntimeError, match="does not match"):
        platform.set_platform(client, runtime["agentRuntimeId"], "V2")


@pytest.mark.parametrize("extra", [
    {"capacityProviderConfiguration": {"capacityProviderArn": "instances"}},
    {"platformVersion": None},
])
def test_instances_and_unknown_platform_cannot_be_updated(runtime, extra):
    client = Mock()
    client.get_agent_runtime.return_value = {**runtime, **extra}
    with pytest.raises((ValueError, RuntimeError)):
        platform.set_platform(client, runtime["agentRuntimeId"], "V2")
    client.update_agent_runtime.assert_not_called()


def test_timeout_is_bounded_without_mutation(runtime, monkeypatch):
    client = Mock()
    client.get_agent_runtime.return_value = {**runtime, "status": "UPDATING"}
    ticks = iter([0, 0, 901])
    monkeypatch.setattr(platform.time, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        platform.set_platform(client, runtime["agentRuntimeId"], "V2")
    client.update_agent_runtime.assert_not_called()


def test_platform_update_gets_its_own_wait_budget(runtime, monkeypatch):
    elapsed = [0]
    monkeypatch.setattr(platform.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(platform.time, "sleep", lambda _: elapsed.__setitem__(0, elapsed[0] + 400))
    upgraded = {**runtime, "platformVersion": "V2", "agentRuntimeVersion": "2"}
    client = Mock()
    client.get_agent_runtime.side_effect = [
        {**runtime, "status": "UPDATING"}, runtime,
        {**upgraded, "status": "UPDATING"}, {**upgraded, "status": "UPDATING"}, upgraded,
    ]
    client.update_agent_runtime.return_value = {"agentRuntimeVersion": "2"}
    assert platform.set_platform(client, runtime["agentRuntimeId"], "V2")["platformVersion"] == "V2"
    assert elapsed[0] == 1200
    assert client.update_agent_runtime.call_count == 1


def test_platform_update_wait_still_times_out(runtime, monkeypatch):
    elapsed = [0]
    monkeypatch.setattr(platform.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(platform.time, "sleep", lambda _: elapsed.__setitem__(0, elapsed[0] + 901))
    client = Mock()
    client.get_agent_runtime.side_effect = [runtime, {**runtime, "status": "UPDATING"}]
    client.update_agent_runtime.return_value = {"agentRuntimeVersion": "2"}
    with pytest.raises(TimeoutError):
        platform.set_platform(client, runtime["agentRuntimeId"], "V2")
    assert client.update_agent_runtime.call_count == 1


@pytest.mark.parametrize("scoring_status,platform_statuses,expected", [
    ("final", ["verified"], "final"),
    ("final", ["pending"], "provisional"),
    ("provisional", ["verified"], "provisional"),
    ("final", [None, "verified"], "final"),
    ("final", ["verified", "pending"], "provisional"),
    ("final", [None], "final"),
])
def test_design_writes_recommendation_status(scoring_status, platform_statuses, expected):
    design_md = Path(__file__).parent.parent / "references/phases/design/design.md"
    code = re.search(r"```python\n(.*?)\n```", design_md.read_text(), re.S).group(1)
    design = {"recommendation_status": "provisional", "units": [
        {"agentcore_platform": None if status is None else {"version": "V2", "status": status}}
        for status in platform_statuses
    ]}
    # Execute the reviewed status-assignment snippet, with only fixture artifacts as inputs.
    exec(code, {"design": design, "scoring_result": {"recommendation_status": scoring_status}})  # nosec B102
    assert design["recommendation_status"] == expected


def _run_deploy_template(tmp_path, failure, run_id, unit_id, override, expected_name, runtime_store=None):
    """Run the authored shell with fake CLIs, including its real config-reading heredoc."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    poc = Path(__file__).parent.parent / "references/phases/poc/poc.md"
    section = poc.read_text().split("### 3d.", 1)[1].split("### 3e.", 1)[0]
    shell = re.search(r"```bash\n(.*?)\n```", section, re.S).group(1)
    shell = shell.replace("<verified-target-region>", "us-west-2").replace("<run_id>", run_id).replace("<unit_id>", unit_id)
    script = tmp_path / "deploy.sh"
    script.write_text(shell)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    # JSON is a YAML subset. This fixture avoids a test dependency on PyYAML.
    (tmp_path / "yaml.py").write_text("import json\nsafe_load = json.loads\n")
    config = {"default_agent": "wrong_default", "agents": {
        "wrong_default": {"bedrock_agentcore": {"agent_id": "wrong-runtime"}},
        expected_name or "unused": {"bedrock_agentcore": {"agent_id": "right-runtime"}},
    }}
    (tmp_path / ".bedrock_agentcore.yaml").write_text(json.dumps(config))
    # Enforce the official starter toolkit's validate_agent_name contract.
    fake_cli = """import json, os, pathlib, re, subprocess, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\\n")
if tool == "aws":
    print("123456789012")
elif tool == "agentcore":
    option = "--name" if args[0] == "configure" else "--agent"
    name = args[args.index(option) + 1]
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,47}", name):
        print("Invalid agent name: only letters, numbers, and underscores are allowed.", file=sys.stderr)
        sys.exit(2)
    if args[0] == os.environ["FAILURE"]:
        sys.exit(1)
    if os.environ.get("FAKE_RUNTIME_STORE") and args[0] == "launch":
        store = pathlib.Path(os.environ["FAKE_RUNTIME_STORE"])
        runtimes = json.loads(store.read_text()) if store.exists() else {}
        if name in runtimes and "--auto-update-on-conflict" not in args:
            sys.exit(1)
        runtime = runtimes.setdefault(name, {"id": f"poc_runtime-{len(runtimes) + 1:010d}"})
        runtime["artifact"] = os.environ["FAKE_UNIT_ID"]
        store.write_text(json.dumps(runtimes))
        pathlib.Path(".bedrock_agentcore.yaml").write_text(json.dumps({
            "agents": {name: {"bedrock_agentcore": {"agent_id": runtime["id"]}}}
        }))
elif tool == "uv":
    if "--check-sdk" in args:
        sys.exit(1 if os.environ["FAILURE"] == "sdk" else 0)
    if "python" in args and "-" in args:
        code = sys.stdin.read()
        command = [sys.executable, "-c", code, *args[args.index("-") + 1:]]
        sys.exit(subprocess.run(command).returncode)
    if os.environ["FAILURE"] == "update":
        sys.exit(1)
    runtime_id = args[args.index("--runtime-id") + 1]
    if os.environ.get("FAKE_RUNTIME_STORE"):
        store = pathlib.Path(os.environ["FAKE_RUNTIME_STORE"])
        runtimes = json.loads(store.read_text())
        runtime = next(row for row in runtimes.values() if row["id"] == runtime_id)
        runtime["platform"] = args[args.index("--platform-version") + 1]
        store.write_text(json.dumps(runtimes))
    print(json.dumps({
        "agentRuntimeId": runtime_id,
        "agentRuntimeVersion": "2",
        "platformVersion": args[args.index("--platform-version") + 1],
        "status": "READY",
    }))
"""
    for tool in ("aws", "agentcore", "uv"):
        executable = binaries / tool
        executable.write_text(f"#!{sys.executable}\n{fake_cli}")
        executable.chmod(0o755)
    evidence_path = tmp_path / "runtime-verification.json"
    evidence_path.write_text(json.dumps({"platformVersion": "V1", "status": "READY"}))
    log = tmp_path / "calls.jsonl"
    env = {**os.environ, "PATH": f"{binaries}:/usr/bin:/bin",
           "PYTHONPATH": str(tmp_path), "CALL_LOG": str(log), "FAILURE": failure,
           "AWS_REGION": "eu-central-1" if failure == "region" else "us-west-2"}
    env.pop("AGENT_NAME", None)
    if override is not None:
        env["AGENT_NAME"] = override
    if runtime_store is not None:
        env["FAKE_RUNTIME_STORE"] = str(runtime_store)
        env["FAKE_UNIT_ID"] = unit_id
    # Fixed bash executable and test-owned script; no shell interpolation.
    result = subprocess.run(  # nosec B603
        ["/bin/bash", str(script)], cwd=tmp_path, env=env,
        input="no\n" if failure == "declined" else "deploy\n",
        text=True, capture_output=True, timeout=10,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    return result, calls, evidence_path


@pytest.mark.parametrize("failure,run_id,override,expected_name", [
    ("none", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
    ("none", "01a0b59b-a54c-7963-8759-48e49b10df0f", None,
     "poc_planner_85a77fa2e38a6bbf0ed9401a"),
    ("none", "0921-1530", "CustomAgent_42", "CustomAgent_42"),
    ("none", "0921-1530", "A" * 48, "A" * 48),
    ("name", "0921-1530", "invalid-name", None),
    ("name", "0921-1530", "9invalid", None),
    ("name", "0921-1530", "A" * 49, None),
    ("sdk", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
    ("configure", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
    ("launch", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
    ("update", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
    ("region", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
    ("declined", "0921-1530", None, "poc_planner_7afe65243f6f1f8032635a87"),
], ids=[
    "default-timestamp", "default-uuid", "custom-name", "max-length",
    "invalid-hyphen", "invalid-first-character", "over-length",
    "sdk", "configure", "launch", "update", "region", "declined",
])
def test_exact_deploy_template_orders_preflight_and_platform_verification(
    tmp_path, failure, run_id, override, expected_name
):
    result, calls, evidence_path = _run_deploy_template(
        tmp_path, failure, run_id, "planner", override, expected_name
    )
    writes = [call for call in calls if call[0] == "agentcore"]
    if failure in ("name", "sdk", "region", "declined"):
        assert result.returncode != 0
        assert writes == []
        assert json.loads(evidence_path.read_text()) == {"platformVersion": "V1", "status": "READY"}
        assert "Platform verified." not in result.stdout
    elif failure in ("configure", "launch"):
        assert result.returncode != 0
        assert len(writes) == (1 if failure == "configure" else 2)
        assert not evidence_path.exists()
        assert "Platform verified." not in result.stdout
    else:
        if failure == "none":
            assert result.returncode == 0, result.stderr
        preflight = next(i for i, call in enumerate(calls) if "--check-sdk" in call)
        assert preflight < next(i for i, call in enumerate(calls) if call[0] == "agentcore")
        assert writes[0][-2:] == ["--region", "us-west-2"]
        assert writes[0][writes[0].index("--name") + 1] == expected_name
        assert writes[1][1:4] == ["launch", "--agent", expected_name]
        update = calls[-1]
        assert update[update.index("--runtime-id") + 1] == "right-runtime"
        assert update[update.index("--platform-version") + 1] == "V2"
        assert update[update.index("--region") + 1] == "us-west-2"
        if failure == "update":
            assert result.returncode != 0
            assert "Platform verified." not in result.stdout
            assert not evidence_path.exists()
        else:
            assert result.returncode == 0, result.stderr
            assert f"agentcore destroy --agent {expected_name}" in result.stdout
            evidence = json.loads((tmp_path / "runtime-verification.json").read_text())
            assert evidence["platformVersion"] == "V2"
            assert evidence["agentRuntimeId"] == "right-runtime"


@pytest.mark.parametrize("run_id,unit_ids", [
    ("0922-0900", ["planner", "researcher"]),
    ("0922-0900", ["worker-a", "worker_a"]),
    ("01a0b59b-a54c-7963-8759-48e49b10df0f", ["worker" * 15 + "a", "worker" * 15 + "b"]),
])
def test_two_units_keep_distinct_runtimes_and_artifacts(tmp_path, run_id, unit_ids):
    store = tmp_path / "runtimes.json"
    ids = []
    for index, unit_id in enumerate(unit_ids):
        result, _, evidence = _run_deploy_template(
            tmp_path / f"unit_{index}", "none", run_id, unit_id, None, None, store
        )
        assert result.returncode == 0, result.stderr
        ids.append(json.loads(evidence.read_text())["agentRuntimeId"])
    runtimes = json.loads(store.read_text())
    assert len(set(ids)) == len(runtimes) == 2
    assert {row["artifact"] for row in runtimes.values()} == set(unit_ids)
    assert all(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,47}", name) for name in runtimes)
    result, _, evidence = _run_deploy_template(
        tmp_path / "rerun", "none", run_id, unit_ids[0], None, None, store
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(evidence.read_text())["agentRuntimeId"] == ids[0]
    assert len(json.loads(store.read_text())) == 2


@pytest.mark.parametrize("primary_unit,worker_duration,expected", [
    ("interactive", "over_8hr", "provisional"),
    ("worker", "over_8hr", "provisional"),
    ("interactive", "under_15min", "final"),
])
def test_design_aggregates_real_per_unit_scoring(tmp_path, capsys, primary_unit, worker_duration, expected):
    answers = {
        "entry_point": "build_scratch", "primary_unit": primary_unit, "system": {},
        "units": {
            "interactive": {"workload_class": "agent_session", "session_duration": "under_15min",
                            "ops_preference": "minimal", "session_state": "hitl", "traffic_pattern": "bursty",
                            "framework": "strands", "isolation": "required"},
            "worker": {"workload_class": "agent_session", "session_duration": worker_duration,
                       "compute_tier": "gpu" if worker_duration == "over_8hr" else "light"},
        },
    }
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers))
    assert score_units.main([str(path)]) == 0
    scored = json.loads(capsys.readouterr().out)
    design = {"units": [{"id": "interactive", "agentcore_platform": {"version": "V2", "status": "verified"}},
                        {"id": "worker", "agentcore_platform": None}]}
    text = (Path(__file__).parent.parent / "references/phases/design/design.md").read_text()
    code = re.search(r"```python\n(.*?)\n```", text, re.S).group(1)
    # Execute the reviewed producer snippet against the actual scoring CLI output.
    exec(code, {"design": design, "scoring_result": scored})  # nosec B102
    assert design["recommendation_status"] == expected
    if worker_duration == "over_8hr":
        assert scored["units"]["interactive"]["recommendation_status"] == "final"
        assert scored["units"]["worker"]["recommendation_status"] == "provisional"
        assert design["deferred_verification_requirements"]
        assert {r["unit_id"] for r in design["deferred_verification_requirements"]} == {"worker"}
    else:
        assert design["deferred_verification_requirements"] == []
