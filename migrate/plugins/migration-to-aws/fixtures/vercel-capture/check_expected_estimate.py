#!/usr/bin/env python3
"""Assert an Estimate run's output against expected-estimate.json.

Usage:
    python3 check_expected_estimate.py <migration_run_dir>

Where <migration_run_dir> contains the estimation-infra.json produced by a
replay seeded from seed-estimate/ (user-provided $200-1000 spend, unresolved
[A, B] tiebreak recommendation). Exits 0 on PASS, 1 on FAIL with one line per
failed assertion. Stdlib only.
"""

import json
import math
import sys
from pathlib import Path

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def close(a, b, tol=0.01) -> bool:
    return is_num(a) and math.isclose(a, b, abs_tol=tol)


def tier_sum_matches(breakdown: dict, total, tier_keys=("mid", "balanced", "monthly")):
    """Return None if some per-service tier key sums to total, else a message."""
    if not isinstance(breakdown, dict) or not breakdown:
        return "breakdown missing/empty"
    entries = {k: v for k, v in breakdown.items() if k != "total"}
    for key in tier_keys:
        vals = []
        ok = True
        for v in entries.values():
            if isinstance(v, dict) and is_num(v.get(key)):
                vals.append(v[key])
            else:
                ok = False
                break
        if ok and vals and is_num(total):
            if math.isclose(sum(vals), total, abs_tol=max(0.02 * total, 1.0)):
                return None
            return f"sum({key})={round(sum(vals), 2)} != total {total}"
    return "no consistent per-service tier key found across breakdown entries"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent

    est = json.loads((run_dir / "estimation-infra.json").read_text())
    exp = json.loads((fixture_dir / "expected-estimate.json").read_text())
    doc = json.dumps(est)

    # --- Baseline (Part 1 rung 2: user-provided midpoint) ---
    cur = est.get("current_costs", {})
    check(cur.get("source") == exp["current_costs"]["source"], f"current_costs.source={cur.get('source')}")
    check(
        close(cur.get("vercel_monthly"), exp["current_costs"]["vercel_monthly"]),
        f"current_costs.vercel_monthly={cur.get('vercel_monthly')} want {exp['current_costs']['vercel_monthly']} (documented $200-1000 midpoint)",
    )

    # --- Projected costs: tiers positive + Property-16 ---
    proj = est.get("projected_costs", {})
    for k in exp["projected_costs"]["tiers_positive"]:
        check(is_num(proj.get(k)) and proj[k] > 0, f"projected_costs.{k}={proj.get(k)} not positive")
    if exp["projected_costs"]["balanced_equals_breakdown_sum"]:
        msg = tier_sum_matches(proj.get("breakdown", {}), proj.get("aws_monthly_balanced"))
        check(msg is None, f"Property-16 (projected_costs): {msg}")

    # --- Tiebreak handling: both paths priced ---
    t = exp["tiebreak"]
    alt = est.get("tiebreak_alternative")
    check(isinstance(alt, dict) and bool(alt), "tiebreak_alternative absent — [A,B] outcome must price BOTH paths")
    if isinstance(alt, dict):
        for f in t["alternative_required_fields"]:
            check(f in alt, f"tiebreak_alternative.{f} missing")
        if is_num(alt.get("aws_monthly_balanced")):
            check(alt["aws_monthly_balanced"] > 0, "tiebreak_alternative balanced not positive")
            msg = tier_sum_matches(alt.get("breakdown", {}), alt.get("aws_monthly_balanced"))
            check(msg is None, f"Property-16 (tiebreak_alternative): {msg}")
    summary_txt = (
        json.dumps(est.get("financial_summary", {})) + json.dumps(est.get("recommendation", {}).get("path_label", ""))
    ).lower()
    for word in t["summary_must_mention"]:
        check(word.lower() in summary_txt, f"financial_summary/path_label does not mention '{word}'")

    # --- Cost comparison consistency ---
    comp = est.get("cost_comparison")
    check(isinstance(comp, dict) and bool(comp), "cost_comparison absent — a baseline exists in this scenario")
    if isinstance(comp, dict):
        check(
            close(comp.get("vercel_monthly"), exp["cost_comparison"]["vercel_monthly"]),
            f"cost_comparison.vercel_monthly={comp.get('vercel_monthly')}",
        )
        if exp["cost_comparison"]["delta_consistent"]:
            aws = comp.get("aws_monthly_balanced")
            delta = comp.get("monthly_delta")
            if is_num(aws) and is_num(delta):
                check(
                    close(delta, aws - exp["cost_comparison"]["vercel_monthly"]),
                    f"monthly_delta {delta} != {aws} - {exp['cost_comparison']['vercel_monthly']}",
                )

    # --- Peripherals priced ---
    breakdown_txt = json.dumps(proj.get("breakdown", {})).lower() + json.dumps(alt or {}).lower()
    for p in exp["peripheral_services_must_be_priced"]:
        aliases = {
            "postgres": ["rds", "postgres"],
            "kv": ["elasticache", "redis", "kv"],
            "cron": ["eventbridge", "cron", "scheduler"],
        }[p]
        check(any(a in breakdown_txt for a in aliases), f"peripheral '{p}' not visible in any cost breakdown")

    # --- Enums ---
    rec = est.get("recommendation", {})
    check(rec.get("path") in exp["recommendation_path_enum"], f"recommendation.path={rec.get('path')}")
    check(bool(str(rec.get("path_label", "")).strip()), "recommendation.path_label empty")
    for f in ("migrate_if", "stay_if"):
        check(isinstance(rec.get(f), list) and len(rec[f]) > 0, f"recommendation.{f} not a non-empty array")
    check(est.get("complexity_tier") in exp["complexity_tier_enum"], f"complexity_tier={est.get('complexity_tier')}")
    ps = est.get("pricing_source", {})
    check(ps.get("status") in exp["pricing_source_status_enum"], f"pricing_source.status={ps.get('status')}")

    # --- Must-not-exist ---
    check(cur.get("source") != "api_billing_data", "source claims api_billing_data with no billing data in scenario")
    for pat in ("*.tf",):
        tf = list(run_dir.rglob(pat))
        check(not tf, f"estimate wrote terraform files: {[str(p) for p in tf][:3]} (_forbids_files)")
    for bad in ("sk_live", "vcp_", "Bearer ", "postgres://", "rediss://"):
        check(bad not in doc, f"possible secret/token material: {bad}")

    if FAILS:
        print(f"FAIL ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("PASS — expected-estimate.json assertions hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
