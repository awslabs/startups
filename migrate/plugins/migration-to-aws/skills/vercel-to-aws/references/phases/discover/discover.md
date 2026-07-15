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
    _trigger: { _when: "next_version >= 16.2 AND next build runs clean" }
    _file: phases/discover/discover-adapter.md
  - _id: manifest-fallback
    _trigger: { _when: "next_version < 16.2 OR next build does not run clean" }
    _file: phases/discover/discover-manifests.md
  - _id: source-configs
    _trigger: { _always: true }
    _file: phases/discover/discover-configs.md
  - _id: vercel-api
    _trigger: { _always: true }
    _file: phases/discover/discover-api.md
  - _id: header-probe
    _trigger: { _when: "a production URL and test account were provided (Tier 2)" }
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
_forbids_files:
  - README.md
  - "terraform/**"
  - assessment-report.html
---

# Phase 2: Full Discovery, Coupling Score, Pre-Flight Checks

Orchestrator that runs 7 independent fragments and one assembler. Signal-priority
fragments (`adapter-build` / `manifest-fallback`) are mutually exclusive — exactly
one runs, chosen by Next.js version + build health. `source-configs` and
`vercel-api` always run. `header-probe` runs only when Tier 2's production URL +
test account were supplied. `coupling-score` and `preflight-checks` ALWAYS run,
unconditionally, regardless of what Recommend will later decide — this is the
concrete mechanism satisfying Requirement 6.2 ("compute all checks, filter at
render time").

**Execute ALL steps in order. Do not skip or deviate.**

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

Evaluate `tier1-signals.json.next_version` and `next_build_health`:

- If `next_version >= "16.2.0"` AND `next_build_health == "clean"`: load
  `references/phases/discover/discover-adapter.md`.
- Otherwise: load `references/phases/discover/discover-manifests.md`.

Exactly one of these runs. Never both.

---

## Step 2: Run Always-On Fragments

Load, in order:

1. `references/phases/discover/discover-configs.md`
2. `references/phases/discover/discover-api.md`

---

## Step 3: Run Conditional Header-Probe Fragment

If Tier 2's production URL + throwaway test account were supplied (check
`assessment-state.json.inputs_received.tier2.production_url_and_test_account.received`):
load `references/phases/discover/discover-probe.md`.

Otherwise, skip this fragment entirely — do not attempt header probing without a
test account, since probing behind auth walls is the probe's biggest blind spot
(Requirement 4.6).

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

| Error Category                                                     | Behavior                                                                                                     |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Adapter API build fails mid-run despite a prior clean `next build` | Fall back to `discover-manifests.md`; record the discrepancy as a LOW-confidence finding                     |
| Vercel API enumeration partially fails                             | Record what succeeded; mark affected findings LOW confidence with `upgrade_input: "retry Vercel API access"` |
| Header probe blocked by an auth wall                               | Record the probe limitation per Requirement 4.6; do not treat as a fatal error                               |

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
