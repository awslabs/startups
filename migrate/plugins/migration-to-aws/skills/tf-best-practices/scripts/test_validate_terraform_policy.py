"""Tests for validate-terraform-policy.py (tf-best-practices, read-only verdict)."""

from __future__ import annotations

import json
import subprocess  # nosec B404 — test-only, inputs are hardcoded literals
import sys
import tempfile
from pathlib import Path

PLUGIN_SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_SKILL_ROOT / "scripts" / "validate-terraform-policy.py"
FIXTURES = PLUGIN_SKILL_ROOT / "fixtures" / "terraform-policy"
GOOD_FIXTURE = FIXTURES / "good-https-redirect"
BAD_HTTP_FORWARD = FIXTURES / "bad-http-forward"
INTERNAL_ALB = FIXTURES / "internal-alb-only"
BAD_RDS_PUBLIC_UNENCRYPTED = FIXTURES / "bad-rds-public-unencrypted"
GOOD_RDS_PRIVATE_ENCRYPTED = FIXTURES / "good-rds-private-encrypted"
BAD_DB_SG_PUBLIC = FIXTURES / "bad-db-sg-public"
GOOD_DB_SG_SCOPED = FIXTURES / "good-db-sg-scoped"
BAD_WILDCARD_IAM = FIXTURES / "bad-wildcard-iam"
GOOD_SCOPED_IAM = FIXTURES / "good-scoped-iam"
BAD_WILDCARD_IAM_LISTFORM = FIXTURES / "bad-wildcard-iam-listform"
GOOD_IAM_SCOPED_LIST = FIXTURES / "good-iam-scoped-list"
GOOD_INTERNET_NLB = FIXTURES / "good-internet-nlb"
BAD_SG_PUBLIC_SSH = FIXTURES / "bad-sg-public-ssh"
GOOD_SG_PUBLIC_WEBAPP = FIXTURES / "good-sg-public-webapp"
BAD_SG_PUBLIC_IPV6 = FIXTURES / "bad-sg-public-ipv6"
GOOD_SG_IPV6_SCOPED = FIXTURES / "good-sg-ipv6-scoped"
BAD_ELASTICACHE_UNENCRYPTED = FIXTURES / "bad-elasticache-unencrypted"
GOOD_ELASTICACHE_ENCRYPTED = FIXTURES / "good-elasticache-encrypted"


def run_policy_validator(terraform_dir: Path, json_out: Path | None = None) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPT), str(terraform_dir)]
    if json_out is not None:
        cmd += ["--json", str(json_out)]
    result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603
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


def test_rds_public_and_unencrypted_fails() -> None:
    code, out = run_policy_validator(BAD_RDS_PUBLIC_UNENCRYPTED)
    assert code == 1, out
    assert "POLICY_FAIL" in out


def test_rds_public_unencrypted_reports_both_rules() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "verdict.json"
        run_policy_validator(BAD_RDS_PUBLIC_UNENCRYPTED, json_out=out_path)
        rules = {v["rule"] for v in json.loads(out_path.read_text())["violations"]}
        assert "rds_not_public" in rules
        assert "rds_encryption_at_rest" in rules


def test_rds_private_encrypted_passes() -> None:
    # Also proves variable-driven storage_encrypted fails open (not flagged).
    code, out = run_policy_validator(GOOD_RDS_PRIVATE_ENCRYPTED)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_db_sg_public_ingress_fails() -> None:
    code, out = run_policy_validator(BAD_DB_SG_PUBLIC)
    assert code == 1, out
    assert "db_sg_no_public_ingress" in out


def test_db_sg_scoped_passes() -> None:
    # Proves: app-SG-scoped DB ingress OK; public 443 not flagged as a DB port;
    # separate aws_vpc_security_group_ingress_rule fails open (not correlated).
    code, out = run_policy_validator(GOOD_DB_SG_SCOPED)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_wildcard_iam_fails() -> None:
    code, out = run_policy_validator(BAD_WILDCARD_IAM)
    assert code == 1, out
    assert "no_wildcard_iam" in out


def test_scoped_iam_passes() -> None:
    # Proves scoped policy OK and assume-role trust policy is not a wildcard hit.
    code, out = run_policy_validator(GOOD_SCOPED_IAM)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_wildcard_iam_listform_fails() -> None:
    # Regression: Resource = ["*"] (single-element list) must fail, like "*".
    code, out = run_policy_validator(BAD_WILDCARD_IAM_LISTFORM)
    assert code == 1, out
    assert "no_wildcard_iam" in out


