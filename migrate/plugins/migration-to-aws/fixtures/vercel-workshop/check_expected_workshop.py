#!/usr/bin/env python3
"""Assert a Vercel what-if workshop run against expected-workshop.json.

Usage:
    python3 check_expected_workshop.py <migration_run_dir> [<seed_dir>]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2

    run_dir = Path(sys.argv[1])
    fixture_dir = Path(__file__).resolve().parent
    seed_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else fixture_dir / "seed"
    exp = json.loads((fixture_dir / "expected-workshop.json").read_text())

    disc_run = run_dir / "discovery.json"
    disc_seed = seed_dir / "discovery.json"
    check(disc_run.exists(), "missing discovery.json in run dir")
    check(disc_seed.exists(), "missing seed discovery.json")
    if disc_run.exists() and disc_seed.exists() and exp.get("discovery_must_match_seed_bytes"):
        check(
            disc_run.read_bytes() == disc_seed.read_bytes(),
            "discovery bytes changed — workshop must freeze discovery",
        )

    index_path = run_dir / "scenarios" / "index.json"
    check(index_path.exists(), "missing scenarios/index.json")
    if not index_path.exists():
        _fail()
        return 1

    index = json.loads(index_path.read_text())
    scenarios = index.get("scenarios") or []
    check(len(scenarios) >= exp["min_scenarios"], f"scenario count {len(scenarios)}")
    check(len(scenarios) <= exp["max_scenarios"], f"scenario count exceeds max")
    check(index.get("baseline_scenario_id") == exp["baseline_scenario_id"], "baseline id mismatch")
    check(index.get("active_scenario_id") == exp["active_scenario_id"], "active id mismatch")

    clar = json.loads((run_dir / "clarify-answers.json").read_text())
    workshop = clar.get("workshop") or {}
    check(workshop.get("cpu_architecture") == exp["active_cpu_architecture"], "cpu_architecture mismatch")
    check(workshop.get("outcome_override") == exp["active_outcome"], "outcome_override mismatch")
    check(workshop.get("active_scenario_id") == exp["active_scenario_id"], "workshop active_scenario_id mismatch")

    q1 = clar.get("Q1_traffic_shape") or {}
    if exp.get("q1_must_have_workshop_note"):
        note = q1.get("workshop_note") or ""
        check(bool(note), "Q1 missing workshop_note after transcript edit")
        if exp.get("q1_original_in_note"):
            check(
                exp["q1_original_in_note"] in note,
                f"workshop_note missing original answer {exp['q1_original_in_note']!r}: {note!r}",
            )

    rec = json.loads((run_dir / "recommendation.json").read_text())
    check(rec.get("outcome") == exp["active_outcome"], f"recommendation.outcome={rec.get('outcome')}")
    check(rec.get("fired_rule") == exp["active_fired_rule"], f"fired_rule={rec.get('fired_rule')}")
    if exp.get("must_not_have_rule_id"):
        check("rule_id" not in rec, "invented rule_id field must not appear")
        check("rule_rationale" not in rec, "invented rule_rationale field must not appear")
    if exp.get("tiebreak_must_be_false"):
        check(rec.get("tiebreak") is False, f"tiebreak={rec.get('tiebreak')} want false")
        check(rec.get("resolving_input") is None, "resolving_input must be null under workshop_override")
    if exp.get("must_omit_separable_for_ab") and rec.get("outcome") in ("A", "B"):
        check("separable" not in rec, "separable must be omitted for outcome A/B")
        check("backend_shape" not in rec, "backend_shape must be omitted for outcome A/B")
    if exp.get("reasons_must_prefix_workshop_assumption"):
        reasons = rec.get("reasons") or []
        check(any(isinstance(r, str) and r.startswith("workshop assumption:") for r in reasons),
              "reasons[] must include a workshop assumption: prefix")

    est = json.loads((run_dir / "estimation-infra.json").read_text())
    base_manifest = run_dir / "scenarios" / f"{exp['baseline_scenario_id']}.json"
    check(base_manifest.exists(), "missing baseline scenario manifest")
    if base_manifest.exists() and exp.get("balanced_must_differ_from_baseline"):
        base = json.loads(base_manifest.read_text())
        base_bal = base["estimation_summary"]["aws_monthly_balanced"]
        act_bal = est["projected_costs"]["aws_monthly_balanced"]
        check(act_bal != base_bal, f"balanced unchanged ({act_bal}) vs baseline ({base_bal})")

    phase_path = run_dir / ".phase-status.json"
    if phase_path.exists():
        phase = json.loads(phase_path.read_text())
        phases = phase.get("phases", {})
        if exp.get("generate_must_not_be_completed"):
            check(phases.get("generate") != "completed", "generate must not auto-complete")
        if exp.get("current_phase_must_be"):
            check(
                phase.get("current_phase") == exp["current_phase_must_be"],
                f"current_phase={phase.get('current_phase')} want {exp['current_phase_must_be']}",
            )
        if exp.get("workshop_phase_must_be"):
            check(
                phases.get("workshop") == exp["workshop_phase_must_be"],
                f"phases.workshop={phases.get('workshop')} want {exp['workshop_phase_must_be']}",
            )

    blob = (run_dir / "clarify-answers.json").read_text() + (run_dir / "recommendation.json").read_text()
    for bad in ("VERCEL_TOKEN", "Bearer ", "vcp_"):
        check(bad not in blob, f"possible secret material: {bad}")

    if FAILS:
        _fail()
        return 1
    print("PASS — expected-workshop.json assertions hold")
    return 0


def _fail() -> None:
    print(f"FAIL ({len(FAILS)}):")
    for f in FAILS:
        print(f"  - {f}")


if __name__ == "__main__":
    sys.exit(main())
