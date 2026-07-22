---
_phase: prescan
_title: "Collect Tier 1 Inputs & Pre-Scan"
_init: true
_input: workspace
_fragments:
  - _id: tier1-collect
    _trigger: { _always: true }
    _file: phases/prescan/prescan-collect.md
  - _id: build-free-scan
    _trigger: { _always: true }
    _file: phases/prescan/prescan-scan.md
_assemble:
  _file: phases/prescan/prescan-assemble.md
_produces:
  - tier1-signals.json
  - assessment-state.json
_advances_to: discover
_interactive: true
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "repo access is present AND a Vercel API token is present AND at least one in-scope Vercel project is identified"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [tier1-signals.json, assessment-state.json]
    _on_failure: _halt_and_inform
  - _validate_json: [tier1-signals.json, assessment-state.json]
    _on_failure: _halt_and_inform
  - _assert: "tier1-signals.json has next_version, package_manager, has_middleware, has_vercel_json, and project_list populated (or explicitly null with a reason)"
    _on_failure: _halt_and_inform
  - _assert: "assessment-state.json validates against references/state/assessment-state.schema.json and inputs_received.tier1 reflects what prescan-collect.md actually found"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - migration-report.html
---

# Phase 1: Collect Tier 1 Inputs & Pre-Scan

Lightweight orchestrator that delegates to two independent fragments: Tier 1 input
collection (the three required inputs) and a build-free workspace/API scan. Neither
fragment depends on the other's output — they run in either order and contribute
their own section of `tier1-signals.json`.

This phase is `_interactive: true` and runs INLINE in the main window, never
dispatched: its work converses with the founder (the token request), runs the
shell (the Tier 1 `next build` health attempt), and calls the Vercel API (token
validation, project enumeration) — none of which a dispatched worker can do, and
the token must never transit an artifact to reach one. Its work is light enough
that inline execution costs little context.

**Execute ALL steps in order. Do not skip or deviate.**

This is this skill's `_init: true` entry phase — the backbone head. On a cold
start, the interpreter loads this file directly (see `INTERPRETER.md` § The
interpreter loop, step 1); it does not scan other phases to find the root.

---

## Step 0: Initialize Migration State

This phase has `_init: true`. Per `INTERPRETER.md` (§ `_init`), establish migration
state before running the fragments: resolve resume-vs-fresh, set
`$MIGRATION_DIR`, create `.migration/.gitignore`, and write the initial
`.phase-status.json`.

**In addition to the vendored `_init` steps**, this skill also seeds its OWN
resumability ledger, `assessment-state.json` (schema:
`references/state/assessment-state.schema.json`) — this is skill-owned, not part
of the vendored DSL contract:

- **If resuming an existing run:** read the existing `assessment-state.json` from
  `$MIGRATION_DIR`. If it is missing or corrupt, treat this independently of
  `.phase-status.json`'s validity — do not fail the whole re-entry over a corrupt
  `assessment-state.json`; instead surface a specific diagnostic ("assessment
  state corrupted — inputs_received/findings history is unavailable; PreScan will
  re-collect from scratch") and initialize a fresh one.
- **If a fresh run:** initialize `assessment-state.json` with `schema_version:
  "1.0"`, this run's `migration_id`, the current timestamp, empty
  `inputs_received.{tier1,tier2,tier3}` maps, empty `findings`, empty
  `clarify_answers`, and an empty `report_history` array.

Confirm `.migration/.gitignore`, `.phase-status.json`, AND `assessment-state.json`
all exist before proceeding to Step 1.

---

## Step 1: Determine Warm-Start Recompute Scope

If this is a warm re-entry (an `assessment-state.json` with non-empty
`inputs_received` already existed before Step 0), determine the `newly_received`
list: for each Tier 2/3 input, compare its `received` flag now against what it was
before this invocation. Pass `newly_received` forward to `discover` — see
`SKILL.md` § Assessment State Management. On a cold, fresh run `newly_received` is
irrelevant (every input is being collected for the first time).

---

## Step 2: Run Fragments

Execute both fragments. They are independent — order does not matter for
correctness, but run `tier1-collect` first since its preconditions gate this whole
phase.

**2a. Tier 1 Collection:**

Load `references/phases/prescan/prescan-collect.md`. This validates the three
required Tier 1 inputs (repo access + `next build` health, Vercel API token,
project scope) and, when Tier 2/3 inputs happen to already be present (e.g. the
founder supplied a log drain export up front), records their presence too.

**2b. Build-Free Scan:**

Load `references/phases/prescan/prescan-scan.md`. This performs the cheap,
build-free workspace + API scan (`package.json`, lockfile census, `middleware.ts`
existence, `vercel.json` presence, Vercel project enumeration).

---

## Step 3: Assemble

Load `references/phases/prescan/prescan-assemble.md` (the phase's assembler) and
follow it to combine both fragments' contributions into `tier1-signals.json`, seed
`assessment-state.json.inputs_received.tier1`, and run the completion gate.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter
and enforced per `INTERPRETER.md` § Gate protocol: re-read both artifacts from
disk, run the mechanical checks and the `_assert` judgment checks, then emit
`GATE_FAIL` (STOP; do not patch artifacts) or
`HANDOFF_OK | phase=prescan | artifacts=<files verified>` and advance.

---

## Step 4: Update Phase Status and Hand Off

Only after `HANDOFF_OK`, apply the phase-status update protocol
(`INTERPRETER.md` § The interpreter loop) — mark `phases.prescan` completed and
advance per `_advances_to` — in the **same turn** as the output message below.

Output to the founder — build the message from `tier1-signals.json` contents:

- "PreScan complete. Detected Next.js {version}, {package_manager}."
- If middleware detected: "Found `middleware.ts` — Discover will analyze what
  it does statically; Clarify does not ask about it (see below)."
- If not detected: "No `middleware.ts` found."
- If multiple projects in scope: "{N} Vercel projects in scope."

Format: "PreScan phase complete. [summary] Next required step: Phase 2 — Discover.
Load `references/phases/discover/discover.md` now."

---

## Output Files

This phase's artifacts are declared in `_produces` and its scope boundary in
`_forbids_files`. All user communication is via output messages only.

---

## Error Handling

| Error Category                                     | Behavior                                                                     |
| -------------------------------------------------- | ---------------------------------------------------------------------------- |
| No repo access at all                              | `_preconditions` `_assert` fails `_unrecoverable` — STOP                     |
| No Vercel API token                                | Same — STOP, name the missing input specifically                             |
| Repo access present but `next build` fails         | NOT a precondition failure — record as a finding, continue                   |
| `assessment-state.json` corrupt on a warm re-entry | Independent of `.phase-status.json` validity — re-initialize, warn, continue |

---

## Scope Boundary

**This phase covers Tier 1 input collection and the build-free scan ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Running the Adapter API build or producing `.next` manifests for Discover
  (Discover's capture pre-work owns those; the ONE plain `next build` health
  attempt in `prescan-collect.md` Step 1b is Tier 1 input validation, not
  discovery)
- AWS service names, recommendations, or equivalents
- Coupling Score computation or Pre-Flight Check computation
- Clarify questions
- Recommendation logic

**Your ONLY job: Validate Tier 1 inputs exist and perform the cheap, build-free
scan. Nothing else.**
