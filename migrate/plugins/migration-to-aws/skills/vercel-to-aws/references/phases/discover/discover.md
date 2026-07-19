---
_phase: discover
_title: "Full Discovery, Coupling Score, Pre-Flight Checks"
_requires_phase: prescan
_input:
  - tier1-signals.json
  - assessment-state.json
_knowledge:
  - { file: knowledge/preflight-checks.json, _when: "always - defines the M1/M2/B1-B4/S1/I1/O1/U1 check table" }
  - { file: knowledge/coupling-weights.json, _when: "always - defines Coupling_Score item weights and detection methods" }
_fragments:
  - _id: adapter-build
    _trigger: { _when: "$MIGRATION_DIR/capture/manifest.json records build.method == \"adapter\"" }
    _file: phases/discover/discover-adapter.md
  - _id: manifest-fallback
    _trigger: { _when: "$MIGRATION_DIR/capture/manifest.json records build.method != \"adapter\" (manifests or unavailable)" }
    _file: phases/discover/discover-manifests.md
  - _id: source-configs
    _trigger: { _always: true }
    _file: phases/discover/discover-configs.md
  - _id: vercel-api
    _trigger: { _always: true }
    _file: phases/discover/discover-api.md
  - _id: header-probe
    _trigger: { _when: "$MIGRATION_DIR/capture/manifest.json records probe.attempted == true" }
    _file: phases/discover/discover-probe.md
  - _id: coupling-score
    _trigger: { _always: true }
    _file: phases/discover/discover-coupling.md
  - _id: preflight-checks
    _trigger: { _always: true }
    _file: phases/discover/discover-preflight.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - discovery.json
  - coupling-score.json
  - preflight-findings.json
_advances_to: clarify
_interactive: false
_exec:
  _agent: rw
_re_entry_guard:
  _stale_if_completed: clarify
  _stale_artifact: clarify-answers.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: prescan
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "$MIGRATION_DIR/capture/manifest.json exists — if missing, load references/phases/discover/discover-capture.md in the MAIN window and run it (shell + network + token work happens there, per Orientation § Capture pre-work), then re-evaluate; fail only if capture cannot run"
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: [discovery.json, coupling-score.json, preflight-findings.json]
    _on_failure: _halt_and_inform
  - _validate_json: [discovery.json, coupling-score.json, preflight-findings.json]
    _on_failure: _halt_and_inform
  - _assert: "every finding in discovery.json and preflight-findings.json carries a confidence field in {LOW, MEDIUM, HIGH} and, when not HIGH, an upgrade_input field naming the specific missing input"
    _on_failure: _halt_and_inform
  - _assert: "preflight-findings.json contains an entry for all 10 named checks (M1, M2, B1-B4, S1, I1, O1, U1) regardless of which outcome will eventually be recommended - none are gated on a recommendation that doesn't exist yet"
    _on_failure: _halt_and_inform
  - _assert: "assessment-state.json findings map was updated with this phase's outputs and computed_from_inputs recorded per finding"
    _on_failure: _halt_and_inform
  - _assert: "no env var VALUES and no API token material appear anywhere in discovery.json, coupling-score.json, or preflight-findings.json — env data is key names only"
    _on_failure: _halt_and_inform
  - _assert: "coupling-score.json items each carry a confidence field in {LOW, MEDIUM, HIGH} and, when not HIGH, an upgrade_input — same discipline the existing assert applies to discovery.json and preflight-findings.json"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - assessment-report.html
---

# Phase 2: Full Discovery, Coupling Score, Pre-Flight Checks

Orchestrator that runs 7 independent fragments and one assembler. Signal-priority
fragments (`adapter-build` / `manifest-fallback`) are mutually exclusive — exactly
one runs, chosen by the capture manifest's `build.method`. `source-configs` and
`vercel-api` always run. `header-probe` runs only when the capture manifest
records probe captures. `coupling-score` and `preflight-checks` ALWAYS run,
unconditionally, regardless of what Recommend will later decide — this is the
concrete mechanism satisfying Requirement 6.2 ("compute all checks, filter at
render time").

**Execute ALL steps in order. Do not skip or deviate.**

---

## Capture Pre-Work (Main Window)

This phase's fragments are PARSE-ONLY and run in the dispatched `rw` worker,
which has no shell, no network, and must never see the Vercel token. All shell
and network work — the Adapter/manifest build, the GET-only Vercel API
enumeration, and the optional header probe — happens FIRST, in the MAIN window,
via `references/phases/discover/discover-capture.md`. It writes raw captures to
`$MIGRATION_DIR/capture/` with a `manifest.json` index; the third
`_precondition` above enforces this ordering (entry gate → capture pre-work →
dispatch). The token never enters any artifact, so it never reaches the worker.

Optional enrichment via Vercel's official MCP (runtime logs in lieu of a log
drain; access links in lieu of a test account) is described in
`discover-capture.md` § Optional Enrichment — read-only tools only, with the
purchase-tool caution stated there.

---

## Signal Priority (Requirement 4.1)

When multiple signal sources are available for the same finding, prioritize in
this order (highest authority first):

1. **Adapter API typed build output** (`discover-adapter.md`, Next.js >= 16.2,
   clean build) — the highest-authority signal; reads Vercel's own public
   contract.
2. **`.next` build manifests** (`discover-manifests.md`, fallback for Next.js <
   16.2 or a broken build) — same artifacts OpenNext v3 consumes.
