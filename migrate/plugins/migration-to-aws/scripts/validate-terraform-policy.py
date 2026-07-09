#!/usr/bin/env python3
"""Static policy checks on generated Terraform (no provider init required).

Currently enforces internet-facing ALB TLS posture:
  - HTTPS listener on port 443 with certificate_arn
  - HTTP port 80 must redirect to HTTPS (never forward)

Usage:
  python3 validate-terraform-policy.py /path/to/terraform

Exit 0 on POLICY_OK, 1 on POLICY_FAIL.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

RESOURCE_OPEN = re.compile(
    r'resource\s+"(?P<type>[a-zA-Z0-9_]+)"\s+"(?P<name>[^"]+)"\s*\{',
    re.MULTILINE,
)


@dataclass(frozen=True)
class PolicyViolation:
    file: str
    resource: str
    summary: str


@dataclass(frozen=True)
class ListenerSpec:
    file: str
    name: str
    port: int | None
    protocol: str | None
    action_type: str | None
    has_certificate_arn: bool


def _read_tf_files(terraform_dir: Path) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for path in sorted(terraform_dir.rglob("*.tf")):
        if path.name.endswith(".tf"):
            files.append((str(path.relative_to(terraform_dir)), path.read_text(encoding="utf-8")))
    return files


def _extract_blocks(content: str, resource_type: str) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    for match in RESOURCE_OPEN.finditer(content):
        if match.group("type") != resource_type:
            continue
        name = match.group("name")
        brace_start = match.end() - 1
        body, _ = _extract_braced_block(content, brace_start)
        blocks.append((resource_type, name, body))
    return blocks


def _extract_braced_block(content: str, open_brace: int) -> tuple[str, int]:
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


def _attr_string(block: str, attr: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(attr)}\s*=\s*"([^"]*)"', block, re.MULTILINE)
    if match:
        return match.group(1)
    bool_match = re.search(
        rf"^\s*{re.escape(attr)}\s*=\s*(true|false)",
        block,
        re.MULTILINE | re.IGNORECASE,
    )
    return bool_match.group(1).lower() if bool_match else None


def _attr_int(block: str, attr: str) -> int | None:
    match = re.search(rf"^\s*{re.escape(attr)}\s*=\s*(\d+)", block, re.MULTILINE)
    return int(match.group(1)) if match else None


def _default_action_type(block: str) -> str | None:
    match = re.search(
        r"default_action\s*\{[^}]*?\btype\s*=\s*\"([^\"]+)\"",
        block,
        re.DOTALL,
    )
    return match.group(1) if match else None


def _has_internet_facing_alb(tf_files: list[tuple[str, str]]) -> bool:
    for _, content in tf_files:
        for _, _, body in _extract_blocks(content, "aws_lb"):
            internal = _attr_string(body, "internal")
            if internal is None or internal.lower() == "false":
                return True
    return False


def _parse_listeners(tf_files: list[tuple[str, str]]) -> list[ListenerSpec]:
    listeners: list[ListenerSpec] = []
    for rel_path, content in tf_files:
        for _, name, body in _extract_blocks(content, "aws_lb_listener"):
            listeners.append(
                ListenerSpec(
                    file=rel_path,
                    name=name,
                    port=_attr_int(body, "port"),
                    protocol=_attr_string(body, "protocol"),
                    action_type=_default_action_type(body),
                    has_certificate_arn="certificate_arn" in body,
                )
            )
    return listeners


def check_alb_https_policy(terraform_dir: Path) -> list[PolicyViolation]:
    tf_files = _read_tf_files(terraform_dir)
    if not tf_files:
        return [
            PolicyViolation(
                file=".",
                resource="terraform/",
                summary="No .tf files found",
            )
        ]

    if not _has_internet_facing_alb(tf_files):
        return []

    listeners = _parse_listeners(tf_files)
    violations: list[PolicyViolation] = []

    https_listeners = [
        listener
        for listener in listeners
        if listener.port == 443
        and (listener.protocol or "").upper() == "HTTPS"
        and listener.has_certificate_arn
        and listener.action_type == "forward"
    ]

    if not https_listeners:
        violations.append(
            PolicyViolation(
                file="compute.tf",
                resource="aws_lb_listener",
                summary=(
                    "Internet-facing ALB requires an HTTPS listener on port 443 "
                    "with certificate_arn and forward action"
                ),
            )
        )

    for listener in listeners:
        if listener.port != 80 or (listener.protocol or "").upper() != "HTTP":
            continue
        if listener.action_type == "forward":
            violations.append(
                PolicyViolation(
                    file=listener.file,
                    resource=f'aws_lb_listener.{listener.name}',
                    summary=(
                        "ALB HTTP listener on port 80 must redirect to HTTPS, "
                        "not forward to targets"
                    ),
                )
            )

    return violations


def validate(terraform_dir: Path) -> tuple[bool, list[PolicyViolation]]:
    violations = check_alb_https_policy(terraform_dir)
    return len(violations) == 0, violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated Terraform policy rules")
    parser.add_argument("terraform_dir", type=Path, help="Path to terraform/ directory")
    args = parser.parse_args()

    terraform_dir = args.terraform_dir.resolve()
    if not terraform_dir.is_dir():
        print(f"POLICY_FAIL | path={terraform_dir} | reason=not_a_directory", file=sys.stderr)
        return 1

    ok, violations = validate(terraform_dir)
    if ok:
        print("POLICY_OK | checks=alb_https")
        return 0

    print("POLICY_FAIL | checks=alb_https", file=sys.stderr)
    for violation in violations:
        print(
            f"POLICY_FAIL | file={violation.file} | resource={violation.resource} | "
            f"reason={violation.summary}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
