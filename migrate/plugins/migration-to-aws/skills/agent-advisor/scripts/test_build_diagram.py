import build_diagram


def test_resolve_runtime_single_winner():
    assert build_diagram.resolve_runtime(
        {"verdict": "agentcore"}, {}) == "agentcore"


def test_resolve_runtime_co_recommend_uses_confirm_choice():
    result = {"verdict": "co_recommend", "co_recommend": ["ecs", "eks"]}
    assert build_diagram.resolve_runtime(result, {"chosen_runtime": "eks"}) == "eks"


def test_resolve_runtime_co_recommend_falls_back_to_first():
    result = {"verdict": "co_recommend", "co_recommend": ["ecs", "eks"]}
    assert build_diagram.resolve_runtime(result, {}) == "ecs"


def test_resolve_runtime_no_viable():
    assert build_diagram.resolve_runtime(
        {"verdict": "no_viable_runtime"}, {}) == "none"


def test_labels_cover_all_runtimes():
    for rid in ("agentcore", "lambda_microvms", "ecs", "eks", "lambda"):
        assert rid in build_diagram.RUNTIME_LABELS


def test_service_labels_include_payments_and_registry():
    # Conditional AgentCore services (SA feedback: relevant but not always).
    assert build_diagram.SERVICE_LABELS["payments"] == "Payments"
    assert build_diagram.SERVICE_LABELS["registry"] == "Registry"


def test_payments_registry_render_in_diagram():
    out = build_diagram.render_mermaid(
        "agentcore", ["identity", "payments", "registry"], "claude_sonnet_4_6", "harness")
    assert "Payments" in out and "Registry" in out


def test_resolve_services_prefers_confirm():
    result = {"agentcore_services": ["identity", "observability"]}
    confirm = {"agentcore_services": ["identity", "memory", "gateway"]}
    assert build_diagram.resolve_services(result, confirm) == [
        "identity", "memory", "gateway"]


def test_resolve_services_falls_back_to_result():
    result = {"agentcore_services": ["identity", "observability"]}
    assert build_diagram.resolve_services(result, {}) == [
        "identity", "observability"]


def test_resolve_services_filters_unknown_and_dedupes():
    confirm = {"agentcore_services": ["identity", "identity", "bogus", "memory"]}
    assert build_diagram.resolve_services({}, confirm) == ["identity", "memory"]


def test_mermaid_has_runtime_model_and_services():
    out = build_diagram.render_mermaid(
        "agentcore", ["identity", "memory"], "claude_sonnet_4_6", "harness")
    assert out.startswith("flowchart TD")
    assert "AgentCore Runtime" in out
    assert "harness" in out.lower()
    assert "claude_sonnet_4_6" in out
    assert "Identity" in out and "Memory" in out
    assert "migration-to-aws" not in out  # no handoff for agentcore


def test_mermaid_model_is_solid_edge_services_are_dotted():
    # Topology: the model is a downstream call (solid invoke edge); services are
    # cross-cutting capabilities attached with a dotted edge into a subgraph.
    out = build_diagram.render_mermaid(
        "agentcore", ["identity", "memory"], "claude_sonnet_4_6", "harness")
    assert "rt -->|invoke| model" in out       # model = solid data-flow edge
    assert 'subgraph svcs["AgentCore services"]' in out
    assert "rt -.-> svcs" in out               # services = dotted attachment
    # Services must NOT be flat solid children of the runtime anymore.
    assert "rt --> svc_identity" not in out


def test_mermaid_no_services_no_subgraph():
    out = build_diagram.render_mermaid(
        "agentcore", [], "claude_sonnet_4_6", "harness")
    assert "subgraph" not in out
    assert "rt -->|invoke| model" in out


def test_mermaid_adds_handoff_note_for_ecs():
    out = build_diagram.render_mermaid("ecs", [], "claude_sonnet_4_6", None)
    assert "Amazon ECS (Fargate)" in out
    assert "migration-to-aws" in out


def test_mermaid_deterministic():
    a = build_diagram.render_mermaid("agentcore", ["identity", "memory"],
                                     "claude_sonnet_4_6", "harness")
    b = build_diagram.render_mermaid("agentcore", ["identity", "memory"],
                                     "claude_sonnet_4_6", "harness")
    assert a == b


def test_ascii_contains_runtime_model_services():
    out = build_diagram.render_ascii(
        "agentcore", ["identity", "memory"], "claude_sonnet_4_6", "harness")
    assert "AgentCore Runtime" in out
    assert "harness" in out.lower()
    assert "claude_sonnet_4_6" in out
    assert "- Identity" in out and "- Memory" in out
    assert "migration-to-aws" not in out
    # Model is on the primary flow; services are attached, not call targets.
    assert "invoke" in out
    assert "attached AgentCore services" in out


def test_ascii_handoff_for_ecs():
    out = build_diagram.render_ascii("ecs", [], "claude_sonnet_4_6", None)
    assert "Amazon ECS" in out
    assert "migration-to-aws" in out


def test_ascii_no_handoff_for_standard_lambda():
    # Standard Lambda is a self-contained Build target (function skeleton), not a
    # heavy-infrastructure handoff — no migration-to-aws note.
    out = build_diagram.render_ascii("lambda", [], "claude_sonnet_4_6", None)
    assert "AWS Lambda" in out
    assert "migration-to-aws" not in out


def test_ascii_deterministic():
    a = build_diagram.render_ascii("eks", ["identity"], "claude_sonnet_4_6", None)
    b = build_diagram.render_ascii("eks", ["identity"], "claude_sonnet_4_6", None)
    assert a == b


def test_build_diagram_end_to_end():
    result = {"verdict": "agentcore", "deployment_model": "harness",
              "agentcore_services": ["identity"],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    assert "flowchart TD" in out["mermaid"]
    assert "AgentCore Runtime" in out["ascii"]


def test_build_diagram_no_viable():
    out = build_diagram.build_diagram({"verdict": "no_viable_runtime"}, {})
    assert "No viable runtime" in out["mermaid"]
    assert "No viable runtime" in out["ascii"]


def test_golden_agentcore_full():
    result = {"verdict": "agentcore", "deployment_model": "framework_on_runtime",
              "agentcore_services": ["identity", "observability", "memory", "gateway"],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    # runtime + deployment model + all four services + model, no handoff
    assert "framework_on_runtime" in out["mermaid"]
    for svc in ("Identity", "Observability", "Memory", "Gateway"):
        assert svc in out["mermaid"] and svc in out["ascii"]
    assert "migration-to-aws" not in out["mermaid"]


def test_golden_lambda_microvms_no_services_no_handoff():
    result = {"verdict": "lambda_microvms", "deployment_model": None,
              "agentcore_services": [],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    assert "Lambda MicroVMs" in out["mermaid"]
    assert "migration-to-aws" not in out["mermaid"]  # MicroVMs is not a handoff runtime


def test_golden_ecs_has_handoff():
    result = {"verdict": "ecs", "deployment_model": None,
              "agentcore_services": ["identity"],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {})
    assert "migration-to-aws" in out["mermaid"]
    assert "migration-to-aws" in out["ascii"]


def test_golden_co_recommend_renders_chosen():
    result = {"verdict": "co_recommend", "co_recommend": ["ecs", "eks"],
              "deployment_model": None, "agentcore_services": [],
              "model_recommendation": {"model": "claude_sonnet_4_6"}}
    out = build_diagram.build_diagram(result, {"chosen_runtime": "eks"})
    assert "Amazon EKS" in out["mermaid"]
    assert "migration-to-aws" in out["mermaid"]  # eks is a handoff runtime
