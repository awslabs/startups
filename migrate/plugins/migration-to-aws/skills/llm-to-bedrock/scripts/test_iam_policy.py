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
    inference_profile_arn,
    is_inference_profile,
)

REGION = "us-east-1"
ACCOUNT = "123456789012"


class TestIsInferenceProfile:
    def test_geo_prefix_us(self):
        assert is_inference_profile("us.anthropic.claude-sonnet-4-20250514-v1:0")

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
        arn = inference_profile_arn("us.anthropic.claude-sonnet-4-20250514-v1:0", REGION, ACCOUNT)
        assert arn == f"arn:aws:bedrock:{REGION}:{ACCOUNT}:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"


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
        policy = generate_policy(["us.anthropic.claude-sonnet-4-20250514-v1:0"], REGION, ACCOUNT)
        resources = policy["Statement"][0]["Resource"]
        assert len(resources) == 2
        has_foundation = any("foundation-model/" in r for r in resources)
        has_profile = any("inference-profile/" in r for r in resources)
        assert has_foundation
        assert has_profile

    def test_mixed_models(self):
        models = [
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
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
                "--models", "us.anthropic.claude-sonnet-4-20250514-v1:0,amazon.nova-lite-v1:0",
                "--region", REGION,
                "--account-id", ACCOUNT,
                "--output", str(out),
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        policy = json.loads(out.read_text())
        assert len(policy["Statement"][0]["Resource"]) == 3
