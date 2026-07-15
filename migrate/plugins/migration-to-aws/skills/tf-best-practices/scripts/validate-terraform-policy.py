#!/usr/bin/env python3
"""Static policy checks on generated Terraform (no provider init required).

Read-only VERDICT PRODUCER. This script never edits .tf files and never touches
run state (.phase-status.json). It parses HCL, evaluates policy, and emits a
structured verdict (stdout summary + optional --json report). Remediation and any
phase/state decisions belong to the CALLER (see tf-best-practices SKILL.md).

Currently enforces internet-facing ALB TLS posture:
  - HTTPS listener on port 443 with certificate_arn and a forward action
  - HTTP listener on port 80 must redirect to HTTPS (never forward to targets)

Usage:
  python3 validate-terraform-policy.py /path/to/terraform [--json report.json]

Exit 0 on POLICY_OK, 1 on POLICY_FAIL, 2 on usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

RESOURCE_OPEN = re.compile(
    r'resource\s+"(?P<type>[a-zA-Z0-9_]+)"\s+"(?P<name>[^"]+)"\s*\{',
    re.MULTILINE,
)


@dataclass(frozen=True)
class Violation:
    check: str          # "policy"
    rule: str           # "alb_https_listener" | "alb_http_redirect" | "no_tf_files"
    file: str
    line: int           # 1-based; 0 if unknown
    severity: str       # "error" | "warning"
    summary: str
    fix_hint: str


@dataclass(frozen=True)
class ListenerSpec:
    file: str
    name: str
    line: int
    port: int | None
    protocol: str | None
    action_type: str | None
    has_certificate_arn: bool


def _read_tf_files(terraform_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for path in sorted(terraform_dir.rglob("*.tf")):
        files.append((str(path.relative_to(terraform_dir)), path.read_text(encoding="utf-8")))
    return files


def _extract_braced_block(content: str, open_brace: int) -> tuple[str, int]:
    """Return (block_text_including_braces, index_after_close). Brace-depth aware."""
    depth = 0
    for idx in range(open_brace, len(content)):
        char = content[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[open_brace : idx + 1], idx + 1
    return content[open_brace:], len(content)


def _extract_blocks(content: str, resource_type: str) -> list[tuple[str, str, int]]:
    """Return (name, body, 1-based line) for each resource of resource_type."""
    blocks: list[tuple[str, str, int]] = []
    for match in RESOURCE_OPEN.finditer(content):
        if match.group("type") != resource_type:
            continue
        name = match.group("name")
        brace_start = match.end() - 1
        body, _ = _extract_braced_block(content, brace_start)
        line = content.count("\n", 0, match.start()) + 1
        blocks.append((name, body, line))
    return blocks


def _attr_string(block: str, attr: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(attr)}\s*=\s*"([^"]*)"', block, re.MULTILINE)
    if match:
        return match.group(1)
    bool_match = re.search(
        rf"^\s*{re.escape(attr)}\s*=\s*(true|false)\b",
        block,
        re.MULTILINE | re.IGNORECASE,
    )
    return bool_match.group(1).lower() if bool_match else None


def _attr_int(block: str, attr: str) -> int | None:
    match = re.search(rf"^\s*{re.escape(attr)}\s*=\s*(\d+)", block, re.MULTILINE)
    return int(match.group(1)) if match else None


def _default_action_type(block: str) -> str | None:
    """Extract default_action { ... type = "X" ... } via BRACE-DEPTH matching.

    NOTE: the naive r'default_action\\s*\\{[^}]*?type' approach breaks when the
    default_action contains a nested block (redirect {} / forward {}) placed
    BEFORE the type attribute — it stops at the first '}'. We isolate the full
    default_action body by brace matching, then read `type` from it.
    """
    m = re.search(r"default_action\s*\{", block)
    if not m:
        return None
    body, _ = _extract_braced_block(block, m.end() - 1)
    tmatch = re.search(r'^\s*type\s*=\s*"([^"]+)"', body, re.MULTILINE)
    return tmatch.group(1) if tmatch else None


def _has_internet_facing_alb(tf_files: list[tuple[str, str]]) -> bool:
    """True if any aws_lb is internet-facing (internal absent, false, or non-literal)."""
    for _, content in tf_files:
        if _extract_blocks(content, "aws_lb"):
            for _, body, _line in _extract_blocks(content, "aws_lb"):
                internal = _attr_string(body, "internal")
                # None => absent OR variable-driven (e.g. var.is_internal) => treat as
                # internet-facing (fail-safe: demand HTTPS unless explicitly internal=true).
                if internal is None or internal == "false":
                    return True
    return False


def _parse_listeners(tf_files: list[tuple[str, str]]) -> list[ListenerSpec]:
    listeners: list[ListenerSpec] = []
    for rel_path, content in tf_files:
        for name, body, line in _extract_blocks(content, "aws_lb_listener"):
            listeners.append(
                ListenerSpec(
                    file=rel_path,
                    name=name,
                    line=line,
                    port=_attr_int(body, "port"),
                    protocol=_attr_string(body, "protocol"),
                    action_type=_default_action_type(body),
                    has_certificate_arn="certificate_arn" in body,
                )
            )
    return listeners


def check_alb_https_policy(terraform_dir: Path) -> list[Violation]:
    tf_files = _read_tf_files(terraform_dir)
    if not tf_files:
        return [
            Violation(
                check="policy",
                rule="no_tf_files",
                file=".",
                line=0,
                severity="error",
                summary="No .tf files found in terraform directory",
                fix_hint="Ensure the generate step wrote terraform/ before validation",
            )
        ]

    if not _has_internet_facing_alb(tf_files):
        return []

    listeners = _parse_listeners(tf_files)
    violations: list[Violation] = []

    https_ok = [
        l
        for l in listeners
        if l.port == 443
        and (l.protocol or "").upper() == "HTTPS"
        and l.has_certificate_arn
        and l.action_type == "forward"
    ]

    if not https_ok:
        # Point at an aws_lb file when we can, else the first tf file.
        lb_file = next(
            (rel for rel, c in tf_files if _extract_blocks(c, "aws_lb")),
            tf_files[0][0],
        )
        violations.append(
            Violation(
                check="policy",
                rule="alb_https_listener",
                file=lb_file,
                line=0,
                severity="error",
                summary=(
                    "Internet-facing ALB requires an HTTPS listener on port 443 "
                    "with certificate_arn and a forward action"
                ),
                fix_hint=(
                    'Add an aws_lb_listener on port 443, protocol "HTTPS", with '
                    "ssl_policy, certificate_arn, and a forward default_action"
                ),
            )
        )

    for l in listeners:
        if l.port != 80 or (l.protocol or "").upper() != "HTTP":
            continue
        if l.action_type == "forward":
            violations.append(
                Violation(
                    check="policy",
                    rule="alb_http_redirect",
                    file=l.file,
                    line=l.line,
                    severity="error",
                    summary=(
                        f"ALB HTTP listener '{l.name}' on port 80 forwards to targets; "
                        "it must redirect to HTTPS"
                    ),
                    fix_hint=(
                        "Replace the forward default_action with a redirect block: "
                        'type = "redirect", redirect { port = "443", protocol = "HTTPS", '
                        'status_code = "HTTP_301" }'
                    ),
                )
            )

    return violations


def validate(terraform_dir: Path) -> tuple[bool, list[Violation]]:
    violations = check_alb_https_policy(terraform_dir)
    return len(violations) == 0, violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated Terraform policy rules")
    parser.add_argument("terraform_dir", type=Path, help="Path to terraform/ directory")
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional path to write a machine-readable JSON verdict",
    )
    args = parser.parse_args()

    terraform_dir = args.terraform_dir.resolve()
    if not terraform_dir.is_dir():
        print(f"POLICY_FAIL | path={terraform_dir} | reason=not_a_directory", file=sys.stderr)
        return 2

    ok, violations = validate(terraform_dir)

    if args.json is not None:
        report = {
            "check": "policy",
            "policy_status": "POLICY_OK" if ok else "POLICY_FAIL",
            "violations": [asdict(v) for v in violations],
        }
        try:
            args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"POLICY_FAIL | reason=json_write_failed | detail={exc}", file=sys.stderr)
            return 2

    if ok:
        print("POLICY_OK | checks=alb_https")
        return 0

    print("POLICY_FAIL | checks=alb_https", file=sys.stderr)
    for v in violations:
        print(
            f"POLICY_FAIL | file={v.file} | line={v.line} | rule={v.rule} | reason={v.summary}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
