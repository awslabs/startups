"""Tests for heroku-to-aws migration report validation (--mode full / decision).

Heroku's validator had zero test coverage before this file. Mirrors the
pattern in test_validate_migration_report.py (subprocess-driven, inline HTML
fixtures) rather than importing the validator module directly, since the
script is invoked as a CLI in every skill call site.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "validate-heroku-migration-report.py"

FULL_MINIMAL_PASS = """<!DOCTYPE html>
<html><body>
<section id="decision-summary"><h2>Decision</h2></section>
<section id="exec-costs"><h2>Costs</h2></section>
<section id="next-steps"><h2>Next steps</h2></section>
<footer>draft for review</footer>
</body></html>
"""

DECISION_MINIMAL_PASS = """<!DOCTYPE html>
<html><body>
<section id="decision-summary"><h2>Decision</h2></section>
<section id="exec-costs"><h2>Costs</h2></section>
<section id="decision-cta"><h2>Ready to execute?</h2></section>
<footer>draft for review</footer>
</body></html>
"""


def run_validator(
    html_path: Path,
    *,
    mode: str = "full",
    migration_dir: Path | None = None,
) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPT), str(html_path), "--mode", mode]
    if migration_dir is not None:
        cmd.extend(["--migration-dir", str(migration_dir)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


# --- full mode (existing behavior, now with explicit --mode full) ---


def test_full_minimal_passes(tmp_path: Path) -> None:
    path = tmp_path / "migration-report.html"
    path.write_text(FULL_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="full")
    assert code == 0, out
    assert "REPORT_OK" in out
    assert "mode=full" in out


def test_full_missing_next_steps_fails(tmp_path: Path) -> None:
    html = FULL_MINIMAL_PASS.replace(
        '<section id="next-steps"><h2>Next steps</h2></section>', ""
    )
    path = tmp_path / "migration-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="full")
    assert code == 1, out
    assert "next-steps" in out


def test_full_mode_is_default_when_flag_omitted(tmp_path: Path) -> None:
    path = tmp_path / "migration-report.html"
    path.write_text(FULL_MINIMAL_PASS, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mode=full" in result.stdout


def test_full_mode_rejects_decision_cta_instead_of_next_steps(tmp_path: Path) -> None:
    """A full-mode report must not carry the pre-execution decision-cta."""
    html = FULL_MINIMAL_PASS.replace(
        '<section id="next-steps"><h2>Next steps</h2></section>',
        '<section id="decision-cta"><h2>Ready to execute?</h2></section>',
    )
    path = tmp_path / "migration-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="full")
    assert code == 1, out
    assert "next-steps" in out  # still missing
    assert "decision-cta" in out  # and the wrong-mode section is present


def test_missing_draft_for_review_fails(tmp_path: Path) -> None:
    html = FULL_MINIMAL_PASS.replace("draft for review", "")
    path = tmp_path / "migration-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="full")
    assert code == 1, out
    assert "draft for review" in out


def test_scenarios_index_requires_what_if_section(tmp_path: Path) -> None:
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "index.json").write_text(
        '{"scenarios": [{"id": "scenario-001"}, {"id": "scenario-002"}]}',
        encoding="utf-8",
    )
    path = tmp_path / "migration-report.html"
    path.write_text(FULL_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="full", migration_dir=tmp_path)
    assert code == 1, out
    assert "what-if-scenarios" in out


def test_scenarios_index_with_what_if_section_passes(tmp_path: Path) -> None:
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "index.json").write_text(
        '{"scenarios": [{"id": "scenario-001"}, {"id": "scenario-002"}]}',
        encoding="utf-8",
    )
    html = FULL_MINIMAL_PASS.replace(
        '<section id="exec-costs"><h2>Costs</h2></section>',
        '<section id="exec-costs"><h2>Costs</h2></section>'
        '<section id="what-if-scenarios"><h2>Scenarios</h2></section>',
    )
    path = tmp_path / "migration-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="full", migration_dir=tmp_path)
    assert code == 0, out
    assert "what-if-scenarios" in out  # reported as optional=... present


# --- decision mode (new: P2-A) ---


def test_decision_minimal_passes(tmp_path: Path) -> None:
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision")
    assert code == 0, out
    assert "REPORT_OK" in out
    assert "mode=decision" in out


def test_decision_missing_cta_fails(tmp_path: Path) -> None:
    html = DECISION_MINIMAL_PASS.replace(
        '<section id="decision-cta"><h2>Ready to execute?</h2></section>', ""
    )
    path = tmp_path / "decision-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="decision")
    assert code == 1, out
    assert "decision-cta" in out


def test_decision_mode_rejects_next_steps_instead_of_cta(tmp_path: Path) -> None:
    """A decision-report.html must not carry next-steps — that implies
    MIGRATION_GUIDE.md / terraform/ already exist, which they don't yet."""
    html = DECISION_MINIMAL_PASS.replace(
        '<section id="decision-cta"><h2>Ready to execute?</h2></section>',
        '<section id="next-steps"><h2>Next steps</h2></section>',
    )
    path = tmp_path / "decision-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="decision")
    assert code == 1, out
    assert "decision-cta" in out  # still missing
    assert "next-steps" in out  # and the wrong-mode section is present