def test_iam_scoped_list_passes() -> None:
    # A list of scoped actions / resource ARNs is not a wildcard — must pass.
    code, out = run_policy_validator(GOOD_IAM_SCOPED_LIST)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_internet_facing_nlb_not_flagged() -> None:
    # Regression: an internet-facing Network LB (L4) has no HTTPS:443 listener
    # by design and must NOT trip the ALB HTTPS rule.
    code, out = run_policy_validator(GOOD_INTERNET_NLB)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_sg_public_admin_ingress_fails() -> None:
    code, out = run_policy_validator(BAD_SG_PUBLIC_SSH)
    assert code == 1, out
    assert "sg_no_public_admin_ingress" in out


def test_sg_public_admin_ingress_reports_ssh_and_redis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "verdict.json"
        run_policy_validator(BAD_SG_PUBLIC_SSH, json_out=out_path)
        summaries = " ".join(
            v["summary"] for v in json.loads(out_path.read_text())["violations"]
        )
        assert "22 (SSH)" in summaries
        assert "6379 (Redis)" in summaries


def test_sg_public_webapp_passes() -> None:
    # Public web ports (80/443), a high game-port range, and a privately-scoped
    # SSH rule must all pass — no false positive from the sensitive-port rule.
    code, out = run_policy_validator(GOOD_SG_PUBLIC_WEBAPP)
    assert code == 0, out
    assert "POLICY_OK" in out


def test_sg_public_ipv6_ingress_fails() -> None:
    """Regression: ipv6_cidr_blocks = ["::/0"] is public exposure and must fail.

    The old checker searched r'cidr_blocks\\s*=\\s*\\[' which also matches the tail
    of `ipv6_cidr_blocks`, and never looked for ::/0 at all — so an SG opening
    SSH/Postgres to the entire IPv6 internet was reported POLICY_OK.
    """
    code, out = run_policy_validator(BAD_SG_PUBLIC_IPV6)
    assert code == 1, out
    assert "sg_no_public_admin_ingress" in out
    assert "db_sg_no_public_ingress" in out


def test_sg_public_ipv6_ingress_names_the_ipv6_cidr() -> None:
    # The report must say ::/0, not 0.0.0.0/0 — the IPv4 list here is benign.
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "verdict.json"
        run_policy_validator(BAD_SG_PUBLIC_IPV6, json_out=out_path)
        summaries = " ".join(
            v["summary"] for v in json.loads(out_path.read_text())["violations"]
        )
        assert "::/0" in summaries
        assert "22 (SSH)" in summaries
        assert "0.0.0.0/0" not in summaries


def test_ipv4_public_ingress_caught_when_ipv6_list_declared_first() -> None:
    """Regression: the pre-fix regex made the IPv4 check ORDER-DEPENDENT.

    r'cidr_blocks\\s*=\\s*\\[' matched the tail of `ipv6_cidr_blocks`, so when the
    IPv6 attribute came first the checker read the IPv6 list and never looked at
    cidr_blocks at all. A plain `0.0.0.0/0` on port 22 — the exact case this rule
    exists to catch, with no IPv6 exposure involved — silently returned
    POLICY_OK. Flipping the two lines was enough to make it fail correctly.
    """
    sg = """
resource "aws_security_group" "ipv4_ssh_open" {
  name   = "test-sg"
  vpc_id = "vpc-123"

  ingress {
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    %s
  }
}
"""
    ipv6_first = 'ipv6_cidr_blocks = ["2001:db8:1234::/48"]\n    cidr_blocks      = ["0.0.0.0/0"]'
    ipv4_first = 'cidr_blocks      = ["0.0.0.0/0"]\n    ipv6_cidr_blocks = ["2001:db8:1234::/48"]'
    for label, attrs in (("ipv6-first", ipv6_first), ("ipv4-first", ipv4_first)):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "vpc.tf").write_text(sg % attrs, encoding="utf-8")
            code, out = run_policy_validator(Path(tmp))
            assert code == 1, f"{label}: 0.0.0.0/0 on SSH must fail, got: {out}"
            assert "22 (SSH)" in out, f"{label}: {out}"
            assert "0.0.0.0/0" in out, f"{label}: must name the IPv4 range, got: {out}"


def test_sg_ipv6_scoped_passes() -> None:
    # Public web over ::/0 is fine; SSH/Postgres over a scoped IPv6 prefix must
    # not fire. Guards against over-matching any ipv6_cidr_blocks value.
    code, out = run_policy_validator(GOOD_SG_IPV6_SCOPED)
    assert code == 0, out
    assert "POLICY_OK" in out


def _sg_fixture(attrs: str, port: int = 22) -> str:
    return f"""
resource "aws_security_group" "under_test" {{
  name   = "sg"
  vpc_id = "vpc-123"

  ingress {{
    from_port = {port}
    to_port   = {port}
    protocol  = "tcp"
    {attrs}
  }}
}}
"""


def _verdict(tf_body: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "vpc.tf").write_text(tf_body, encoding="utf-8")
        return run_policy_validator(Path(tmp))


