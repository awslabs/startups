"""Test suite for scripts/validate-assessment-report.py.

Mirrors the structure of the GCP skill's tests/test_validate_migration_report.py.
Covers: required/conditional section presence, TOC integrity, readability
patterns, exec-vocabulary leaks (Pre-Flight Check IDs / filenames / Terraform
resource IDs / "route disposition"), cost-labeling, decision-traceability
content, verdict banner, action-list ordering, fixture-bleed detection, and
exit-code behavior for all three cases (0/1/other).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "validate-assessment-report.py"
)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

spec = importlib.util.spec_from_file_location("validate_assessment_report", SCRIPT_PATH)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)  # type: ignore[union-attr]


MINIMAL_PASS = """
<!DOCTYPE html><html><body>
<nav class="toc">
  <a href="#exec-verdict">V</a>
  <a href="#what-you-gain">G</a>
  <a href="#what-you-lose">L</a>
  <a href="#coupling-score">C</a>
  <a href="#preflight-findings">P</a>
  <a href="#decision-traceability">D</a>
  <a href="#next-steps">N</a>
</nav>
<section id="exec-verdict"><p class="verdict">Recommendation: Fargate.</p></section>
<section id="what-you-gain"><p>Predictable bills.</p></section>
<section id="what-you-lose"><p>Preview deployments go away.</p></section>
<section id="coupling-score">
  <table><tbody><tr><td>a</td></tr><tr><td>b</td></tr><tr><td>c</td></tr></tbody></table>
</section>
<section id="preflight-findings">
  <table><tbody><tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>
