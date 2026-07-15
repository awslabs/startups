"""Content lock for references/decision-refs/temporal.md.

The temporal_worker branch has no scoring script — its Tier 1 decision table and
cutover-runbook preconditions live as markdown. These tests pin the
load-bearing content (eliminations, rule order, precondition wording, status
labels) so an edit that weakens them fails loudly, in the same spirit as the
model-pool drift tests in test_scoring.py.
"""
import pathlib
import re

TEMPORAL_MD = (pathlib.Path(__file__).parent.parent
               / "references" / "decision-refs" / "temporal.md")
BRANCH_MD = (pathlib.Path(__file__).parent.parent
             / "references" / "phases" / "temporal-worker" / "temporal-worker.md")


def _text():
    return TEMPORAL_MD.read_text()


def test_file_exists():
    assert TEMPORAL_MD.exists(), TEMPORAL_MD


def test_tier1_eliminations_present():
    text = _text()
    for runtime, reason_fragment in [
        ("Lambda classic", "15-min cap"),
        ("AgentCore Runtime", "8-hour max execution"),
        ("Lambda MicroVMs", "resident-polling cost"),
    ]:
        pattern = re.escape(runtime) + r".{0,200}" + re.escape(reason_fragment)
        assert re.search(pattern, text, re.DOTALL), (
            f"Tier 1 elimination for '{runtime}' (reason '{reason_fragment}') "
            "missing or reworded — the branch depends on it")


def test_tier1_tension_rule_is_first():
    # The K8s+low/spiky tension rule must stay rule 1: if the plain
    # "K8s → EKS" direct-pick evaluates first, the tension case can never fire.
    text = _text()
    tension = text.find("the only genuine tension")
    eks_pick = text.find("team already operates K8s")
    assert tension != -1 and eks_pick != -1, "Tier 1 rules missing"
    assert tension < eks_pick, (
        "tension rule must precede the EKS direct-pick (rules are first-match-wins)")


def test_tier1_rules_are_first_match_wins():
    assert "first match wins" in _text() or "IN ORDER" in _text()


def test_tier1_user_choice_gates_are_marked():
    # Rules 1 and 4 are offers, not direct picks. If rule 4 loses its OFFER
    # wording, an agent will auto-split task queues without asking — and a
    # declined split gets misrecorded as "rule 5 default" (observed in the
    # first live test before this was pinned).
    text = _text()
    assert "OFFER a split" in text, "rule 4 must be an offer (AskUserQuestion)"
    assert "declining it is legitimate" in text
    assert "NOT as falling through to rule 5" in text


def test_serverless_workers_labeled_prerelease():
    text = _text()
    assert "PRE-RELEASE" in text
    # The trap this guards: docs.temporal.io shows "Available" — outputs must
    # not launder that into GA.
    assert "do not trust the docs label" in text.lower() or \
        "Do not trust the docs label" in text


def test_runbook1_preconditions_locked():
    text = _text()
    for fragment in [
        "SAME workflow and activity types",
        "GRACEFULLY",
        "do NOT migrate mid-execution",
        "retry policies + heartbeat timeouts",
    ]:
        assert fragment in text, f"runbook 1 precondition missing: {fragment!r}"


def test_runbook2_warns_no_history_migration_tool():
    # Whitespace-tolerant: the sentence may wrap across markdown lines.
    normalized = re.sub(r"\s+", " ", _text())
    assert "no official cross-cluster history migration tool" in normalized


def test_runbook3_determinism_broader_than_signatures():
    text = _text()
    assert "broader than Activity signatures" in text
    assert "NOT a" in text and "compatibility layer" in text
    assert "Worker Versioning" in text


def test_way_table_defaults_to_way1():
    text = _text()
    assert "Way 1 (default)" in text
    assert "External Payload Storage" in text  # must be surfaced before Way 2


def test_commercials_split_by_current_state():
    # Users already on Temporal Cloud must not be pitched the Marketplace
    # subscribe flow — they have a namespace and pay for it already.
    text = re.sub(r"\s+", " ", _text())  # tolerate markdown line wraps
    assert "Already on Temporal Cloud" in text
    assert "do NOT pitch the subscribe flow" in text
    assert "not a technical" in text  # billing move is a commercial question
    assert "New Temporal Cloud customer" in text


def test_sfn_comparison_is_chat_only():
    # User decision (2026-07-08): the plan must NOT contain a Step Functions
    # comparison section; the facts live in decision-refs only as a chat
    # fallback for when the user asks.
    text = _text()
    assert "does NOT include a Step Functions comparison" in text
    assert "Do not volunteer this unprompted" in text
    for fragment in ["waitForTaskToken", "1-year Standard", "time-skipping"]:
        assert fragment in text, f"SFN chat-fallback fact missing: {fragment!r}"
    branch = BRANCH_MD.read_text()
    assert "No Step Functions comparison section" in branch, (
        "the branch's output spec must say the plan has no SFN section")


def test_branch_points_at_decision_ref():
    # The branch must load this file rather than restating rules from memory.
    branch = BRANCH_MD.read_text()
    assert "decision-refs/temporal.md" in branch


def test_branch_adapter_dimensions_are_legal():
    # The Tier 2 agent-session adapter table in the branch file must only name
    # real scoring dimensions with legal values — otherwise scoring.py rejects
    # or silently defaults the input.
    import scoring
    branch = BRANCH_MD.read_text()
    # Single-dimension rows only (the catch-all "others → unknown" row lists
    # several dims in one cell and defines no value mapping).
    # `\`dim\` +\|` tolerates the multiple spaces dprint's table alignment
    # inserts after short cell values (single-space match would false-fail).
    table_rows = re.findall(r"^\s*\| `([a-z_]+)` +\|", branch, re.MULTILINE)
    adapter_dims = [d for d in table_rows if d in scoring.DIMENSIONS]
    assert len(adapter_dims) >= 8, (
        f"adapter table looks broken — only found {adapter_dims}")
    # Backtick-quoted answer values mentioned in adapter rows must be legal.
    for dim in adapter_dims:
        row = re.search(r"\| `" + dim + r"` +\|([^\n]*)", branch).group(1)
        for value in re.findall(r"`([a-z0-9_]+)`", row):
            assert value in scoring.LEGAL_VALUES[dim], (
                f"adapter maps {dim} to illegal value {value!r} "
                f"(legal: {scoring.LEGAL_VALUES[dim]})")