3. **Source configs** (`discover-configs.md`) — `next.config.js`,
   `middleware.ts` + matcher.
4. **`vercel.json`** (also `discover-configs.md`) — headers, redirects,
   rewrites, function `maxDuration`/`memory`, regions, crons.
5. **Vercel REST API** (`discover-api.md`) — projects, deployments, env var
   names, domains, crons, storage enumeration, coarse usage.
6. **Header probing** (`discover-probe.md`) — confirmation-ONLY, never primary.

A finding that could be sourced from multiple levels should cite the
highest-priority source that actually produced it, and note if a lower-priority
source disagrees (a discrepancy is itself worth recording, at LOW-MEDIUM
confidence pending investigation).

---

## Step 0: Determine Warm-Start Recompute Scope

If `prescan.md` Step 1 determined a `newly_received` list (a warm re-entry with
new Tier 2/3 inputs), pass it to every fragment below. Each fragment that
contributes to `assessment-state.json.findings` (`discover-coupling.md`,
`discover-preflight.md`, and any finding-bearing fragment) checks its own
findings' `computed_from_inputs` against `newly_received` and short-circuits
unaffected findings — see each fragment's own "Recompute Short-Circuit" section
and `SKILL.md` § Assessment State Management.

---

## Step 1: Run Signal-Priority Fragments (Mutually Exclusive)

Read `$MIGRATION_DIR/capture/manifest.json` (written by the capture pre-work;
the capture step itself chose the path from `tier1-signals.json.next_version`
and `next_build_health`):

- If `build.method == "adapter"`: load
  `references/phases/discover/discover-adapter.md`.
- Otherwise (`"manifests"` or `"unavailable"`): load
  `references/phases/discover/discover-manifests.md`.

Exactly one of these runs. Never both.

---

## Step 2: Run Always-On Fragments

Load, in order:

1. `references/phases/discover/discover-configs.md`
2. `references/phases/discover/discover-api.md`

---

## Step 3: Run Conditional Header-Probe Fragment

If `capture/manifest.json` records `probe.attempted: true`: load
`references/phases/discover/discover-probe.md` to parse the captured headers.

Otherwise, skip this fragment entirely. (The capture pre-work only probes when
Tier 2's production URL + throwaway test account were supplied — never
speculatively, since probing behind auth walls is the probe's biggest blind
spot, Requirement 4.6.)

---

## Step 4: Run Unconditional Coupling Score + Pre-Flight Check Fragments

Load, in order:

1. `references/phases/discover/discover-coupling.md`
2. `references/phases/discover/discover-preflight.md`

Both ALWAYS run, regardless of Step 1-3 outcomes. Neither depends on which
outcome Recommend will eventually select.

---

## Step 5: Assemble

Load `references/phases/discover/discover-assemble.md` (the phase's assembler)
and follow it to combine all fragment contributions into `discovery.json`,
`coupling-score.json`, and `preflight-findings.json`, assign Confidence_Tier per
finding, write back to `assessment-state.json`, and run the completion gate.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter
and enforced per `INTERPRETER.md` § Gate protocol: re-read all three artifacts
from disk, run the mechanical checks and the `_assert` judgment checks (every
finding has a valid confidence + upgrade_input, all 10 Pre-Flight Checks present
unconditionally, `assessment-state.json` updated), then emit `GATE_FAIL` or
`HANDOFF_OK | phase=discover | artifacts=<files verified>` and advance.

---

## Step 6: Update Phase Status and Hand Off

Only after `HANDOFF_OK`, apply the phase-status update protocol
(`INTERPRETER.md` § The interpreter loop) — mark `phases.discover` completed and
advance per `_advances_to` — in the **same turn** as the output message.

Output to the founder — build the message from the artifacts' contents:

- "Discover phase complete. {signal source used}: adapter API build" or "manifest
  fallback"."
- "Coupling Score: {N} items inventoried."
- "Pre-Flight Checks: {N} findings at HIGH severity, {N} at MEDIUM, {N}
  informational."
- If any finding is sub-HIGH confidence: "{N} findings would upgrade with
  additional input — see the confidence-upgrade offers in the final report."

Format: "Discover phase complete. [summary] Next required step: Phase 3 —
Clarify. Load `references/phases/clarify/clarify.md` now."

---

## Error Handling

| Error Category                                                          | Behavior                                                                                                                                                 |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Capture-step adapter build failed despite PreScan's clean `next build`  | Manifest records `build.method: "manifests"` + `prescan_discrepancy: true`; fallback fragment runs and the discrepancy lands as a LOW-confidence finding |
| API capture rows partially failed (manifest `failed`/`skipped` entries) | Parse what succeeded; mark affected findings LOW confidence with `upgrade_input: "retry Vercel API access"`                                              |
| Probe captures show auth-wall/bot-challenge responses                   | Record the probe limitation per Requirement 4.6; do not treat as a fatal error                                                                           |

---

## Scope Boundary

**This phase covers Full Discovery, Coupling Score, and Pre-Flight Check
computation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Recommendation logic (that is Phase 4 — Recommend)
- Filtering or reframing Pre-Flight Check findings by outcome (that is Phase 5 —
  Report's job; this phase computes unconditionally)
- Clarify questions (that is Phase 3 — Clarify)
- Terraform/SST generation (that is the Scaffold checkpoint)

**Your ONLY job: Discover signals, compute Coupling Score and all 10 Pre-Flight
Checks unconditionally. Nothing else.**