def test_cidr_attribute_sharing_line_with_opening_brace_is_read() -> None:
    """Regression: a line-anchored pattern alone hides an attribute that shares
    its block's opening line, which is valid HCL:

        ingress { cidr_blocks = ["0.0.0.0/0"]

    An earlier revision of this fix used a bare `^\\s*` anchor and traded the
    ipv6 tail-match bug for this false negative (main: POLICY_FAIL -> POLICY_OK).
    The `(?:^|\\{)` alternation keeps both properties.
    """
    body = """
resource "aws_security_group" "brace_same_line" {
  name   = "sg"
  vpc_id = "vpc-123"

  ingress { cidr_blocks = ["0.0.0.0/0"]
    from_port = 22
    to_port   = 22
    protocol  = "tcp"
  }
}
"""
    code, out = _verdict(body)
    assert code == 1, f"0.0.0.0/0 on the brace line must fail, got: {out}"
    assert "22 (SSH)" in out, out


def test_noncanonical_ipv6_zero_prefix_spellings_fire() -> None:
    """`::/0` has many legal spellings and Terraform normalises none of them, so
    the check canonicalises via ipaddress rather than substring-matching text."""
    for spelling in ("::/0", "::0/0", "0:0:0:0:0:0:0:0/0", "0000:0000:0000:0000:0000:0000:0000:0000/0"):
        code, out = _verdict(_sg_fixture(f'ipv6_cidr_blocks = ["{spelling}"]'))
        assert code == 1, f"{spelling} is the whole IPv6 internet, must fail: {out}"
        assert "sg_no_public_admin_ingress" in out, f"{spelling}: {out}"


def test_scoped_and_nonliteral_cidrs_still_fail_open() -> None:
    """The canonicalising check must not widen what counts as public: scoped
    prefixes and non-literal values stay unflagged (documented fail-open)."""
    for spelling in ("10.0.0.0/8", "2001:db8:1234::/48", "0.0.0.0/1", "128.0.0.0/1"):
        attr = "ipv6_cidr_blocks" if ":" in spelling else "cidr_blocks"
        code, out = _verdict(_sg_fixture(f'{attr} = ["{spelling}"]'))
        assert code == 0, f"{spelling} is not the whole internet, must pass: {out}"
    for nonliteral in ("var.admin_cidrs", "[var.cidr]", "local.allowed"):
        inner = nonliteral if nonliteral.startswith("[") else f"[{nonliteral}]"
        code, out = _verdict(_sg_fixture(f"cidr_blocks = {inner}"))
        assert code == 0, f"non-literal {nonliteral} must fail open: {out}"


def test_cidr_named_only_in_a_comment_is_not_an_allowed_range() -> None:
    """False positive: a correctly-scoped SG that merely MENTIONS 0.0.0.0/0 in a
    comment inside the list was reported POLICY_FAIL, blocking a valid migration.

    Also pins the opposite direction — stripping comments must not swallow a real
    entry that follows one, which a naive split-on-comma would have done.
    """
    scoped_with_comment = """
    cidr_blocks = [
      # TODO: was 0.0.0.0/0
      "10.0.0.0/8",
    ]"""
    code, out = _verdict(_sg_fixture(scoped_with_comment, port=3389))
    assert code == 0, f"a commented CIDR is not an allowed range: {out}"

    comment_then_real = """
    cidr_blocks = [
      # temporary, remove before prod
      "0.0.0.0/0",
    ]"""
    code, out = _verdict(_sg_fixture(comment_then_real, port=3389))
    assert code == 1, f"a real 0.0.0.0/0 after a comment must still fire: {out}"
    assert "3389 (RDP)" in out, out


def test_commented_out_cidr_attribute_is_not_read() -> None:
    # A commented-out attribute must not be read as set; the live value here is
    # an SG reference, so this SG is correctly scoped and must pass.
    body = _sg_fixture('# cidr_blocks = ["0.0.0.0/0"]\n    security_groups = ["sg-abc123"]')
    code, out = _verdict(body)
    assert code == 0, f"commented-out cidr_blocks must not fire: {out}"


def test_elasticache_unencrypted_fails() -> None:
    code, out = run_policy_validator(BAD_ELASTICACHE_UNENCRYPTED)
    assert code == 1, out
    assert "elasticache_encryption_at_rest" in out


def test_elasticache_encrypted_passes() -> None:
    # Encrypted RG passes; variable-driven RG fails open (not flagged).
    code, out = run_policy_validator(GOOD_ELASTICACHE_ENCRYPTED)
    assert code == 0, out
    assert "POLICY_OK" in out


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
  # Placeholder — the checker only tests for the presence of `certificate_arn`,
  # not its value (see has_certificate_arn). A literal ACM ARN here trips secret
  # scanners for no benefit, so use a variable reference.
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