</section>
<section id="decision-traceability"><p>Rule 3 fired because traffic is sustained.</p></section>
<section id="next-steps"><ol><li>Do a thing.</li></ol></section>
<footer><p>This is a draft for review.</p></footer>
</body></html>
"""


class TestRequiredSections:
    def test_all_required_sections_present_passes_that_check(self):
        errors = validator._validate_required_sections(MINIMAL_PASS)
        assert errors == []

    def test_missing_required_section_flagged(self):
        html = MINIMAL_PASS.replace('<section id="next-steps">', '<section id="next-stepz">')
        errors = validator._validate_required_sections(html)
        assert any("next-steps" in e for e in errors)

    def test_duplicate_required_section_flagged(self):
        html = MINIMAL_PASS + '<section id="exec-verdict"><p>dup</p></section>'
        errors = validator._validate_required_sections(html)
        assert any("duplicate" in e and "exec-verdict" in e for e in errors)


class TestConditionalSections:
    def test_tiebreak_requires_exec_tiebreak_section(self):
        rec = {"tiebreak": True}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, rec, None, None)
        assert any("exec-tiebreak" in e for e in errors)

    def test_no_tiebreak_does_not_require_exec_tiebreak(self):
        rec = {"tiebreak": False}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, rec, None, None)
        assert not any("exec-tiebreak" in e for e in errors)

    def test_sub_high_finding_requires_inputs_received_section(self):
        pf = {"checks": [{"id": "U1", "confidence": "LOW"}]}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, None, pf, None)
        assert any("inputs-received" in e for e in errors)

    def test_all_high_findings_does_not_require_inputs_received(self):
        pf = {"checks": [{"id": "M1", "confidence": "HIGH"}]}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, None, pf, None)
        assert not any("inputs-received" in e for e in errors)

    def test_middleware_detected_requires_appendix_m1(self):
        t1 = {"has_middleware": True}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, None, None, t1)
        assert any("appendix-m1" in e for e in errors)

    def test_no_middleware_does_not_require_appendix_m1(self):
        t1 = {"has_middleware": False}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, None, None, t1)
        assert not any("appendix-m1" in e for e in errors)

    def test_outcome_c_requires_out_of_scope_section(self):
        rec = {"outcome": "C"}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, rec, None, None)
        assert any("out-of-scope" in e for e in errors)

    def test_outcome_stay_requires_out_of_scope_section(self):
        rec = {"outcome": "stay"}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, rec, None, None)
        assert any("out-of-scope" in e for e in errors)

    def test_outcome_a_does_not_require_out_of_scope_section(self):
        rec = {"outcome": "A"}
        errors = validator._validate_conditional_sections(MINIMAL_PASS, rec, None, None)
        assert not any("out-of-scope" in e for e in errors)


class TestExecVocabulary:
    def test_preflight_check_id_in_exec_section_flagged(self):
        html = MINIMAL_PASS.replace(
            "Recommendation: Fargate.", "Recommendation: Fargate. M1 fired at HIGH."
        )
        errors = validator._validate_exec_vocabulary(html)
        assert any("M1" in e for e in errors)

    def test_artifact_filename_in_exec_section_flagged(self):
        html = MINIMAL_PASS.replace(
            "Predictable bills.", "Predictable bills. See preflight-findings.json."
        )
        errors = validator._validate_exec_vocabulary(html)
        assert any("preflight-findings.json" in e for e in errors)

    def test_terraform_resource_id_in_exec_section_flagged(self):
        html = MINIMAL_PASS.replace(
            "Predictable bills.", "Predictable bills. See aws_ecs_service.web."
        )
        errors = validator._validate_exec_vocabulary(html)
        assert any("aws_ecs_service.web" in e for e in errors)

    def test_route_disposition_in_exec_section_flagged(self):
        html = MINIMAL_PASS.replace(
            "Predictable bills.", "Predictable bills. Route disposition analysis shows X."
        )
        errors = validator._validate_exec_vocabulary(html)
        assert any("route disposition" in e for e in errors)

    def test_check_id_in_appendix_not_flagged(self):
        # Appendix sections (preflight-findings) are exempt from exec vocabulary rules.
        html = MINIMAL_PASS.replace(
            "<tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>\n</section>\n<section id=\"decision-traceability\">",
            "<tr><td>M1 fired</td></tr><tr><td>b</td></tr></tbody></table>\n</section>\n<section id=\"decision-traceability\">",
        )
        errors = validator._validate_exec_vocabulary(html)
        assert errors == []


class TestCostLabeling:
    def test_dollar_amount_without_estimated_monthly_in_prose_flagged(self):
        html = MINIMAL_PASS.replace(
            "Predictable bills.", "Predictable bills. This costs $85 extra."
        )
        errors = validator._validate_cost_labeling(html)
        assert any("$85" in e for e in errors)

    def test_dollar_amount_with_estimated_monthly_nearby_passes(self):
        html = MINIMAL_PASS.replace(
            "Predictable bills.",
            "Predictable bills. This is an estimated monthly cost of $85.",
        )
        errors = validator._validate_cost_labeling(html)
        assert errors == []

    def test_dollar_amount_in_table_cell_without_label_flagged(self):
        html = MINIMAL_PASS.replace(
            "<table><tbody><tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>\n</section>\n<section id=\"decision-traceability\">",
            "<table><tbody><tr><td>a</td></tr><tr><td>$85</td></tr></tbody></table>\n</section>\n<section id=\"decision-traceability\">",
        )
        assert html != MINIMAL_PASS, "replace() target did not match fixture - test setup bug"
        errors = validator._validate_cost_labeling(html)
        assert any("$85" in e for e in errors)

    def test_no_dollar_amounts_passes(self):
        errors = validator._validate_cost_labeling(MINIMAL_PASS)
        assert errors == []

    def test_activate_credit_ceiling_without_estimated_monthly_passes(self):
        html = MINIMAL_PASS.replace(
            "Predictable bills.",
            "Predictable bills. AWS Activate offers up to $5,000 in credits.",
        )
        errors = validator._validate_cost_labeling(html)
        assert errors == []

    def test_credit_ceiling_in_table_cell_without_estimated_monthly_passes(self):
        html = MINIMAL_PASS.replace(
            "<table><tbody><tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>\n</section>\n<section id=\"decision-traceability\">",
            "<table><tbody><tr><td>a</td></tr><tr><td>up to $5,000 in Activate credits</td></tr></tbody></table>\n</section>\n<section id=\"decision-traceability\">",
        )
        assert html != MINIMAL_PASS, "replace() target did not match fixture - test setup bug"
        errors = validator._validate_cost_labeling(html)
        assert errors == []

    def test_unrelated_credit_word_does_not_exempt_a_real_cost_figure(self):
        # The exemption keys on "Activate" specifically, not a bare "credit(s)"
        # match - an unrelated use of "credit" (e.g. "credit card") must NOT
        # exempt a real, unlabeled cost figure from the cost-labeling rule.
        html = MINIMAL_PASS.replace(
            "Predictable bills.",
            "Predictable bills. Your credit card will be charged $85 monthly.",
        )
        errors = validator._validate_cost_labeling(html)
        assert any("$85" in e for e in errors)


class TestDecisionTraceability:
    def test_missing_fired_rule_language_flagged(self):
        html = MINIMAL_PASS.replace(
            '<section id="decision-traceability"><p>Rule 3 fired because traffic is sustained.</p></section>',
            '<section id="decision-traceability"><p>Nothing to see here.</p></section>',
        )
        errors = validator._validate_decision_traceability(html, None)
        assert any("fired" in e.lower() or "rule" in e.lower() for e in errors)

    def test_present_fired_rule_language_passes(self):
        errors = validator._validate_decision_traceability(MINIMAL_PASS, None)
        assert errors == []

    def test_tiebreak_requires_log_drain_language(self):
        rec = {"tiebreak": True}
        errors = validator._validate_decision_traceability(MINIMAL_PASS, rec)
        assert any("log drain" in e.lower() or "resolving" in e.lower() for e in errors)

    def test_tiebreak_with_log_drain_language_passes(self):
        html = MINIMAL_PASS.replace(
            "Rule 3 fired because traffic is sustained.",
            "Rule 3 fired; 14 days of log drain data would resolve this further.",
        )
        rec = {"tiebreak": True}
        errors = validator._validate_decision_traceability(html, rec)
        assert errors == []


class TestActionLists:
    def test_ul_in_next_steps_flagged(self):
        html = MINIMAL_PASS.replace(
            '<section id="next-steps"><ol><li>Do a thing.</li></ol></section>',
            '<section id="next-steps"><ul><li>Do a thing.</li></ul></section>',
        )
        errors = validator._validate_action_lists(html)
        assert any("ol" in e for e in errors)

    def test_ol_in_next_steps_passes(self):
        errors = validator._validate_action_lists(MINIMAL_PASS)
        assert errors == []


class TestFixtureBleed:
    def test_canary_id_in_real_run_flagged(self, tmp_path):
        html = MINIMAL_PASS.replace(
            "</body></html>", f"<p>{validator.FIXTURE_CANARY_ID}</p></body></html>"
        )
        real_dir = tmp_path / "0101-0101"
        real_dir.mkdir()
        errors = validator._validate_fixture_bleed(html, real_dir)
        assert any("fixture bleed" in e for e in errors)

    def test_canary_id_without_migration_dir_not_flagged(self):
        html = MINIMAL_PASS.replace(
            "</body></html>", f"<p>{validator.FIXTURE_CANARY_ID}</p></body></html>"
        )
        errors = validator._validate_fixture_bleed(html, None)
        assert errors == []

    def test_canary_id_matching_its_own_dir_not_flagged(self, tmp_path):
        html = MINIMAL_PASS.replace(
            "</body></html>", f"<p>{validator.FIXTURE_CANARY_ID}</p></body></html>"
        )
        own_dir = tmp_path / validator.FIXTURE_CANARY_ID
        own_dir.mkdir()
        errors = validator._validate_fixture_bleed(html, own_dir)
        assert not any("fixture bleed" in e for e in errors)


class TestReferenceFixture:
    def test_reference_fixture_passes_full_validation(self):
        html = (FIXTURES_DIR / "assessment-report-reference.html").read_text()
        recommendation = validator.json.loads(
            (FIXTURES_DIR / "recommendation-reference.json").read_text()
        )
        preflight_findings = validator.json.loads(
            (FIXTURES_DIR / "preflight-findings-reference.json").read_text()
        )
        tier1_signals = validator.json.loads(
            (FIXTURES_DIR / "tier1-signals-reference.json").read_text()
        )
        errors = validator.validate_report(
            html, recommendation, preflight_findings, tier1_signals
        )
        assert errors == [], f"Reference fixture should pass cleanly, got: {errors}"

    def test_stub_fixture_fails_with_actionable_errors(self):
        html = (FIXTURES_DIR / "assessment-report-stub.html").read_text()
        errors = validator.validate_report(html, require_toc=False)
        assert len(errors) > 0
        # Spot-check a few of the specific failure modes the stub was built to trigger.
        joined = "\n".join(errors)
        assert "decision-traceability" in joined
        assert "TODO" in joined
        assert "$85" in joined


class TestExitCodeContract:
    """The agent must branch on shell exit code, not stdout text alone. These
    tests exercise main() end-to-end via subprocess to confirm the contract."""

    def test_exit_0_on_pass(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(FIXTURES_DIR / "assessment-report-reference.html"),
                "--recommendation",
                str(FIXTURES_DIR / "recommendation-reference.json"),
                "--preflight-findings",
                str(FIXTURES_DIR / "preflight-findings-reference.json"),
                "--tier1-signals",
                str(FIXTURES_DIR / "tier1-signals-reference.json"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "REPORT_OK" in result.stdout

    def test_exit_1_on_fail(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(FIXTURES_DIR / "assessment-report-stub.html"),
                "--no-require-toc",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "REPORT_FAIL" in result.stderr

    def test_exit_1_on_missing_file(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "/tmp/does-not-exist-at-all.html"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "reason=not_found" in result.stderr

    def test_nonzero_non_one_exit_means_did_not_run(self):
        # Simulate "validator did not run" by invoking python with a bad flag
        # the script's own argparse will reject (argparse itself exits 2).
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--this-flag-does-not-exist"],
            capture_output=True,
            text=True,
        )
        assert result.returncode not in (0, 1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
