"""Tests for heroku-to-aws migration report validation (--mode full / decision).

Heroku's validator had zero test coverage before this file. Mirrors the
pattern in test_validate_migration_report.py (subprocess-driven, inline HTML
fixtures) rather than importing the validator module directly, since the
script is invoked as a CLI in every skill call site.
"""

from __future__ import annotations

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


def test_decision_mode_rejects_terraform_dir_on_disk(tmp_path: Path) -> None:
    (tmp_path / "terraform").mkdir()
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "terraform" in out.lower()


def test_decision_mode_rejects_generation_artifacts_on_disk(tmp_path: Path) -> None:
    (tmp_path / "generation-infra.json").write_text("{}", encoding="utf-8")
    path = tmp_path / "decision-report.html"
    path.write_text(DECISION_MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, mode="decision", migration_dir=tmp_path)
    assert code == 1, out
    assert "generation-" in out


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


def test_missing_file_fails_cleanly() -> None:
    code, out = run_validator(Path("/nonexistent/decision-report.html"), mode="decision")
    assert code == 1, out
    assert "not_found" in out