def test_decision_mode_rejects_completed_generate_phase(tmp_path: Path) -> None:
    # The real pre-execution invariant: THIS decide-complete cycle must not
    # have already gone through Generate. Signaled by .phase-status.json's
    # phases.generate, not by raw file presence on disk (see the sibling
    # test below — stale files from a PRIOR cycle may legitimately remain).
    (tmp_path / ".phase-status.json").write_text(
        json.dumps({"phases": {"generate": "completed"}}), encoding="utf-8"
    )
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "phases.generate" in out


def test_decision_mode_rejects_in_progress_generate_phase(tmp_path: Path) -> None:
    (tmp_path / ".phase-status.json").write_text(
        json.dumps({"phases": {"generate": "in_progress"}}), encoding="utf-8"
    )
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "phases.generate" in out


def test_decision_mode_tolerates_stale_terraform_dir_when_generate_pending(
    tmp_path: Path,
) -> None:
    # Regression: a workshop reprice on a PREVIOUSLY-executed run resets
    # phases.generate to "pending" but does not (and must not) delete the
    # previous execution pack, since terraform/ may hold customer edits
    # (baseline.tf/variables.tf) or hand-authored terraform.tfvars/state that
    # cannot be safely deleted. A stale terraform/ directory coexisting with
    # phases.generate == "pending" is the expected, supported post-reprice
    # state and must PASS, not fail on raw directory presence.
    (tmp_path / ".phase-status.json").write_text(
        json.dumps({"phases": {"generate": "pending"}}), encoding="utf-8"
    )
    (tmp_path / "terraform").mkdir()
    (tmp_path / "terraform" / "terraform.tfvars").write_text(
        "operations_email = \"ops@example.com\"", encoding="utf-8"
    )
    (tmp_path / "generation-warnings.json").write_text("{}", encoding="utf-8")
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 0, out


def test_decision_mode_without_phase_status_file_skips_generate_check(
    tmp_path: Path,
) -> None:
    # Fail open on a missing .phase-status.json: an ambiguous case (no state
    # file at all) must not block a genuinely fresh decision run.
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 0, out


def test_decision_mode_rejects_truncated_phase_status_json(tmp_path: Path) -> None:
    # Regression: a .phase-status.json that EXISTS but fails to parse (e.g.
    # truncated mid-write) was previously treated the same as a MISSING file
    # (fail open) — but INTERPRETER.md's State-file validation contract is
    # explicit that invalid JSON is a STOP condition, not something to guess
    # past. An unreadable state file must never be treated as evidence the
    # current cycle is pre-execution.
    (tmp_path / ".phase-status.json").write_text(
        '{"phases":{"generate":"completed"', encoding="utf-8"
    )
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "corrupted" in out.lower()


