---
_phase: intake
_title: "Intake — Entry Point + Background"
_init: true
_input: workspace
_assemble:
  _file: phases/intake/intake-assemble.md
_produces:
  - .phase-status.json
_advances_to: discover
_postconditions:
  - _check_file_exists: .phase-status.json
    _on_failure: _halt_and_inform
  - _validate_json: .phase-status.json
    _on_failure: _halt_and_inform
  - _assert: "the .phase-status.json written by Step 5 has entry_point and audience set, intake = completed, and all later phases set to pending or skipped per the entry point"
    _on_failure: _halt_and_inform
---

# Phase: Intake — Entry Point + Background

## Step 1 — Create the run directory

Generate a run id from the current time as `MMDD-HHMM`. Create the run directory under the
**user's current working directory** (run `pwd` and anchor to it) — NOT the plugin install tree.
So: `<cwd>/.agent-advisor/<run_id>/`, plus `<cwd>/.agent-advisor/.gitignore` containing `*` (so
run state is never committed). All later `$RUN_DIR` references point here.

## Step 1.5 — Temporal signal check (before the two questions)

If the opening message carries a Temporal signal (mentions Temporal, Temporal Cloud,
Temporal workers, `temporalio` / `go.temporal.io` / `@temporalio` / `temporal-sdk`), gate on
how explicit the INTENT is:

- **Intent explicit** — the message already says both "Temporal" AND "move/migrate (workers)
  to AWS" in substance → do NOT ask a confirmation (the user just told you; re-asking is
  friction). Set `entry_point = temporal_worker` in `.phase-status.json` (Step 5 write; Q1 is
  skipped — the entry point is decided), tell the user in one line ("Entering the Temporal
  Worker path — your workflow orchestration code stays untouched"), still ask Q2 (background)
  and the Step 4 code-path prompt (the branch scans code when a path is given), then load
  `references/phases/temporal-worker/temporal-worker.md` and follow it. Do NOT continue into Discover/Clarify.
- **Intent unclear** — Temporal is mentioned but the ask could be a general runtime
  recommendation → confirm first (AskUserQuestion): "You run on Temporal — is this about
  moving the Temporal workers to AWS? (Your workflow code stays untouched.)"
  On yes → same as above. On no → proceed normally with Step 2; do not re-raise Temporal.

## Step 2 — Ask two questions with AskUserQuestion

Ask BOTH in one AskUserQuestion call (two questions):

**Q1 — Starting point** (header "Starting point"):

- Build from scratch — I have an idea, no code → `build_scratch`
- Deploy existing code — I have working agent code → `build_deploy`
- Migrate — I have agents running elsewhere → `migrate`
- Add capabilities — already on AWS, want to add services → `add_capabilities`

**Q2 — Your background** (header "Background"):

- Technical (engineer/developer) → `technical`
- Business-leaning (founder/PM/non-technical) → `business`
- Mixed team → `business` (start in business language, add technical detail on request)

## Step 3 — Handle add_capabilities

If Q1 == add_capabilities: this is a self-contained branch of THIS skill. Set `entry_point =
add_capabilities` in `.phase-status.json` (Step 5), then load
`references/phases/add-capabilities/add-capabilities.md` and follow it. Do NOT continue into Discover / Clarify /
Design — the branch runs its own 5-step flow and ends by writing
`capabilities-recommendation.md`. (Per the state table, the `add_capabilities` row routes here
directly after intake.)

## Step 4 — Open context prompt

Ask (plain text): "What can you tell me about your agent? Any files or existing code to
share? (Optional — say 'skip' to move on.)" Capture any framework/model/infra hints into
`$RUN_DIR/context-notes.md`.

For `build_deploy` / `migrate`, **explicitly ask for the code path** ("Where's your agent code?
A directory path lets me detect your framework/model and skip questions."). Discover runs only
if a path is given; if the user declines a path, note it and set `discover = skipped` in Step 5.

## Step 5 — Write state

Write `$RUN_DIR/.phase-status.json` with `entry_point`, `audience` (from Q2), `intake` =
completed. Set `discover` = pending if entry point is build_deploy/migrate AND the user
offered a code path, else `skipped`. Set all later phases (`clarify`, `confirm`, `design`,
`estimate`, `generate`) to pending.
