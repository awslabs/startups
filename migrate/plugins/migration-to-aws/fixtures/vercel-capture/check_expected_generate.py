#!/usr/bin/env python3
"""Assert a Generate run's output against expected-generate.json.

Usage:
    python3 check_expected_generate.py <migration_run_dir>

Where <migration_run_dir> contains the terraform/, scripts/, docs, and
generation-warnings.json produced by a replay seeded from seed-generate/
(unresolved [A, B] tiebreak; the replay founder picks Outcome A). Exits 0 on
PASS, 1 on FAIL with one line per failed assertion. Stdlib only.
"""

import json
import re
import sys
from pathlib import Path

FAILS: list = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent
    exp = json.loads((fixture_dir / "expected-generate.json").read_text())

    # --- File inventory ---
    for f in exp["mandatory_files"]:
        check((run_dir / f).is_file(), f"mandatory file missing: {f}")
    for f in exp["outcome_a_files_must_exist"]:
        check((run_dir / f).is_file(), f"Outcome A artifact missing: {f} (founder picked A)")
    for f in exp["outcome_b_files_must_not_exist"]:
        check(not (run_dir / f).exists(), f"mutual exclusion broken: {f} exists alongside the OpenNext path")
    for f in exp["peripheral_files_must_exist"]:
        check((run_dir / f).is_file(), f"peripheral terraform missing: {f}")

    scripts = sorted((run_dir / "scripts").glob("*.sh")) if (run_dir / "scripts").is_dir() else []
    check(len(scripts) >= exp["scripts_dir_min_files"], f"scripts/: {len(scripts)} files, want >= {exp['scripts_dir_min_files']}")
    check(
        any(exp["scripts_must_include_substring"] in p.name for p in scripts),
        f"no script name contains '{exp['scripts_must_include_substring']}'",
    )

    # --- main.tf provider pin + variables ---
    main_tf = (run_dir / "terraform/main.tf").read_text() if (run_dir / "terraform/main.tf").is_file() else ""
    for s in exp["main_tf_must_contain"]:
        check(s in main_tf, f"main.tf missing '{s}'")
    variables_tf = (run_dir / "terraform/variables.tf").read_text() if (run_dir / "terraform/variables.tf").is_file() else ""
    for v in exp["variables_must_declare"]:
        check(re.search(rf'variable\s+"{v}"', variables_tf), f"variables.tf does not declare {v}")

    # --- Placeholder scan (backend block exempt) ---
    if exp["no_placeholder_tokens_outside_backend"]:
        for tf in sorted((run_dir / "terraform").glob("*.tf")):
            text = tf.read_text()
            # strip backend block(s) before scanning
            stripped = re.sub(r'backend\s+"[^"]+"\s*\{[^}]*\}', "", text, flags=re.DOTALL)
            for m in re.finditer(r"\{\{[A-Za-z0-9_]+\}\}", stripped):
                check(False, f"placeholder token {m.group(0)} in {tf.name}")

    # --- terraform validate warning (environment-dependent Step 6) ---
    gw = json.loads((run_dir / "generation-warnings.json").read_text()) if (run_dir / "generation-warnings.json").is_file() else {}
    warnings = gw.get("warnings", [])
    if exp["terraform_validate_warning"]["at_most_one"]:
        tv = [w for w in warnings if w.get("service") == "terraform_validate"]
        check(len(tv) <= 1, f"expected at most one terraform_validate warning entry, found {len(tv)}")
        for w in tv:
            check(bool(str(w.get("action", "")).strip()), "terraform_validate warning has no founder-facing action")

    # --- Compliance: Q8 'none' => no Config recorder / Security Hub ---
    if exp["compliance_none_means_no_config_recorder"]:
        baseline = (run_dir / "terraform/baseline.tf").read_text() if (run_dir / "terraform/baseline.tf").is_file() else ""
        for bad in ("aws_config_configuration_recorder", "aws_securityhub_account"):
            check(bad not in baseline, f"baseline.tf contains {bad} despite Q8 compliance = none")

    # --- Cross-reference: every estimated service accounted for ---
    est_path = run_dir / "estimation-infra.json"
    if not est_path.exists():
        check(False, "missing estimation-infra.json in run dir")
        print(f"FAIL ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    est = json.loads(est_path.read_text())
    tf_text = "".join(p.read_text() for p in (run_dir / "terraform").glob("*.tf")) + (
        (run_dir / "sst.config.ts").read_text() if (run_dir / "sst.config.ts").is_file() else ""
    )
    scripts_text = "".join(p.read_text() for p in scripts)
    warn_text = json.dumps(warnings)
    covered_corpus = (tf_text + scripts_text + warn_text).lower()
    aliases = {
        "rds_postgresql": ["aws_db_instance", "rds", "postgres"],
        "elasticache_redis": ["aws_elasticache", "elasticache", "redis"],
        "cron_eventbridge_lambda": ["aws_scheduler", "aws_cloudwatch_event", "eventbridge", "cron"],
        "nat_gateway": ["aws_nat_gateway", "nat"],
        "secrets_manager": ["secretsmanager", "secrets_manager", "secrets"],
        "cloudfront": ["cloudfront"],
        "lambda": ["lambda"],
        "s3": ["s3", "bucket"],
        "eventbridge": ["eventbridge", "scheduler", "revalidation"],
    }
    for svc in est.get("projected_costs", {}).get("breakdown", {}):
        if svc == "total":
            continue
        candidates = aliases.get(svc, [svc.lower(), svc.lower().replace("_", "")])
        check(
            any(a in covered_corpus for a in candidates),
            f"estimated service '{svc}' not found in terraform/scripts/warnings (aliases tried: {candidates})",
        )

    # --- Secret hygiene ---
    all_docs = tf_text + scripts_text + json.dumps(gw)
    for p in ("MIGRATION_GUIDE.md", "README.md"):
        if (run_dir / p).is_file():
            all_docs += (run_dir / p).read_text()
    for bad in ("sk_live", "vcp_", "Bearer "):
        check(bad not in all_docs, f"possible secret/token material: {bad}")

    if FAILS:
        print(f"FAIL ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("PASS — expected-generate.json assertions hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
