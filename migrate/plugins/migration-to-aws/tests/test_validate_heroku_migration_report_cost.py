"""P1-C cost-figure cross-check tests for the heroku-to-aws report validator.

Kept in a separate module from the broader heroku report-validator suite so this
change does not collide with the report-blocking PR that adds that suite; the two
can be merged in either order and the cost tests move into the main suite on rebase.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "validate-heroku-migration-report.py"

GOOD = """<!DOCTYPE html>
<html lang="en"><body><div class="report">
<section id="decision-summary"><p class="verdict-headline">Go</p></section>
<section id="exec-costs"><p>Balanced <span data-cost-key="aws_monthly_balanced">$112/mo</span></p></section>
<section id="cost-optimization"><p>No 1-year/3-year commitment product applies.</p></section>
<section id="next-steps"><ol><li>See MIGRATION_GUIDE.md</li></ol></section>
<footer>draft for review</footer>
</div></body></html>
"""


def run(html: str, migration_dir: Path | None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "migration-report.html"
        report.write_text(html, encoding="utf-8")
        cmd = [sys.executable, str(SCRIPT), str(report)]
        if migration_dir is not None:
            cmd += ["--migration-dir", str(migration_dir)]
        result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603
        return result.returncode, result.stdout + result.stderr


def _est_dir(tmp: str, balanced: int) -> Path:
    d = Path(tmp)
    (d / "estimation-infra.json").write_text(
        json.dumps({"projected_costs": {"aws_monthly_balanced": balanced}}),
        encoding="utf-8",
    )
    return d


def test_cost_figure_match_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run(GOOD, migration_dir=_est_dir(tmp, 112))
    assert code == 0, out
    assert "cost figure mismatch" not in out


def test_cost_figure_mismatch_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run(GOOD, migration_dir=_est_dir(tmp, 999))
    assert code == 1, out
    assert "cost figure mismatch" in out
    assert "aws_monthly_balanced" in out


def test_cost_figure_skipped_without_estimation() -> None:
    # No --migration-dir -> no estimation-infra.json -> the cost check is skipped entirely,
    # so the otherwise-valid report passes.
    code, out = run(GOOD, migration_dir=None)
    assert code == 0, out
    assert "cost figure mismatch" not in out
    assert "missing data-cost-key" not in out


def test_missing_required_balanced_anchor_fails() -> None:
    # The core P1-C guarantee: an un-anchored balanced figure must FAIL, not pass —
    # otherwise a wrong un-anchored number reaches the reader unchecked.
    html = GOOD.replace(
        '<span data-cost-key="aws_monthly_balanced">$112/mo</span>',
        "$999/mo",
    )
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run(html, migration_dir=_est_dir(tmp, 112))
    assert code == 1, out
    assert 'missing data-cost-key="aws_monthly_balanced"' in out


def test_nested_markup_reads() -> None:
    html = GOOD.replace(
        '<span data-cost-key="aws_monthly_balanced">$112/mo</span>',
        '<span data-cost-key="aws_monthly_balanced"><strong>$112/mo</strong></span>',
    )
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run(html, migration_dir=_est_dir(tmp, 112))
    assert code == 0, out
    assert "cost figure mismatch" not in out


def test_non_numeric_json_value_fails_not_crash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "estimation-infra.json").write_text(
            json.dumps({"projected_costs": {"aws_monthly_balanced": "$112"}}),
            encoding="utf-8",
        )
        code, out = run(GOOD, migration_dir=d)
    assert code == 1, out
    assert "not a whole-dollar number" in out
