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


def test_minimum_gcp_design_route_is_accepted_without_inferred_defaults():
    from evaluation_routes import assign_case_routes

    route = {
        "source_provider": "openai",
        "source_model": "gpt-5.4",
        "workload_id": "wl-chat",
        "call_sites": ["src/app.py:20"],
        "aws_model_id": "global.openai.gpt-5.4",
        "migration_path": "runtime_openai_chat",
        "model_change": False,
        "iam_features": [],
    }
    [assigned] = assign_case_routes(
        [{"id": "p1", "workload_id": "wl-chat", "call_site": "src/app.py:20"}],
        [route],
    )
    assert all(assigned[field] == route[field] for field in route)

    gcp_design = read("gcp-to-aws/references/phases/design/design-ai.md")
    for field in ("source_provider", "source_model", "workload_id", "call_sites[]",
                  "model_change", "iam_features[]", "migration_path"):
        assert field in gcp_design


def test_minimum_azure_design_route_is_consumable_without_inferred_defaults():
    from evaluation_routes import assign_case_routes

    route = {
        "source_provider": "openai",
        "source_model": "gpt-5.4",
        "workload_id": "wl-chat",
        "call_sites": ["src/app.py:20"],
        "aws_model_id": "global.openai.gpt-5.4",
        "migration_path": "runtime_openai_chat",
        "model_change": False,
        "iam_features": [],
    }
    [assigned] = assign_case_routes(
        [{"id": "p1", "workload_id": "wl-chat", "call_site": "src/app.py:20"}],
        [route],
    )
    assert all(assigned[field] == route[field] for field in route)

    schema = read("azure-to-aws/references/shared/schema-design-aws-ai.md")
    generate = read("azure-to-aws/references/phases/generate/generate-artifacts-ai.md")
    for field in ("source_provider", "source_model", "workload_id", "call_sites[]",
                  "model_change", "iam_features[]", "migration_path"):
        assert field in schema
        assert field in generate
    assert "source_model_id`" not in schema


def test_azure_openrouter_same_model_routes_dispatch_to_exact_endpoint_lane():
    fixtures = [
        {
            "openrouter_path": "same_model_runtime",
            "aws_model_id": "global.openai.gpt-5.4",
            "migration_path": "runtime_openai_chat",
        },
        {
            "openrouter_path": "same_model_mantle",
            "aws_model_id": "openai.gpt-5.4",
            "migration_path": "mantle_openai_chat",
        },
    ]
    schema = read("azure-to-aws/references/shared/schema-design-aws-ai.md")
    generate = read("azure-to-aws/references/phases/generate/generate-artifacts-ai.md")
    for fixture in fixtures:
        assert fixture["openrouter_path"] in schema
        assert fixture["openrouter_path"] in generate
        assert fixture["migration_path"] in generate
    assert "same_model_runtime` selects the" in generate
    assert "runs Step 1R" in generate
    assert "same_model_mantle` selects the" in generate
    assert "runs Step 1M" in generate
    assert "Never route `same_model_runtime` through LiteLLM" in generate


def test_rewriter_final_guards_preserve_compatible_sdks_per_route():
    rewriter = (SKILLS.parent / "agents/llm2bedrock-code-rewriter.md").read_text()
    for path in (
        "runtime_openai_responses", "runtime_openai_chat", "runtime_messages",
        "mantle_openai_responses", "mantle_openai_chat", "mantle_messages",
    ):
        assert path in rewriter
    assert "require the OpenAI dependency/import to remain" in rewriter
    assert "require the Anthropic dependency/import to" in rewriter
    assert "mixed compatible/native repositories" in rewriter
    assert "A source-SDK import is not itself a residual failure" in rewriter
    assert "reject source-SDK imports only" in rewriter


def test_standalone_generators_bundle_and_execute_iam_helper():
    import importlib.util

    for skill in ("gcp-to-aws", "azure-to-aws"):
        helper = SKILLS / skill / "scripts/iam_policy.py"
        assert helper.is_file()
        spec = importlib.util.spec_from_file_location(f"{skill}_iam", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        policy = module.generate_policy(
            ["global.openai.gpt-5.4", "openai.gpt-5.5"],
            "us-east-1", "123456789012",
            ["runtime_openai_chat", "mantle_openai_responses"],
            [[], ["web_search", "external_web_access"]],
        )
        sids = {statement["Sid"] for statement in policy["Statement"]}
        assert {"BedrockInvokeModelScoped", "BedrockMantleInference",
                "BedrockWebSearch"} <= sids
        web = next(statement for statement in policy["Statement"]
                   if statement["Sid"] == "BedrockWebSearch")
        assert "bedrock-websearch:ExternalWebAccess" in web["Action"]

        generate = read(f"{skill}/references/phases/generate/generate.md")
        assert "$SKILL_BASE/scripts/iam_policy.py" in generate
        assert "bedrock-iam-policy.json" in generate


def test_evaluator_reuses_path_specific_preflight_and_vision_clients():
    evaluator = (SKILLS.parent / "agents/llm2bedrock-prompt-evaluator.md").read_text()
    assert "from preflight_bedrock import probe_compatible_model" in evaluator
    assert "from preflight_bedrock import runtime_openai_client, mantle_openai_client" in evaluator
    assert 'path = "<EXACT_MIGRATION_PATH>"' in evaluator
    assert "BedrockOpenAI(" not in evaluator
    assert "Runtime paths require" in evaluator
    assert "Mantle paths require" in evaluator


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
