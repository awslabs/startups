"""Tests for iam_policy.py — scoped IAM policy generation."""
import json
import subprocess  # nosec B404 — test-only, inputs are hardcoded literals
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from iam_policy import (
    foundation_model_arn,
    generate_policy,
    is_mantle_model,
    mantle_project_arn,
    inference_profile_arn,
    is_inference_profile,
)

REGION = "us-east-1"
ACCOUNT = "123456789012"


class TestIsInferenceProfile:
    def test_geo_prefix_us(self):
        assert is_inference_profile("us.anthropic.claude-sonnet-5")

    def test_geo_prefix_eu(self):
        assert is_inference_profile("eu.anthropic.claude-haiku-4-5-20251001-v1:0")

    def test_no_prefix(self):
        assert not is_inference_profile("anthropic.claude-haiku-4-5-20251001-v1:0")

    def test_amazon_model(self):
        assert not is_inference_profile("amazon.nova-lite-v1:0")


class TestArnGeneration:
    def test_foundation_model_arn(self):
        arn = foundation_model_arn("anthropic.claude-haiku-4-5-20251001-v1:0")
        assert arn == "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_inference_profile_arn(self):
        arn = inference_profile_arn("us.anthropic.claude-sonnet-5", REGION, ACCOUNT)
        assert arn == f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-sonnet-5"


class TestGeneratePolicy:
    def test_single_foundation_model(self):
        policy = generate_policy(["anthropic.claude-haiku-4-5-20251001-v1:0"], REGION, ACCOUNT)
        assert policy["Version"] == "2012-10-17"
        stmt = policy["Statement"][0]
        assert stmt["Effect"] == "Allow"
        assert "bedrock:InvokeModel" in stmt["Action"]
        assert "bedrock:InvokeModelWithResponseStream" in stmt["Action"]
        assert len(stmt["Resource"]) == 1
        assert "foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0" in stmt["Resource"][0]

    def test_inference_profile_generates_dual_arns(self):
        policy = generate_policy(["us.anthropic.claude-sonnet-5"], REGION, ACCOUNT)
        resources = policy["Statement"][0]["Resource"]
        assert len(resources) == 2
        has_foundation = any("foundation-model/" in r for r in resources)
        has_profile = any("inference-profile/" in r for r in resources)
        assert has_foundation
        assert has_profile

    def test_mixed_models(self):
        models = [
            "us.anthropic.claude-sonnet-5",
            "amazon.nova-lite-v1:0",
        ]
        policy = generate_policy(models, REGION, ACCOUNT)
        resources = policy["Statement"][0]["Resource"]
        assert any("nova-lite" in r for r in resources)
        assert any("inference-profile/" in r for r in resources)

    def test_deduplicates_models(self):
        models = ["amazon.nova-lite-v1:0", "amazon.nova-lite-v1:0"]
        policy = generate_policy(models, REGION, ACCOUNT)
        resources = policy["Statement"][0]["Resource"]
        assert len(resources) == 1

    def test_empty_models(self):
        policy = generate_policy([], REGION, ACCOUNT)
        assert policy["Statement"][0]["Resource"] == []


