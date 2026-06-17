"""Tests for migration-report.html post-write validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "validate-migration-report.py"
FIXTURE = PLUGIN_ROOT / "fixtures" / "migration-report-reference.html"

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


def run_validator(html_path: Path, estimation_infra: Path | None = None) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPT), str(html_path)]
    if estimation_infra:
        cmd.extend(["--estimation-infra", str(estimation_infra)])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def test_reference_fixture_passes() -> None:
    assert FIXTURE.is_file(), "reference fixture missing"
    code, out = run_validator(FIXTURE)
    assert code == 0, out
    assert "REPORT_OK" in out


def test_minimal_html_passes(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(MINIMAL_PASS, encoding="utf-8")
    code, out = run_validator(path)
    assert code == 0, out


def test_stub_appendix_fails(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    path.write_text(STUB_FAIL, encoding="utf-8")
    code, out = run_validator(path)
    assert code == 1, out
    assert "REPORT_FAIL" in out


def test_security_baseline_check(tmp_path: Path) -> None:
    html = MINIMAL_PASS.replace("GuardDuty $13", "compute only")
    path = tmp_path / "report.html"
    path.write_text(html, encoding="utf-8")
    est = tmp_path / "estimation-infra.json"
    est.write_text(
        json.dumps(
            {
                "projected_costs": {
                    "aws_monthly_balanced": 118,
                    "breakdown": {"security_baseline": {"mid": 15, "components": {"guardduty": 13}}},
                }
            }
        ),
        encoding="utf-8",
    )
    code, out = run_validator(path, est)
    assert code == 1, out
    assert "GuardDuty" in out or "security_baseline" in out
