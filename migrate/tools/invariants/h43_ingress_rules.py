#!/usr/bin/env python3
"""H43: No unrestricted ingress (0.0.0.0/0) except ALB ports 443/80.

Invariant
---------
Generated Terraform security groups must not allow unrestricted inbound traffic
(0.0.0.0/0 CIDR) on any port except:
  - Port 443 (HTTPS) on the ALB security group
  - Port 80 (HTTP → HTTPS redirect) on the ALB security group

All other security groups (Fargate, database, internal) must restrict ingress
to specific source security groups or CIDR ranges — never 0.0.0.0/0.

Note: Route tables with 0.0.0.0/0 (default routes to IGW/NAT) are NOT checked
by this invariant — only ingress blocks in security group resources.

Skill file reference
--------------------
  references/phases/generate/generate-artifacts-infra.md (line 153)
    "No unrestricted ingress except ALB port 443. All other security groups
     must use source security group references."

  references/phases/generate/generate-artifacts-infra.md (lines 145-153)
    Security rules: no hardcoded credentials, no wildcard IAM, no unrestricted
    ingress.

Examples
--------
  PASS: ingress { from_port = 443, to_port = 443, cidr_blocks = ["0.0.0.0/0"] }
        Port 443 is allowed to be open to the internet (ALB HTTPS).

  PASS: ingress { from_port = 80, to_port = 80, cidr_blocks = ["0.0.0.0/0"] }
        Port 80 is allowed for HTTP-to-HTTPS redirect on ALB.

  FAIL: ingress { from_port = 5432, to_port = 5432, cidr_blocks = ["0.0.0.0/0"] }
        Database port open to internet — critical security violation.

  FAIL: ingress { from_port = 0, to_port = 65535, cidr_blocks = ["0.0.0.0/0"] }
        All ports open to internet — critical security violation.

  PASS: No terraform/ directory exists — nothing to check, passes trivially.
"""

import json
import re
import sys
from pathlib import Path


def main():
    migration_dir = Path(sys.argv[1])
    tf_dir = migration_dir / "terraform"

    if not tf_dir.exists():
        print(json.dumps({"status": "pass"}))
        return

    tf_files = list(tf_dir.glob("*.tf"))
    if not tf_files:
        print(json.dumps({"status": "pass"}))
        return

    violations = []

    for tf_file in tf_files:
        content = tf_file.read_text(encoding="utf-8")

        # Find ingress blocks that reference 0.0.0.0/0
        ingress_blocks = re.findall(
            r'ingress\s*\{[^}]*\}',
            content,
            re.DOTALL,
        )

        for block in ingress_blocks:
            if '0.0.0.0/0' not in block:
                continue
            # Allow ALB ports 443 (HTTPS) and 80 (HTTP redirect)
            port_match = re.search(r'(?:from_port|port)\s*=\s*(\d+)', block)
            if port_match and port_match.group(1) in ("443", "80"):
                continue
            violations.append(f"{tf_file.name}: unrestricted ingress (0.0.0.0/0) on non-443/80 port")

        # Also check aws_security_group_rule resources with cidr 0.0.0.0/0
        sg_rules = re.findall(
            r'resource\s+"aws_security_group_rule"[^{]*\{[^}]*\}',
            content,
            re.DOTALL,
        )

        for block in sg_rules:
            if '0.0.0.0/0' not in block or 'type' not in block:
                continue
            if '"ingress"' not in block:
                continue
            port_match = re.search(r'from_port\s*=\s*(\d+)', block)
            if port_match and port_match.group(1) in ("443", "80"):
                continue
            violations.append(f"{tf_file.name}: sg rule with unrestricted ingress on non-443/80 port")

    if violations:
        print(json.dumps({"status": "fail", "details": "; ".join(violations[:5])}))
    else:
        print(json.dumps({"status": "pass"}))


if __name__ == "__main__":
    main()
