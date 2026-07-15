"""Tests for validate-terraform-policy.py (tf-best-practices, read-only verdict)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_SKILL_ROOT / "scripts" / "validate-terraform-policy.py"
FIXTURES = PLUGIN_SKILL_ROOT / "fixtures" / "terraform-policy"
GOOD_FIXTURE = FIXTURES / "good-https-redirect"
BAD_HTTP_FORWARD = FIXTURES / "bad-http-forward"
INTERNAL_ALB = FIXTURES / "internal-alb-only"


def run_policy_validator(terraform_dir: Path, json_out: Path | None = None) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPT), str(terraform_dir)]
    if json_out is not None:
        cmd += ["--json", str(json_out)]
    result = subprocess.run(cmd, capture_output=True, text=True)
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


def test_json_report_written_on_pass() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "verdict.json"
        code, _ = run_policy_validator(GOOD_FIXTURE, json_out=out_path)
        assert code == 0
        report = json.loads(out_path.read_text())
        assert report["policy_status"] == "POLICY_OK"
        assert report["violations"] == []


def test_json_report_written_on_fail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "verdict.json"
        code, _ = run_policy_validator(BAD_HTTP_FORWARD, json_out=out_path)
        assert code == 1
        report = json.loads(out_path.read_text())
        assert report["policy_status"] == "POLICY_FAIL"
        rules = {v["rule"] for v in report["violations"]}
        assert "alb_http_redirect" in rules


def test_missing_directory_is_usage_error() -> None:
    code, out = run_policy_validator(Path("/nonexistent/terraform/dir"))
    assert code == 2, out
    assert "not_a_directory" in out


def test_no_tf_files_flagged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run_policy_validator(Path(tmp))
        assert code == 1, out
        assert "No .tf files" in out


def test_block_form_forward_https_listener_does_not_false_fail() -> None:
    """Regression: a valid HTTPS listener whose default_action uses a NESTED
    forward { ... } block before `type` must NOT be misparsed as missing/wrong.

    The old r'default_action{[^}]*?type' regex stopped at the first '}' (the end
    of the nested block) and failed to read `type`, producing a false POLICY_FAIL.
    """
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "compute.tf").write_text(
            """
resource "aws_lb" "app" {
  name     = "app-alb"
  internal = false
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    forward {
      target_group {
        arn = aws_lb_target_group.app.arn
      }
    }
    type = "forward"
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
""",
            encoding="utf-8",
        )
        code, out = run_policy_validator(Path(tmp))
        assert code == 0, f"block-form forward should pass, got: {out}"
        assert "POLICY_OK" in out
