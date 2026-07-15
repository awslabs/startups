---
_phase: report
_title: "Write & Validate the Assessment Report"
_requires_phase: generate
_input:
  - discovery.json
  - coupling-score.json
  - preflight-findings.json
  - clarify-answers.json
  - recommendation.json
  - assessment-state.json
  - tier1-signals.json
_fragments:
  - _id: render
    _trigger: { _always: true }
    _file: phases/report/report-render.md
_assemble:
  _file: phases/report/report-assemble.md
_produces:
  - assessment-report.html
_advances_to: complete
_preconditions:
  - _check_phase_completed: generate
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: assessment-report.html
    _on_failure: _halt_and_inform
  - _assert: "the report-render.md validator invocation (scripts/validate-assessment-report.py) exited 0 within the 2-retry cap; the shell exit code was branched on, not stdout text pattern-matching"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
---

# Phase 5: Write & Validate the Assessment Report

Renders `assessment-report.html` from every upstream artifact, then runs it
through `scripts/validate-assessment-report.py` immediately after writing —
this is the last backbone phase; its completion marks the migration `complete`.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Render

Load `references/phases/report/report-render.md` and follow it. It renders
`assessment-report.html`, applying the outcome-based filter/reframe rule
(Requirement 6.3-6.4) to Pre-Flight Check findings, the reader-vocabulary rule
(Requirement 9.7), and the cost-labeling rule (Requirement 9.6) as authoring
discipline. The validator (Step 2, via the assembler) is the enforcement
mechanism backing these rules — `report-render.md` should get them right the
first time, but the validator is what actually gates completion.

---

## Step 2: Assemble, Validate, Retry-Cap, Hand Off

Load `references/phases/report/report-assemble.md` (the phase's assembler) and
follow it. It owns:

- Invoking `scripts/validate-assessment-report.py` immediately after the HTML
  is written.
- Branching on the validator's shell exit code per the table in
  `design.md` § 4.1 (0 = pass, 1 = fail-with-errors, anything else = validator
  did not run — never treated as pass).
- The retry-cap loop: up to 2 additional regeneration attempts on
  fail-with-errors, renaming to `assessment-report.incomplete.html` on each
  failed attempt (never deleting), surfacing all failure lines to the founder.
- Appending a `report_history` entry to `assessment-state.json` (capped at 5,
  FIFO eviction) and computing `diff_from_previous` (Requirement 11.4).
- The completion gate and phase-status update.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions`
frontmatter and enforced per `INTERPRETER.md` § Gate protocol: re-verify
`assessment-report.html` exists and that the validator exited 0 within the
retry cap, then emit `GATE_FAIL` or
`HANDOFF_OK | phase=report | artifacts=assessment-report.html` and advance.

**Important:** unlike other phases' gate failures, a report validation failure
that exhausts the retry cap does NOT mean the underlying assessment failed —
per Requirement 12.4, the assessment itself is still considered complete; only
the report's RENDERING failed. `report-assemble.md`'s own completion logic
handles this distinction (see its "On retry cap exhausted" section) —
it still surfaces the incomplete report and stops, but frames this to the
founder correctly: their findings and recommendation are valid, only the HTML
rendering needs attention.

---

## Step 3: Open the Report and Update Phase Status

After a genuine `HANDOFF_OK` (never on a validator-did-not-run or retry-cap-
exhausted path — only open a report that actually passed), try opening
`assessment-report.html` directly in the founder's default browser: run
`open "$MIGRATION_DIR/assessment-report.html"` on macOS or
`xdg-open "$MIGRATION_DIR/assessment-report.html"` on Linux. This is a
convenience only — if the command fails or the environment has no browser
available, do not treat this as an error; fall back to stating the file path
in the output message below.

Then apply the phase-status update protocol (`INTERPRETER.md` § The
interpreter loop) — mark `phases.report` completed and advance per
`_advances_to` (the terminal `complete`) — in the same turn as the output
message.

Output to the founder: "Your assessment report is ready:
`$MIGRATION_DIR/assessment-report.html`. [one-sentence recommendation summary].
Would you like a scaffold generated for this outcome?" (See `SKILL.md` §
Scaffold Checkpoint for the exact prompt.)

---

## Error Handling

| Error Category                                             | Behavior                                                                                                        |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `python3` not found when invoking the validator            | Validator did not run (exit 127) — tell the founder, do not treat as pass, do not rename/delete the HTML        |
| Validator script path resolves incorrectly                 | Same as above — surface the resolution error, never silently continue                                           |
| Retry cap (2 additional attempts) exhausted without a pass | Surface the incomplete report + failures, stop; the underlying assessment remains complete per Requirement 12.4 |

---

## Scope Boundary

**This phase covers rendering and validating `assessment-report.html` ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Terraform/SST generation (that is the Scaffold checkpoint's job)
- Re-running the Recommendation Engine or Discover's fragments
- Presenting a validator-did-not-run result as a pass

**Your ONLY job: render the report, validate it, retry within the cap, hand
off. Nothing else.**
