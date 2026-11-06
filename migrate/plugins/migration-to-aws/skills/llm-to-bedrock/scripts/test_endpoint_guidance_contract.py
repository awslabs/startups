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


def endpoint_requirements_value(preferences: dict) -> list[str]:
    """Mirror the documented consumer path for artifact-shape regression coverage."""
    return preferences["ai_constraints"]["ai_endpoint_requirements"]["value"]


def test_endpoint_requirements_artifact_shape_empty_and_nonempty():
    for value in ([], ["web_search", "strict_in_region"]):
        preferences = {
            "ai_constraints": {
                "ai_endpoint_requirements": {
                    "value": value,
                    "chosen_by": "derived",
                    "prompt": "Confirmed endpoint requirements",
                    "design_consequence": "Select the matching endpoint",
                }
            }
        }
        assert endpoint_requirements_value(preferences) == value

    for skill in ("gcp-to-aws", "azure-to-aws"):
        assembler = read(f"{skill}/references/phases/clarify/clarify-assemble.md")
        design = read(f"{skill}/references/phases/design/design-ai.md")
        assert "ai_endpoint_requirements" in assembler and "value" in assembler
        assert "ai_constraints.ai_endpoint_requirements.value" in design


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
    assert "bedrock-runtime.{region}.amazonaws.com/anthropic" in combined
    assert "bedrock-mantle.{region}.api.aws/openai/v1" in combined
    assert "bedrock:InvokeModel" in combined
    for action in (
        "CreateInference", "GetProject", "ListProjects", "CallWithBearerToken"):
        assert action in combined
    assert "bedrock-mantle:*" not in combined
    assert "auto-refreshing short-lived" in combined


def test_llm_executor_consumes_the_delegated_exact_vocabulary():
    skill = read("llm-to-bedrock/SKILL.md")
    analyzer = (SKILLS.parent / "agents/llm2bedrock-code-analyzer.md").read_text()
    rewriter = (SKILLS.parent / "agents/llm2bedrock-code-rewriter.md").read_text()
    assert "gcp-to-aws" in skill
    for path in EXACT_PATHS:
        assert path in skill
    assert "Bedrock workload routes:" in skill
    assert "mixed" in skill
    assert "Responses+Chat or OpenAI+Anthropic" in skill
    assert "Unsupported or ambiguous call-site" in analyzer and "route:" in analyzer
    assert "Unsupported or ambiguous call-site route" in rewriter
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


def test_workload_route_identity_survives_every_execution_stage():
    skill = read("llm-to-bedrock/SKILL.md")
    agents = {
        name: (SKILLS.parent / f"agents/{name}.md").read_text()
        for name in (
            "llm2bedrock-code-analyzer", "llm2bedrock-log-ingestor",
            "llm2bedrock-prompt-evaluator", "llm2bedrock-code-rewriter",
            "llm2bedrock-report-generator",
        )
    }
    for field in ("workload_id", "model_change", "iam_features"):
        assert field in skill
        assert all(field in text for text in agents.values())
    assert "never merge" in skill.lower()
    assert "assign_case_routes" in agents["llm2bedrock-prompt-evaluator"]
    assert "dispatch_cases" in agents["llm2bedrock-prompt-evaluator"]
    assert "prompt id alone" in agents["llm2bedrock-code-rewriter"].lower()
    assert "<BEDROCK_API_PATH>" not in agents["llm2bedrock-report-generator"]


def test_generated_iam_guidance_carries_route_features():
    shared = read("shared/ai/ai-openai-to-bedrock.md")
    report = (SKILLS.parent / "agents/llm2bedrock-report-generator.md").read_text()
    for skill in ("gcp-to-aws", "azure-to-aws"):
        design = read(f"{skill}/references/phases/design/design-ai.md")
        generate = read(f"{skill}/references/phases/generate/generate-artifacts-ai.md")
        assert "iam_features" in design
        assert "iam_features" in generate
        for action in ("InvokeSearch", "InvokeFetch", "ExternalWebAccess"):
            assert action in generate
    for text in (shared, report):
        assert "bedrock:GetInferenceProfile" in text
        assert "project/default" in text
        assert "bedrock-websearch:InvokeSearch" in text
        assert "bedrock-websearch:InvokeFetch" in text
        assert "bedrock-websearch:ExternalWebAccess" in text
        assert "security-web-search.html" in text
