"""Contracts for Runtime-default delegated migration guidance."""
from pathlib import Path


SKILLS = Path(__file__).resolve().parents[2]
EXACT_PATHS = {
    "runtime_openai_responses",
    "runtime_openai_chat",
    "runtime_messages",
    "mantle_openai_responses",
    "mantle_openai_chat",
    "mantle_messages",
    "runtime_converse",
    "runtime_invoke",
}
REQUIREMENTS = {
    "background_inference",
    "server_side_tools",
    "web_search",
    "projects",
    "workspaces",
    "required_model_api",
    "strict_in_region",
}
PUBLIC_LINKS = {
    "https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html",
    "https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html",
}


def read(relative: str) -> str:
    return (SKILLS / relative).read_text()


def test_runtime_default_and_verified_mantle_selectors_are_reachable():
    for skill in ("gcp-to-aws", "azure-to-aws"):
        entrypoint = read(f"{skill}/SKILL.md")
        design = read(f"{skill}/references/phases/design/design-ai.md")
        clarify = read(f"{skill}/references/phases/clarify/clarify-ai.md")
        discovery = read(f"{skill}/references/phases/discover/discover-app-code.md")

        assert "Runtime by default" in entrypoint
        assert "Endpoint availability" in design
        assert "Programmatic Access" in design
        assert "API compatibility" in design
        assert "Region" in design
        assert "ai_endpoint_requirements" in clarify
        assert "source_api_surface" in discovery
        assert "endpoint_sensitive_features" in discovery
        assert REQUIREMENTS <= set(word.strip("`.,;:()") for word in (clarify + discovery + design).split())
        assert EXACT_PATHS <= set(word.strip("`.,;:()") for word in design.split())


def test_exact_paths_reach_generation_with_matching_hosts_and_iam():
    gcp = read("gcp-to-aws/references/phases/generate/generate-artifacts-ai.md")
    azure = read("azure-to-aws/references/phases/generate/generate-artifacts-ai.md")
    combined = gcp + azure

    for path in EXACT_PATHS:
        assert path in gcp
        assert path in azure
    assert "bedrock-runtime.{region}.amazonaws.com/openai/v1" in combined
    assert "bedrock-runtime.{region}.amazonaws.com/anthropic/v1" in combined
    assert "bedrock-mantle.{region}.api.aws/openai/v1" in combined
    assert "bedrock:InvokeModel" in combined
    assert "bedrock-mantle:*" in combined
    assert "auto-refreshing short-lived" in combined


def test_llm_executor_consumes_the_delegated_exact_vocabulary():
    skill = read("llm-to-bedrock/SKILL.md")
    assert "gcp-to-aws" in skill
    for path in EXACT_PATHS:
        assert path in skill
    assert "unknown" in skill.lower() and "STOP" in skill


def test_public_sources_and_current_gpt_metadata_are_present():
    for skill in ("gcp-to-aws", "azure-to-aws"):
        facts = read(f"{skill}/references/shared/openai-on-bedrock.md")
        pricing = read(f"{skill}/references/shared/pricing-cache.md")
        for link in PUBLIC_LINKS:
            assert link in facts
        assert "us.openai.gpt-5.4" in facts
        assert "global.openai.gpt-5.4" in facts
        assert "us.openai.gpt-5.5" in facts
        assert "global.openai.gpt-5.5" in facts
        assert "Responses, Chat Completions" in facts
        assert "Runtime CRIS" in pricing
        assert "endpoint choice does not change" in pricing or "same across Runtime and Mantle" in facts


def test_web_search_and_throughput_guidance_match_public_contract():
    openai = read("shared/ai/ai-openai-to-bedrock.md")
    guardrails = read("shared/ai/ai-migration-guardrails.md")
    combined = openai + guardrails

    assert "Web Search" in combined
    assert "preconfigured" in combined
    assert "Mantle has no RPM quota" in guardrails
    assert "separate per-model, per-Region" in guardrails
    assert "model-specific RPM quotas where applicable" in guardrails
    assert "bounded concurrency" in guardrails
    assert "finite retry budget" in guardrails


def test_known_stale_or_private_claims_are_absent():
    files = [
        "shared/ai/ai-openai-to-bedrock.md",
        "shared/ai/ai-anthropic-to-bedrock.md",
        "shared/ai/ai-migration-guardrails.md",
    ]
    for skill in ("gcp-to-aws", "azure-to-aws"):
        files.extend(
            [
                f"{skill}/references/shared/openai-on-bedrock.md",
                f"{skill}/references/phases/clarify/clarify-ai-only.md",
                f"{skill}/references/phases/design/design-ai.md",
                f"{skill}/references/phases/generate/generate-artifacts-ai.md",
            ]
        )
    text = "\n".join(read(file) for file in files).lower()
    forbidden = (
        "mantle-only and in-region only",
        "mantle only; no",
        "chat completions support is unverified",
        "must reshape to responses",
        "internal reference probe",
        "internal migration reference",
        "aws internal",
    )
    for phrase in forbidden:
        assert phrase not in text
