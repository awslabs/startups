---
_assemble: report-assemble
_of_phase: report
_reads:
  - render (migration-report.html content)
_produces:
  - migration-report.html
---

# Report Phase: Assembler

> Writes `report-render.md`'s content to `migration-report.html`, invokes
> `scripts/validate-assessment-report.py` immediately after, branches on the
> validator's shell exit code, retries within a 2-additional-attempt cap on
> fail-with-errors, appends a capped `report_history` entry to
> `assessment-state.json`, and runs the completion gate. This is the SINGLE
> creator of `migration-report.html` and the sole owner of the retry-cap
> loop.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Write `migration-report.html`

Write `report-render.md`'s rendered content to
`$MIGRATION_DIR/migration-report.html`.

---

## Step 2: Invoke the Validator

Run:

```bash
python3 "$PLUGIN_ROOT/scripts/validate-assessment-report.py" \
  "$MIGRATION_DIR/migration-report.html" \
  --recommendation "$MIGRATION_DIR/recommendation.json" \
  --preflight-findings "$MIGRATION_DIR/preflight-findings.json" \
  --tier1-signals "$MIGRATION_DIR/tier1-signals.json" \
  --migration-dir "$MIGRATION_DIR"
```

**Branch on the shell exit code — never on stdout/stderr text pattern-matching
alone** (per Requirement 12.2 and `design.md` § 4.1):

| Exit code                                                                                | Meaning                                                                   | Action                                               |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------- |
| `0`                                                                                      | `REPORT_OK` — validation passed                                           | Proceed to Step 5 (report_history + completion gate) |
| `1`                                                                                      | `REPORT_FAIL` — validation ran and found issues                           | Go to Step 3 (retry loop)                            |
| anything else (e.g. `127` command not found, `126` permission denied, `2` bad arguments) | **Validator did not run** — this is neither `REPORT_OK` nor `REPORT_FAIL` | Go to Step 4 (validator-did-not-run handling)        |

---

## Step 3: Retry Loop (On Exit Code 1 — Fail-With-Errors)

Per Requirement 12.3-12.4:

1. Rename the failed HTML to `$MIGRATION_DIR/migration-report.incomplete.html`
   (never delete unless the founder explicitly asks).
2. Emit all failure lines (from the validator's stderr) to the founder.
3. Retry report generation: re-run `report-render.md`'s Step 1-11 addressing
   the specific failures reported, re-write `migration-report.html`, and
   return to Step 2 above.
4. **Retry cap: maximum 2 additional attempts** (3 total including the first).
   Track attempt count for this reason within this phase invocation.
5. **If the retry cap is reached without a passing validation:**
   - Surface the incomplete report (`migration-report.incomplete.html`) and
     its most recent failure list to the founder.
   - **STOP.** Do not present a stub as complete.
   - **Critically:** per Requirement 12.4, the underlying ASSESSMENT is still
     considered complete — the report is the deliverable's RENDERING, not the
     assessment itself. Tell the founder their findings and recommendation
     (`recommendation.json`, `discovery.json`, etc.) remain valid and usable
     even though the HTML rendering needs attention. Do NOT mark
     `phases.report` as `"completed"` in this case — the phase itself did not
     complete successfully, only the underlying data is sound. Leave
     `phases.report` at `"in_progress"` and let the founder decide whether to
     manually fix the HTML or re-invoke Report later.

---

## Step 4: Validator-Did-Not-Run Handling (Any Other Exit Code)

Per Requirement 12.2: this is NEVER treated as a pass.

1. Do NOT rename or delete `migration-report.html`.
2. Do NOT claim the report passed or failed validation.
3. Tell the founder: "Could not run the report validator (exit code {N},
   stderr: {stderr}) — install Python 3 (`python3 --version` to check) or
   verify the plugin path is correct, then re-run validation manually."
4. The Report phase MAY still complete with the UNVALIDATED report present on
   disk, but the founder MUST be told validation did not occur — never
   silently treat a missing interpreter (or any other non-0/1 exit) as a pass.
   If completing under this condition, still write the `report_history` entry
   (Step 5) but mark it with `validated: false` so a future diff knows this
   entry's `migration-report.html` was never actually validated.

---

## Step 5: Append `report_history` Entry (On a Genuine Pass, or Step 4's Unvalidated-Complete Path)

Read the current `assessment-state.json` (read-merge-write):

1. Compute `diff_from_previous` by comparing this run's `findings` snapshot
   against the immediately prior `report_history` entry's
   `recommendation_snapshot` (if any exist) — per Requirement 11.4, list every
   `finding_id` whose `confidence` or `value` changed since that entry.
2. Append the new entry:

   ```json
   {
     "generated_at": "<ISO 8601>",
     "recommendation_snapshot": {/* copy of recommendation.json */},
     "diff_from_previous": [/* per above, or null if this is the first entry */]
   }
   ```

3. **Apply the 5-entry cap (FIFO eviction):** if `report_history` now has more
   than 5 entries, drop the OLDEST (index 0) before writing. This is the
   design.md "Resolved Design Decisions" item 2 cap.
4. Update `last_updated`. Write the file back.

---

## Completion Gate

Re-read `migration-report.html` from disk, then run the checks declared in
`report.md`'s `_postconditions`:

1. `migration-report.html` exists.
2. The validator invocation exited `0` within the retry cap (or, per Step 4,
   the founder was explicitly told validation did not occur — this counts as
   satisfying the `_assert` since the constraint is "branch on exit code
   correctly and never silently treat a non-pass as a pass," not "always
   achieve exit 0").
3. `assessment-state.json.report_history` has at most 5 entries after this
   write.

**On any failure (including retry-cap exhaustion at Step 3.5):** emit exactly:

```
GATE_FAIL | phase=report | field=migration-report.html | reason=<invalid|validator_exhausted_retries>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`
to `"completed"` in this case — see Step 3.5's guidance on leaving
`phases.report` at `in_progress`.

**On all-pass:** emit exactly:

```
HANDOFF_OK | phase=report | artifacts=migration-report.html
```

Then update `.phase-status.json`: mark `phases.report` `"completed"`, set
`current_phase` to `complete` (the terminal — the backbone is now exhausted),
update `last_updated` — in the same turn as `report.md`'s Step 3 output
message.

---

## Scope Boundary

**This assembler covers writing, validating, retrying within the cap, and the
completion gate ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-rendering content beyond what a retry explicitly requires (do not
  re-render sections that already passed validation, if the validator's error
  list is scoped enough to identify which section(s) failed)
- Presenting a stub report as complete
- Treating a non-0/1 exit code as a pass
- Advancing `.phase-status.json` to `"completed"` when the retry cap was
  exhausted

**Your ONLY job: write, validate, retry within cap, record history, gate,
hand off.**
