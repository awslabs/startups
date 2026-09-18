#!/usr/bin/env python3
"""Run the committed fixture asserters in CI.

Two tiers:

1. GOLDEN — asserters whose fixture directory contains a committed golden
   run tree. The asserter is executed against that tree and MUST exit 0.
   This makes every committed exact-math guarantee (workshop scenario
   deltas, reprice totals) a permanent CI invariant instead of a
   run-it-by-hand convention.

2. SMOKE — asserters that validate a live replay run dir (no golden output
   is committed; producing one requires an agent run). These are executed
   against an empty scratch directory and MUST exit non-zero WITHOUT a
   Python traceback: a clean assertion failure proves the script still
   parses and its failure path works (bitrot guard).

Zero dependencies (stdlib only), mirroring the asserters themselves.
Exit 0 iff every check passes.
"""

import subprocess  # nosec B404 — CI runner; executes only committed asserter scripts via sys.executable
import sys
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# asserter path (relative to fixtures/) -> committed golden run dir, or None for smoke-only
ASSERTERS = {
    "heroku-workshop/check_expected_workshop.py": "heroku-workshop/after-arm64-reprice",
    "heroku-nonweb-scaling/check_expected_nonweb_scaling.py": "heroku-nonweb-scaling/after-design",
    "gcp-workshop/check_expected_workshop.py": "gcp-workshop/after-graviton-reprice",
    "gcp-decision-gate/check_expected_decide.py": "gcp-decision-gate/after-decide-complete",
    "heroku-live-capture/check_expected_drift.py": None,
    "heroku-live-capture/check_expected_estimate.py": None,
    "gcp-live-capture/check_expected_drift.py": None,
    "gcp-live-capture/check_expected_baseline.py": None,
    # Input-corpus fixture. `workspace-terraform/` is the committed INPUT; each golden
    # tree below is the hand-authored expected output for one phase.
    "azure-iac-terraform/check_expected_iac_terraform.py": "azure-iac-terraform/after-discover",
    # Design, both passes. CORRECTED 2026-09-08: this golden is NO LONGER a halted design.
    # It was, while the corpus carried an untranslated cost-bearing type and the pass-2
    # rubrics were absent. Derivation resolved azurerm_iothub and the rubrics landed, so the
    # tree now has untranslated_types [] and pending_rubric [] and SATISFIES design.md's
    # _postconditions. That is what makes Estimate reachable on this corpus at all: with
    # after-clarify-complete/ answering the clarify gate, both blockers that once stood in
    # front of Estimate are gone. The directory name is unchanged only to avoid churning
    # every reference to it.
    "azure-iac-terraform/check_expected_design.py": "azure-iac-terraform/after-design",
    # Clarify. The golden is a BLOCKED clarify — an ESSENTIAL row is unanswered, so the phase
    # must GATE_FAIL. That pins the completion gate rather than only the happy path. Clarify is
    # _interactive: true, so `clarify-answers.json` stands in for the user; the asserter tests
    # BRANCHING (which rows fire, which are ESSENTIAL, which are N/A), never the conversation.
    "azure-iac-terraform/check_expected_clarify.py": "azure-iac-terraform/after-clarify",
    # second branch of the same phase: BLOCKED above, COMPLETING here. Both are real states.
    "azure-iac-terraform/check_expected_clarify_complete.py": "azure-iac-terraform/after-clarify-complete",
    # Estimate. FIRST asserter in the repo that uses TOLERANCES rather than exact equality:
    # AWS rates move on AWS's cadence, so an exact committed total would go permanently red
    # on the next refresh. Three tiers — contracts exact, arithmetic identities exact but
    # RELATIVE (they survive any rate change), dollar figures against bands recorded in
    # expected-estimate.json. The golden is deliberately not a clean estimate: five of the
    # sixteen designed services cannot be priced, so both totals are FLOORS and the
    # right-sizing delta is legitimately $0 — the two states an implementation is most
    # likely to fake into something tidier.
    "azure-iac-terraform/check_expected_estimate.py": "azure-iac-terraform/after-estimate",
}


def run(asserter: Path, run_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 — list args, no shell, paths from the committed registry only
        [sys.executable, str(asserter), str(run_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def main() -> int:
    # Fail loudly if a new asserter appears without being registered here.
    on_disk = {str(p.relative_to(FIXTURES)) for p in FIXTURES.rglob("check_expected_*.py")}
    unregistered = on_disk - set(ASSERTERS)
    missing = set(ASSERTERS) - on_disk
    failures = []
    if unregistered:
        failures.append(f"unregistered asserters (add to run-asserters.py): {sorted(unregistered)}")
    if missing:
        failures.append(f"registered asserters missing on disk: {sorted(missing)}")

    for rel, golden in sorted(ASSERTERS.items()):
        if rel in missing:
            continue
        asserter = FIXTURES / rel
        if golden is not None:
            result = run(asserter, FIXTURES / golden)
            if result.returncode != 0:
                failures.append(
                    f"GOLDEN {rel} vs {golden}: exit {result.returncode}\n"
                    f"{result.stdout.strip()}\n{result.stderr.strip()}"
                )
            else:
                print(f"GOLDEN ok   {rel}")
        else:
            with tempfile.TemporaryDirectory() as scratch:
                result = run(asserter, Path(scratch))
            if result.returncode == 0:
                failures.append(f"SMOKE {rel}: exited 0 on an empty run dir (should fail)")
            elif "Traceback" in result.stderr:
                failures.append(f"SMOKE {rel}: crashed with traceback instead of clean FAIL\n{result.stderr.strip()}")
            else:
                print(f"SMOKE  ok   {rel}")

    if failures:
        print(f"\nFAIL ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"\nPASS — {len(ASSERTERS)} asserters ({sum(1 for g in ASSERTERS.values() if g)} golden, "
          f"{sum(1 for g in ASSERTERS.values() if g is None)} smoke)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
