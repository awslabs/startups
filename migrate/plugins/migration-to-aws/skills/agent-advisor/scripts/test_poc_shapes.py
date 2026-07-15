"""Content lock for references/decision-refs/poc-shapes.md and temporal-poc.md.

The POC shapes are markdown-specified deploy contracts. These tests pin the
security- and cost-load-bearing content (create whitelists, auth modes,
fallback rules, the Temporal TLS contract) so a wording "simplification"
cannot silently turn a locked-down POC into a footgun. Matching is
whitespace-normalized throughout (markdown wraps lines).
"""
import pathlib
import re

SHAPES_MD = (pathlib.Path(__file__).parent.parent
             / "references" / "decision-refs" / "poc-shapes.md")
TEMPORAL_POC_MD = (pathlib.Path(__file__).parent.parent
                   / "references" / "phases" / "temporal-poc" / "temporal-poc.md")
POC_MD = (pathlib.Path(__file__).parent.parent
          / "references" / "phases" / "poc" / "poc.md")
SKILL_MD = pathlib.Path(__file__).parent.parent / "SKILL.md"


def _norm(path):
    return re.sub(r"\s+", " ", path.read_text())


def test_files_exist():
    assert SHAPES_MD.exists(), SHAPES_MD
    assert TEMPORAL_POC_MD.exists(), TEMPORAL_POC_MD


def test_ecs_create_whitelist_and_never_list():
    text = _norm(SHAPES_MD)
    assert "Terraform may create ONLY" in text
    assert "Terraform must NEVER create" in text
    for never in ["VPC", "subnets", "NAT gateway", "internet gateway", "ALB"]:
        assert never in text, f"ECS never-list item missing: {never!r}"
    # No-ALB smoke path: a service that deploys but can't be invoked isn't a POC.
    assert "No ALB" in text
    assert "run-task" in text or "execute-command" in text


def test_ecs_networking_never_creates_vpc():
    text = _norm(SHAPES_MD)
    assert "default VPC" in text
    assert "never create one" in text or "never create a VPC" in text.lower()


def test_eks_unique_namespace_and_no_iam():
    text = _norm(SHAPES_MD)
    assert "agent-advisor-poc-<run_id>" in text, (
        "EKS namespace must be unique per run — a fixed name like 'poc' risks "
        "deleting a user's pre-existing namespace on teardown")
    assert "Never a fixed name" in text
    assert "ClusterIP" in text
    assert "No LoadBalancer" in text
    assert "creates no IAM resources" in text


def test_eks_never_creates_cluster():
    assert "Never creates an EKS cluster" in _norm(SHAPES_MD)


def test_lambda_url_auth_is_iam_never_none():
    text = _norm(SHAPES_MD)
    assert "AWS_IAM" in text
    assert "never `NONE`" in text or "never NONE" in text, (
        "a public Bedrock-invoking Function URL is an open cost hole")


def test_microvms_disabled_fallback():
    text = _norm(SHAPES_MD)
    assert "microvms.tf.disabled" in text
    assert "MicroVMs config pending verification" in text
    assert "No deployable claim" in text


def test_temporal_tls_contract_complete():
    # All six connection vars, explicitly — the API-key-implies-TLS binary
    # broke mTLS self-hosted servers (Codex review, Critical 2).
    for var in ["TEMPORAL_ADDRESS", "TEMPORAL_NAMESPACE", "TEMPORAL_TLS",
                "TEMPORAL_API_KEY", "TEMPORAL_TLS_SERVER_NAME",
                "TEMPORAL_TLS_CA_PATH", "TEMPORAL_TLS_CERT_PATH",
                "TEMPORAL_TLS_KEY_PATH"]:
        assert var in _norm(SHAPES_MD), f"TLS contract var missing: {var}"
        assert var in _norm(TEMPORAL_POC_MD), f"{var} missing from phase file"
    assert "never inferred" in _norm(SHAPES_MD)


def test_temporal_smoke_queue_isolated():
    for text in [_norm(SHAPES_MD), _norm(TEMPORAL_POC_MD)]:
        assert "poc-smoke-<run_id>" in text
        assert "never the user's real queues" in text.lower() or \
            "never touched production queues" in text


def test_temporal_apply_proves_nothing():
    # terraform apply succeeding is not pickup proof — the starter's result is.
    for text in [_norm(SHAPES_MD), _norm(TEMPORAL_POC_MD)]:
        assert "apply alone proves nothing" in text or \
            "proves nothing by itself" in text


def test_temporal_teardown_wording():
    for text in [_norm(SHAPES_MD), _norm(TEMPORAL_POC_MD)]:
        assert "not deletable resources" in text
        assert "ages out" in text


def test_temporal_secrets_never_inline():
    text = _norm(SHAPES_MD)
    assert "SSM Parameter Store" in text or "SSM SecureString" in text
    assert "never inline" in text


def test_poc_md_dispatches_to_shapes():
    text = _norm(POC_MD)
    assert "poc-shapes.md" in text
    assert "RUNTIME DISPATCH" in text
    # The old skip message must be gone.
    assert "supports AgentCore only" not in text


def test_skill_md_rows():
    # SKILL.md's execution moved from a hand-written state-machine table to the
    # interpreter-loop delegation (Routing & gates orchestration prose). The two
    # invariants this test pins are unchanged — only where they live moved.
    text = _norm(SKILL_MD)
    assert "temporal_poc" in text
    # Evaluation order: temporal_poc's trigger must be stated to run before
    # temporal_worker's (which would otherwise swallow the route on resume).
    assert re.search(
        r"evaluate the `temporal_poc` trigger.*?BEFORE the `temporal_worker` trigger",
        text), "SKILL.md must state temporal_poc is evaluated before temporal_worker"
    # Gate 2 / poc is not AgentCore-gated: any winning runtime gets a POC shape.
    gate2 = re.search(r"\*\*Gate 2 → `poc`\*\*(.*?)- Persisting", text)
    assert gate2, "SKILL.md must carry the Gate 2 → poc semantics"
    assert "Any winning runtime" in gate2.group(1)
    assert "== agentcore" not in gate2.group(1)
