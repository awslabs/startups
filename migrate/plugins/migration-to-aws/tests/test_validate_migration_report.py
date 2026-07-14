"""Tests for migration-report.html post-write validation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "validate-migration-report.py"
FIXTURE = PLUGIN_ROOT / "fixtures" / "migration-report-reference.html"
FIXTURE_EST_INFRA = PLUGIN_ROOT / "fixtures" / "estimation-infra-reference.json"
FIXTURE_EST_AI = PLUGIN_ROOT / "fixtures" / "estimation-ai-reference.json"
STUB_FIXTURE = PLUGIN_ROOT / "fixtures" / "migration-report-stub.html"

MINIMAL_PASS = """<!DOCTYPE html>
<html><body>
<section id="decision-summary"><h2>Decision</h2></section>
<section id="exec-services"><h2>Services</h2><table><tbody><tr><td>a</td></tr></tbody></table></section>
<section id="exec-costs"><h2>Costs</h2></section>
<section id="exec-timeline"><h2>Timeline</h2></section>
<section id="exec-risks"><h2>Risks</h2></section>
<section id="appendix-services"><h2>A</h2><table><tbody><tr><td>x</td></tr><tr><td>y</td></tr></tbody></table></section>
<section id="appendix-costs"><h2>B</h2><table><tbody><tr><td>1</td></tr><tr><td>2</td></tr><tr><td>GuardDuty $13</td></tr></tbody></table></section>
<section id="appendix-steps"><h2>C</h2><table><tbody><tr><td>p1</td></tr><tr><td>p2</td></tr></tbody></table></section>
<section id="appendix-artifacts"><h2>E</h2></section>
<footer>draft for review</footer>
</body></html>
"""

STUB_FAIL = """<!DOCTYPE html>
<html><body>
<section id="decision-summary"></section>
<section id="exec-services"></section>
<section id="exec-costs"></section>
<section id="exec-timeline"></section>
<section id="exec-risks"></section>
<section id="appendix-services"><p>See aws-design.json</p></section>
<section id="appendix-costs"><p>Full artifacts: <code>estimation-infra.json</code></p></section>
<section id="appendix-steps"></section>
<section id="appendix-artifacts"></section>
<footer>draft for review</footer>
</body></html>
"""


def run_validator(
    html_path: Path,
    estimation_infra: Path | None = None,
    estimation_ai: Path | None = None,
    *,
    require_toc: bool = True,
    readability: bool = True,
    migration_dir: Path | None = None,
) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPT), str(html_path)]
    if estimation_infra:
        cmd.extend(["--estimation-infra", str(estimation_infra)])
    if estimation_ai:
        cmd.extend(["--estimation-ai", str(estimation_ai)])
    if migration_dir:
        cmd.extend(["--migration-dir", str(migration_dir)])
    if not require_toc:
        cmd.append("--no-require-toc")
    if not readability:
        cmd.append("--no-readability")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_reference_fixture_passes() -> None:
    assert FIXTURE.is_file(), "reference fixture missing"
    assert FIXTURE_EST_INFRA.is_file(), "estimation-infra reference fixture missing"
    assert FIXTURE_EST_AI.is_file(), "estimation-ai reference fixture missing"
    code, out = run_validator(FIXTURE, FIXTURE_EST_INFRA, FIXTURE_EST_AI)
    assert code == 0, out
    assert "REPORT_OK" in out
    assert "structure=complete" in out


def test_minimal_html_passes_without_toc(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 0, out


def test_stub_appendix_fails(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(STUB_FAIL, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "REPORT_FAIL" in out


def test_missing_required_section_fails(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace('<section id="exec-risks">', "")
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "exec-risks" in out


def test_duplicate_section_fails(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="exec-costs">',
        '<section id="exec-costs"><section id="exec-costs">',
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "duplicate" in out.lower()


def test_todo_rejected(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        "<footer>draft for review</footer>",
        "<p>TODO fix costs</p><footer>draft for review</footer>",
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "TODO" in out


def test_broken_toc_fails(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        "<body>",
        '<body><nav class="toc"><a href="#wrong-id">Bad</a></nav>',
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path)
    assert code == 1, out
    assert "broken link" in out.lower() or "missing link" in out.lower()


def test_security_baseline_accepts_dollar_component_without_label(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace("GuardDuty $13", "CloudTrail S3 $1.50")
    html = html.replace(
        "</body>",
        '<section id="exec-security-teaser"><h2>Security Posture</h2></section></body>',
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    est = tmp_path / "estimation-infra.json"
    est.write_text(
        json.dumps(
            {
                "projected_costs": {
                    "aws_monthly_balanced": 112,
                    "breakdown": {
                        "security_baseline": {
                            "mid": 15,
                            "components": {"guardduty": 13, "cloudtrail_s3": 1.5},
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    code, out = run_validator(path, est, require_toc=False)
    assert code == 0, out


def test_security_baseline_rejects_css_false_positive(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace("GuardDuty $13", "compute only")
    html = html.replace("<html>", '<html><style>body{font-size:15px;line-height:1.55}</style>', 1)
    html = html.replace(
        "</body>",
        '<section id="exec-security-teaser"><h2>Security Posture</h2></section></body>',
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    est = tmp_path / "estimation-infra.json"
    est.write_text(
        json.dumps(
            {
                "projected_costs": {
                    "aws_monthly_balanced": 112,
                    "breakdown": {"security_baseline": {"mid": 15, "components": {"guardduty": 13}}},
                }
            }
        ),
        encoding="utf-8",
    )
    code, out = run_validator(path, est, require_toc=False)
    assert code == 1, out
    assert "GuardDuty" in out or "security baseline" in out.lower()


def test_exec_tco_required_when_both_estimates(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        "</body>",
        '<section id="appendix-ai"><h2>AI</h2></section></body>',
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    est_infra = tmp_path / "estimation-infra.json"
    est_ai = tmp_path / "estimation-ai.json"
    est_infra.write_text('{"projected_costs": {"aws_monthly_balanced": 100}}', encoding="utf-8")
    est_ai.write_text('{"cost_comparison": {"projected_bedrock_monthly": 50}}', encoding="utf-8")
    code, out = run_validator(path, est_infra, est_ai, require_toc=False)
    assert code == 1, out
    assert "exec-tco" in out


def test_ai_only_does_not_require_exec_tco(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(
        MINIMAL_PASS.replace(
            "</body>",
            '<section id="appendix-ai"><h2>AI</h2></section></body>',
            1,
        ),
        encoding="utf-8",
    )
    est_ai = tmp_path / "estimation-ai.json"
    est_ai.write_text("{}", encoding="utf-8")
    code, out = run_validator(path, estimation_ai=est_ai, require_toc=False)
    assert code == 0, out


# --- Readability checks (Rubric: / numbered headings) ---


def test_rubric_trace_rejected(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="appendix-services"><h2>A</h2>',
        '<section id="appendix-services"><h2>A</h2><p>Rubric: Eliminators PASS</p>',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "Rubric" in out


def test_section_zero_heading_rejected(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2>',
        '<section id="decision-summary"><h2>Section 0 — Decision</h2>',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "Section 0" in out or "numbered" in out.lower()


def test_numbered_section_heading_rejected(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="exec-services"><h2>Services</h2>',
        '<section id="exec-services"><h2>Section 1b — Services</h2>',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "numbered" in out.lower() or "Section" in out


def test_readability_can_be_disabled(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2>',
        '<section id="decision-summary"><h2>Section 0 — Decision</h2><p>Rubric: x</p>',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False, readability=False)
    assert code == 0, out


def test_rubric_css_class_does_not_false_positive(tmp_path: Path) -> None:
    """A `.rubric` CSS selector in <style> must not trip the readability check."""
    html = MINIMAL_PASS.replace(
        "<html>",
        "<html><style>.rubric { color: #656d76; } /* Section 0 layout */</style>",
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 0, out


# --- #2 security teaser required when baseline exists ---


def _infra_with_baseline(tmp_path: Path) -> Path:
    est = tmp_path / "estimation-infra.json"
    est.write_text(
        json.dumps(
            {
                "projected_costs": {
                    "aws_monthly_balanced": 112,
                    "breakdown": {"security_baseline": {"mid": 15, "components": {"guardduty": 13}}},
                }
            }
        ),
        encoding="utf-8",
    )
    return est


def test_security_teaser_required_when_baseline(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(MINIMAL_PASS, encoding="utf-8")  # GuardDuty present, but no teaser section
    code, out = run_validator(path, _infra_with_baseline(tmp_path), require_toc=False)
    assert code == 1, out
    assert "exec-security-teaser" in out


def test_security_teaser_present_passes(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        "</body>",
        '<section id="exec-security-teaser"><h2>Security Posture</h2>'
        "<p>GuardDuty $13</p></section></body>",
        1,
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, _infra_with_baseline(tmp_path), require_toc=False)
    assert code == 0, out


# --- #3 verdict banner required when recommendation exists ---


def _infra_with_recommendation(tmp_path: Path) -> Path:
    est = tmp_path / "estimation-infra.json"
    est.write_text(
        json.dumps({"recommendation": {"path_label": "migrate_phased"}}),
        encoding="utf-8",
    )
    return est


def test_verdict_required_when_recommendation(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(MINIMAL_PASS, encoding="utf-8")  # decision-summary has no verdict
    code, out = run_validator(path, _infra_with_recommendation(tmp_path), require_toc=False)
    assert code == 1, out
    assert "verdict" in out.lower()


def test_verdict_class_satisfies(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2>',
        '<section id="decision-summary"><h2>Decision</h2>'
        '<div class="verdict">Recommendation: migrate phased</div>',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, _infra_with_recommendation(tmp_path), require_toc=False)
    assert code == 0, out


# --- #4 fixture-bleed canary + self-exemption ---


def test_fixture_bleed_flagged_on_real_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "0612-0900"
    run_dir.mkdir()
    html = MINIMAL_PASS.replace(
        "<footer>", "<p>Migration ID 0611-0606 generated today</p><footer>"
    )
    path = run_dir / "migration-report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False, migration_dir=run_dir)
    assert code == 1, out
    assert "fixture bleed" in out.lower() or "0611-0606" in out


def test_no_migration_dir_exempts_canary(tmp_path: Path) -> None:
    """Validating the fixture itself (no --migration-dir) must not flag its own ID."""
    html = MINIMAL_PASS.replace(
        "<footer>", "<p>Migration ID 0611-0606</p><footer>"
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 0, out


def test_reference_fixture_not_flagged_with_matching_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "0611-0606"
    run_dir.mkdir()
    path = run_dir / "migration-report.html"
    path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    code, out = run_validator(
        path, FIXTURE_EST_INFRA, FIXTURE_EST_AI, migration_dir=run_dir
    )
    assert code == 0, out


# --- #12 committed stub fixture must fail loudly (runs in CI) ---


def test_stub_fixture_fails() -> None:
    assert STUB_FIXTURE.is_file(), "stub regression fixture missing"
    code, out = run_validator(STUB_FIXTURE, FIXTURE_EST_INFRA, FIXTURE_EST_AI)
    assert code == 1, out
    assert "REPORT_FAIL" in out
    # It should trip multiple new gates, not just one.
    assert "Rubric" in out
    assert "Section 0" in out or "numbered" in out.lower()
    assert "exec-security-teaser" in out
    assert "verdict" in out.lower()


# --- exec-flow reader vocabulary (no artifact filenames / resource IDs up top) ---


def test_exec_vocabulary_rejects_json_filename(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="exec-costs"><h2>Costs</h2></section>',
        '<section id="exec-costs"><h2>Costs</h2>'
        "<p>See <code>estimation-infra.json</code> for the breakdown.</p></section>",
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "exec vocabulary" in out.lower()
    assert "estimation-infra.json" in out


def test_exec_vocabulary_rejects_terraform_resource(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="exec-services"><h2>Services</h2>',
        '<section id="exec-services"><h2>Services</h2>'
        "<p>Deployed via <code>aws_guardduty_detector.baseline</code>.</p>",
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "exec vocabulary" in out.lower()
    assert "aws_guardduty_detector.baseline" in out


def test_exec_vocabulary_allows_filename_in_appendix(tmp_path: Path) -> None:
    """Appendices may name artifacts/resources — only the exec flow is gated."""
    html = MINIMAL_PASS.replace(
        "<tr><td>GuardDuty $13</td></tr>",
        "<tr><td>GuardDuty $13</td></tr>"
        "<tr><td>Source: estimation-infra.json (aws_guardduty_detector.baseline)</td></tr>",
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 0, out


def test_exec_vocabulary_can_be_disabled(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="exec-costs"><h2>Costs</h2></section>',
        '<section id="exec-costs"><h2>Costs</h2>'
        "<p>See <code>estimation-infra.json</code>.</p></section>",
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False, readability=False)
    assert code == 0, out


def test_next_steps_must_be_ordered_list(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2></section>',
        '<section id="decision-summary"><h2>Decision</h2>'
        "<h3>Next steps</h3><ul class=\"compact\"><li>Do something</li></ul></section>",
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "Next steps" in out
    assert "<ol>" in out or "ordered" in out.lower()


def test_key_decisions_ahead_must_be_ordered_list(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="decision-summary"><h2>Decision</h2></section>',
        '<section id="decision-summary"><h2>Decision</h2>'
        '<h3>Key decisions ahead</h3><ul><li>Pick a region</li></ul></section>',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "Key decisions ahead" in out


def test_appendix_config_requires_provenance_columns(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="appendix-artifacts">',
        '<section id="appendix-config"><h2>Config</h2>'
        "<table><thead><tr><th>Decision</th><th>Value</th></tr></thead>"
        "<tbody><tr><td>Region</td><td>us-west-2</td></tr></tbody></table></section>"
        '<section id="appendix-artifacts">',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 1, out
    assert "appendix-config" in out
    assert "consequence" in out.lower()


def test_appendix_config_passes_with_full_table(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace(
        '<section id="appendix-artifacts">',
        '<section id="appendix-config"><h2>Config</h2>'
        "<table><thead><tr><th>Question</th><th>Choice</th><th>Source</th>"
        "<th>Design consequence</th></tr></thead>"
        "<tbody><tr><td>Q?</td><td>A</td><td>User</td><td>Impact</td></tr>"
        "<tr><td>Q2?</td><td>B</td><td>Extracted</td><td>Impact 2</td></tr>"
        "</tbody></table></section>"
        '<section id="appendix-artifacts">',
    )
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    code, out = run_validator(path, require_toc=False)
    assert code == 0, out
