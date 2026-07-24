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
    "gcp-workshop/check_expected_workshop.py": "gcp-workshop/after-graviton-reprice",
    "gcp-decision-gate/check_expected_decide.py": "gcp-decision-gate/after-decide-complete",
    "heroku-live-capture/check_expected_drift.py": None,
    "heroku-live-capture/check_expected_estimate.py": None,
    "gcp-live-capture/check_expected_drift.py": None,
    "gcp-live-capture/check_expected_baseline.py": None,
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
