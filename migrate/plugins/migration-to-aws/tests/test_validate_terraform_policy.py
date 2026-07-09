"""Tests for validate-terraform-policy.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "validate-terraform-policy.py"
GOOD_FIXTURE = PLUGIN_ROOT / "fixtures" / "terraform-policy" / "good-https-redirect"
BAD_HTTP_FORWARD = PLUGIN_ROOT / "fixtures" / "terraform-policy" / "bad-http-forward"
INTERNAL_ALB = PLUGIN_ROOT / "fixtures" / "terraform-policy" / "internal-alb-only"


def run_policy_validator(terraform_dir: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(terraform_dir)],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def test_good_https_redirect_passes() -> None:
    code, out = run_policy_validator(GOOD_FIXTURE)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_bad_http_forward_fails() -> None:
    code, out = run_policy_validator(BAD_HTTP_FORWARD)
    assert code == 1, out
    assert "POLICY_FAIL" in out
    assert "redirect" in out.lower()


def test_internal_alb_skips_https_requirement() -> None:
    code, out = run_policy_validator(INTERNAL_ALB)
    assert code == 0, out
    assert "POLICY_OK" in out