class TestCLI:
    def test_stdout_output(self):
        result = subprocess.run(  # nosec B603
            [
                sys.executable, str(Path(__file__).parent / "iam_policy.py"),
                "--models", "amazon.nova-lite-v1:0",
                "--region", REGION,
                "--account-id", ACCOUNT,
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        policy = json.loads(result.stdout)
        assert policy["Statement"][0]["Sid"] == "BedrockInvokeModelScoped"

    def test_file_output(self, tmp_path):
        out = tmp_path / "policy.json"
        result = subprocess.run(  # nosec B603
            [
                sys.executable, str(Path(__file__).parent / "iam_policy.py"),
                "--models", "us.anthropic.claude-sonnet-5,amazon.nova-lite-v1:0",
                "--region", REGION,
                "--account-id", ACCOUNT,
                "--output", str(out),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        policy = json.loads(out.read_text())
        assert len(policy["Statement"][0]["Resource"]) == 3


def test_mantle_model_detection_excludes_gpt_oss():
    assert is_mantle_model("openai.gpt-5.6-terra") is True
    assert is_mantle_model("openai.gpt-5.5") is True
    assert is_mantle_model("openai.gpt-oss-120b-1:0") is False
    assert is_mantle_model("anthropic.claude-sonnet-4-6") is False


def test_mantle_target_gets_mantle_actions_not_invoke_model():
    # Regression: the generated policy emitted only bedrock:InvokeModel against a
    # foundation-model ARN, which cannot authorize a mantle call — the migrated app
    # would deploy and immediately fail authorization.
    pol = generate_policy(["openai.gpt-5.6-terra"], "us-east-1", "111122223333")
    sids = {s["Sid"] for s in pol["Statement"]}
    assert "BedrockMantleInference" in sids
    assert "BedrockMantleCallWithBearerToken" in sids
    # An all-mantle run must NOT emit an InvokeModel statement with an empty
    # Resource list — that is an invalid IAM policy.
    assert "BedrockInvokeModelScoped" not in sids
    for s in pol["Statement"]:
        assert s.get("Resource"), s["Sid"]


def test_mantle_bearer_token_is_scoped_to_star():
    # AWS does not support narrowing CallWithBearerToken; it must be "*".
    pol = generate_policy(["openai.gpt-5.5"], "us-east-1", "111122223333")
    bearer = [s for s in pol["Statement"] if s["Sid"] == "BedrockMantleCallWithBearerToken"][0]
    assert bearer["Resource"] == "*"
    assert bearer["Action"] == ["bedrock-mantle:CallWithBearerToken"]


def test_mantle_inference_uses_only_documented_exact_actions():
    pol = generate_policy(["openai.gpt-5.5"], "us-west-2", "999988887777")
    inf = [s for s in pol["Statement"] if s["Sid"] == "BedrockMantleInference"][0]
    assert inf["Resource"] == "arn:aws:bedrock-mantle:us-west-2:999988887777:project/*"
    assert inf["Action"] == [
        "bedrock-mantle:CreateInference",
        "bedrock-mantle:GetProject",
        "bedrock-mantle:ListProjects",
    ]
    assert all("*" not in action for action in inf["Action"])


def test_mixed_targets_emit_both_runtime_and_mantle_statements():
    pol = generate_policy(
        ["openai.gpt-5.6-luna", "us.anthropic.claude-sonnet-4-6"], "us-east-1", "111122223333")
    sids = [s["Sid"] for s in pol["Statement"]]
    assert "BedrockInvokeModelScoped" in sids
    assert "BedrockMantleInference" in sids
    invoke = [s for s in pol["Statement"] if s["Sid"] == "BedrockInvokeModelScoped"][0]
    # The mantle model must not leak into the InvokeModel resource list.
    assert not any("gpt-5" in r for r in invoke["Resource"])


def test_gpt_oss_stays_on_the_runtime_path():
    pol = generate_policy(["openai.gpt-oss-120b-1:0"], "us-east-1", "111122223333")
    sids = {s["Sid"] for s in pol["Statement"]}
    assert sids == {"BedrockInvokeModelScoped"}


def test_selected_runtime_path_overrides_bare_gpt_legacy_inference():
    policy = generate_policy(
        ["openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai_responses")
    assert {stmt["Sid"] for stmt in policy["Statement"]} == {
        "BedrockInvokeModelScoped", "BedrockResponsesDefaultProject"}
    invoke = next(stmt for stmt in policy["Statement"]
                  if stmt["Sid"] == "BedrockInvokeModelScoped")
    assert invoke["Resource"] == [
        "arn:aws:bedrock:*::foundation-model/openai.gpt-5.4"]


def test_selected_mantle_path_overrides_non_gpt_legacy_inference():
    policy = generate_policy(
        ["anthropic.claude-sonnet-5"], REGION, ACCOUNT, "mantle_messages")
    assert {stmt["Sid"] for stmt in policy["Statement"]} == {
        "BedrockMantleInference", "BedrockMantleCallWithBearerToken"}


def test_unknown_selected_path_fails_closed():
    with pytest.raises(ValueError, match="unknown Bedrock API path"):
        generate_policy(["openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai")


def test_cli_accepts_selected_api_path():
    result = subprocess.run(  # nosec B603
        [sys.executable, str(Path(__file__).parent / "iam_policy.py"),
         "--models", "openai.gpt-5.4", "--api-path", "runtime_openai_chat",
         "--region", REGION, "--account-id", ACCOUNT],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["Statement"][0]["Sid"] == "BedrockInvokeModelScoped"


def test_cris_route_gets_profile_permission():
    policy = generate_policy(
        ["global.openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai_chat")
    profile = next(stmt for stmt in policy["Statement"]
                   if stmt["Sid"] == "BedrockGetInferenceProfile")
    assert profile["Action"] == ["bedrock:GetInferenceProfile"]
    assert profile["Resource"] == [
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/global.openai.gpt-5.4"]


def test_runtime_responses_gets_default_project_but_other_runtime_paths_do_not():
    response_policy = generate_policy(
        ["global.openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai_responses")
    project = next(stmt for stmt in response_policy["Statement"]
                   if stmt["Sid"] == "BedrockResponsesDefaultProject")
    assert project["Action"] == ["bedrock:InvokeModel"]
    assert project["Resource"] == f"arn:aws:bedrock:{REGION}:{ACCOUNT}:project/default"

    for path in ("runtime_openai_chat", "runtime_messages", "runtime_converse", "runtime_invoke"):
        policy = generate_policy(["global.openai.gpt-5.4"], REGION, ACCOUNT, path)
        assert "BedrockResponsesDefaultProject" not in {
            stmt["Sid"] for stmt in policy["Statement"]}


def test_stored_response_actions_are_feature_gated():
    policy = generate_policy(
        ["global.openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai_responses",
        [["response_get", "response_delete"]],
    )
    stored = next(stmt for stmt in policy["Statement"]
                  if stmt["Sid"] == "BedrockStoredResponses")
    assert stored["Action"] == ["bedrock:DeleteInvoke", "bedrock:GetInvoke"]

    plain = generate_policy(
        ["global.openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai_responses")
    assert "BedrockStoredResponses" not in {stmt["Sid"] for stmt in plain["Statement"]}


def test_web_search_actions_are_route_feature_gated():
    policy = generate_policy(
        ["openai.gpt-5.5"], REGION, ACCOUNT, "mantle_openai_responses",
        [["web_search"]],
    )
    web = next(stmt for stmt in policy["Statement"] if stmt["Sid"] == "BedrockWebSearch")
    assert web["Action"] == [
        "bedrock-websearch:InvokeSearch", "bedrock-websearch:InvokeFetch"]
    assert web["Resource"] == "*"
    assert web["Condition"] == {"StringEquals": {"aws:RequestedRegion": REGION}}


def test_external_web_access_requires_explicit_feature():
    cached = generate_policy(
        ["openai.gpt-5.5"], REGION, ACCOUNT, "mantle_openai_responses",
        [["web_search"]],
    )
    external = generate_policy(
        ["openai.gpt-5.5"], REGION, ACCOUNT, "mantle_openai_responses",
        [["web_search", "external_web_access"]],
    )
    assert "bedrock-websearch:ExternalWebAccess" not in next(
        stmt for stmt in cached["Statement"] if stmt["Sid"] == "BedrockWebSearch")["Action"]
    assert "bedrock-websearch:ExternalWebAccess" in next(
        stmt for stmt in external["Statement"] if stmt["Sid"] == "BedrockWebSearch")["Action"]


def test_cli_emits_mixed_runtime_mantle_and_web_search_statements():
    result = subprocess.run(  # nosec B603
        [sys.executable, str(Path(__file__).parent / "iam_policy.py"),
         "--models", "global.openai.gpt-5.4,openai.gpt-5.5",
         "--api-path", "runtime_openai_chat,mantle_openai_responses",
         "--features-json", '[[],["web_search"]]',
         "--region", REGION, "--account-id", ACCOUNT],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    sids = {stmt["Sid"] for stmt in json.loads(result.stdout)["Statement"]}
    assert {"BedrockInvokeModelScoped", "BedrockGetInferenceProfile",
            "BedrockMantleInference", "BedrockMantleCallWithBearerToken",
            "BedrockWebSearch"} <= sids


def test_unknown_route_feature_fails_closed():
    with pytest.raises(ValueError, match="unknown IAM route feature"):
        generate_policy(
            ["openai.gpt-5.5"], REGION, ACCOUNT, "mantle_openai_responses",
            [["unverified_feature"]],
        )


def test_route_features_must_match_the_selected_api():
    with pytest.raises(ValueError, match="stored-response IAM features"):
        generate_policy(
            ["global.openai.gpt-5.4"], REGION, ACCOUNT, "runtime_openai_chat",
            [["response_get"]],
        )
    with pytest.raises(ValueError, match="mantle_openai_responses"):
        generate_policy(
            ["openai.gpt-5.5"], REGION, ACCOUNT, "mantle_openai_chat",
            [["web_search"]],
        )
    with pytest.raises(ValueError, match="mantle_openai_responses"):
        generate_policy(
            ["global.openai.gpt-5.4"], REGION, ACCOUNT,
            "runtime_openai_responses", [["web_search"]],
        )
    with pytest.raises(ValueError, match="requires web_search"):
        generate_policy(
            ["openai.gpt-5.5"], REGION, ACCOUNT, "mantle_openai_responses",
            [["external_web_access"]],
        )