def test_decision_mode_rejects_empty_phase_status_json(tmp_path: Path) -> None:
    # Same corruption class, different shape: an existing but entirely empty
    # state file must also fail rather than silently defaulting to "no
    # phases at all" (which would fail open incorrectly).
    (tmp_path / ".phase-status.json").write_text("", encoding="utf-8")
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "corrupted" in out.lower()


def test_decision_mode_without_migration_dir_skips_disk_checks(tmp_path: Path) -> None:
    """Unit-testing HTML in isolation (no --migration-dir) must not fail on
    the terraform/generation-*.json checks — those require a real run dir."""
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision")
    assert code == 0, out


def test_decision_mode_with_decision_basis_reports_optional(tmp_path: Path) -> None:
    html = DECISION_MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2></section>',
        '<section id="decision-summary"><h2>Decision</h2></section>'
        '<section id="decision-basis"><h2>What This Assessment Rests On</h2></section>',
    )
    path = tmp_path / "decision-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="decision")
    assert code == 0, out
    assert "decision-basis" in out


def test_decision_basis_required_when_estimate_declares_it(tmp_path: Path) -> None:
    """Regression: estimation-infra.json declares recommendation.decision_basis
    but the report omits <section id="decision-basis"> — must fail, not
    silently REPORT_OK. Only checked when --migration-dir is supplied (the
    validator reads estimation-infra.json from there)."""
    (tmp_path / "estimation-infra.json").write_text(
        '{"recommendation": {"decision_basis": {"measured": ["x"], "assumed": [], "unknown": []}}}',
        encoding="utf-8",
    )
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")  # no decision-basis section
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "decision-basis" in out
    assert "decision_basis" in out


def test_decision_basis_not_required_when_estimate_omits_it(tmp_path: Path) -> None:
    """Control: no decision_basis in estimation-infra.json → the report's
    absence of <section id="decision-basis"> is fine (pre-extension artifacts)."""
    (tmp_path / "estimation-infra.json").write_text(
        '{"recommendation": {"outcome": "go"}}', encoding="utf-8"
    )
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 0, out


def test_decision_basis_present_and_required_passes(tmp_path: Path) -> None:
    """Control: decision_basis declared AND the section is rendered → passes."""
    (tmp_path / "estimation-infra.json").write_text(
        '{"recommendation": {"decision_basis": {"measured": ["x"], "assumed": [], "unknown": []}}}',
        encoding="utf-8",
    )
    html = DECISION_MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2></section>',
        '<section id="decision-summary"><h2>Decision</h2></section>'
        '<section id="decision-basis"><h2>What This Assessment Rests On</h2></section>',
    )
    path = tmp_path / "decision-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 0, out


def test_decision_basis_shipped_skeleton_placeholder_comment_does_not_satisfy_requirement(
    tmp_path: Path,
) -> None:
    """Regression: _section_counts previously matched a <section id="..."> tag
    via a raw-source regex, so the exact unexpanded skeleton placeholder from
    generate-report.md — `<!-- <section id="decision-basis"> when
    recommendation.decision_basis exists -->` — was counted as a real section
    even though it never renders anything. A report that never actually filled
    in the template (declared decision_basis, but shipped the comment
    verbatim) must FAIL, not silently report decision-basis as present."""
    (tmp_path / "estimation-infra.json").write_text(
        '{"recommendation": {"decision_basis": {"measured": ["x"], "assumed": [], "unknown": []}}}',
        encoding="utf-8",
    )
    html = DECISION_MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2></section>',
        '<section id="decision-summary"><h2>Decision</h2></section>'
        "<!-- <section id=\"decision-basis\"> when recommendation.decision_basis exists -->",
    )
    path = tmp_path / "decision-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "decision-basis" in out
    assert "decision_basis" in out


def test_missing_file_fails_cleanly() -> None:
    code, out = run_validator(Path("/nonexistent/decision-report.html"), mode="decision")
    assert code == 1, out
    assert "not_found" in out
