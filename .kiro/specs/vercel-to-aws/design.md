# Design Document: Vercel-to-AWS Migration Skill

## Overview

`vercel-to-aws` is a new skill under `migrate/plugins/migration-to-aws/skills/`, sitting alongside `gcp-to-aws` and `heroku-to-aws`. It is driven by the same plugin-shared DSL interpreter (`skills/shared/dsl/INTERPRETER.md`, vendored byte-identical into `references/vendored/dsl/`) — phase files carry YAML frontmatter (`_phase`, `_fragments`, `_assemble`, `_produces`, `_preconditions`/`_postconditions`, `_knowledge`, `_exec`) and the interpreter loop drives execution exactly as it does for the other two skills.

This document resolves the four open design items identified during spec review:

1. **Phase/fragment breakdown** — mapping the spec's conceptual pipeline onto concrete DSL phase files.
2. **Assessment state ledger** — a skill-owned resumability model beyond `.phase-status.json`, supporting partial recompute.
3. **Recommendation engine** — the §8 precedence-rule cascade, designed as a reusable decision-table pattern (same shape as `skills/shared/org-recommendation-engine.md`).
4. **Validator adaptation** — porting `scripts/validate-migration-report.py` to a Vercel-specific sibling script.

Everything else (knowledge tables for peripheral mappings, scaffold conditional artifacts, checkpoint semantics for Scaffold) follows existing precedent directly and is noted only where it affects the four items above.

## 1. Phase / Fragment Breakdown

The spec's conceptual pipeline (`Collect Tier 1 -> Pre-Scan -> Clarify -> Full Discover -> Coupling Score -> Pre-Flight Checks -> Recommendation -> Scaffold`) collapses onto **5 backbone phases + 1 checkpoint phase**. Coupling Score and Pre-Flight Checks are not separate backbone phases — per Requirement 6.2, they must compute unconditionally *before* Recommendation exists, so they are fragments of Discover's assembler, matching how GCP's optional-section pattern (`validate-artifacts.md`) computes-then-conditionally-renders rather than gating computation on a later phase.

```
prescan (_init) --> discover --> clarify --> recommend --> report --> [complete]
                                                                 \
                                                                  scaffold (checkpoint, opt-in)
```

### 1.1 `prescan` (backbone, entry phase)

```yaml
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
_interactive: false
_exec:
  _agent: rw
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
  - assessment-report.html
```

- `prescan-collect.md` — Requirement 1: validates the three Tier 1 preconditions (repo access + `next build` health check, read-only Vercel API token, project scope), requests the token with the least-privilege statement per Requirement 1.7, and performs `_init` state setup (creates `.migration/`, `.phase-status.json`, **and** the skill-owned `assessment-state.json` — see §2).
- `prescan-scan.md` — Requirement 2: the build-free pass (`package.json`, lockfile census, `middleware.ts` existence, `vercel.json` presence, Vercel API project enumeration). Explicitly forbidden from running `next build` — that is Discover's job.
- `prescan-assemble.md` — merges both fragments into `tier1-signals.json`, seeds `assessment-state.json.inputs_received.tier1`, and hands off.

This mirrors `heroku-to-aws/discover.md`'s role as the `_init: true` entry phase with `_exec: rw` (file-heavy, non-interactive, exactly the profile `_exec` targets).

### 1.2 `discover` (backbone)

```yaml
_phase: discover
_title: "Full Discovery, Coupling Score, Pre-Flight Checks"
_requires_phase: prescan
_input:
  - tier1-signals.json
  - assessment-state.json
_knowledge:
  - { file: knowledge/preflight-checks.json, _when: "always — defines the M1/M2/B1-B4/S1/I1/O1/U1 check table" }
  - { file: knowledge/coupling-weights.json, _when: "always — defines Coupling_Score item weights and detection methods" }
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
  - _assert: "preflight-findings.json contains an entry for all 10 named checks (M1, M2, B1-B4, S1, I1, O1, U1) regardless of which outcome will eventually be recommended — none are gated on a recommendation that doesn't exist yet"
    _on_failure: _halt_and_inform
  - _assert: "assessment-state.json findings map was updated with this phase's outputs and computed_from_inputs recorded per finding"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - assessment-report.html
```

- **Signal-priority fragments** (`discover-adapter.md` / `discover-manifests.md`) are mutually exclusive alternatives gated by the same `_when` pattern `design.md` uses for its EKS branch — exactly one runs, chosen by Next.js version + build health (Requirement 4.1-4.2).
- `discover-configs.md`, `discover-api.md` always run (source configs and Vercel REST API are always-available signal classes).
- `discover-probe.md` is conditionally triggered only when Tier 2's throwaway test account was supplied — confirmation-only, per Requirement 4.1 (header probing is never primary).
- `discover-coupling.md` and `discover-preflight.md` always run and are unconditional by design (Requirement 6.2) — this is the concrete mechanism for "compute all checks, filter at render time." They are **fragments of Discover**, not a later phase, specifically so nothing about their execution depends on Recommendation's output.
- `discover-assemble.md` merges everything, and is also the point where the assembler writes back into `assessment-state.json` (see §2.3 — recompute-on-new-input hooks into this same assembler logic on a warm re-entry).

### 1.3 `clarify` (backbone, interactive)

```yaml
_phase: clarify
_title: "Clarify — Ask What Discovery Can't Answer"
_requires_phase: discover
_input:
  - discovery.json
  - tier1-signals.json
_interactive: true
_fragments:
  - _id: ask
    _trigger: { _always: true }
    _file: phases/clarify/clarify-ask.md
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - clarify-answers.json
_advances_to: recommend
_re_entry_guard:
  _stale_if_completed: recommend
  _stale_artifact: recommendation.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: clarify-answers.json
    _on_failure: _halt_and_inform
  - _validate_json: clarify-answers.json
    _on_failure: _halt_and_inform
  - _assert: "every answer entry has prompt, answer, and design_consequence fields populated (design_consequence may state 'not yet determined — feeds recommend phase rule N' when the consequence depends on a rule that hasn't run)"
    _on_failure: _halt_and_inform
  - _assert: "no question was asked whose answer PreScan or Discover already determined (e.g. no middleware question when tier1-signals.json.has_middleware is false)"
    _on_failure: _halt_and_inform
  - _assert: "the Next.js-upgrade question, if asked, is not gated as a precondition for any other question or for phase completion"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - assessment-report.html
```

Interactive phases cannot carry `_exec` (the grammar's own rule — a dispatched worker cannot converse), so this runs inline in the main window, same as `heroku-to-aws/clarify.md`. `clarify-ask.md` implements Requirement 3's fixed question set, consulting `tier1-signals.json` + `discovery.json` first to skip anything already answered (Requirement 2.3). Each answer is written with `prompt` + `design_consequence` per Requirement 3.2 — this is the exact shape `assessment-state.json.clarify_answers` needs (§2.2).

### 1.4 `recommend` (backbone)

```yaml
_phase: recommend
_title: "Apply Precedence Rules -> Outcome"
_requires_phase: clarify
_input:
  - discovery.json
  - coupling-score.json
  - preflight-findings.json
  - clarify-answers.json
_knowledge:
  - { file: references/shared/vercel-recommendation-engine.md, _when: "always" }
_fragments:
  - _id: apply-rules
    _trigger: { _always: true }
    _file: phases/recommend/recommend-rules.md
_assemble:
  _file: phases/recommend/recommend-assemble.md
_produces:
  - recommendation.json
_advances_to: report
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_file_exists: [discovery.json, coupling-score.json, preflight-findings.json, clarify-answers.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: recommendation.json
    _on_failure: _halt_and_inform
  - _validate_json: recommendation.json
    _on_failure: _halt_and_inform
  - _assert: "recommendation.outcome is one of {A, B, C, stay}; recommendation.fired_rule names exactly one of the 4 precedence rules; recommendation.tiebreak is true only when rule 4 fired"
    _on_failure: _halt_and_inform
  - _assert: "if outcome is C, recommendation.separable is true; if separable is false, outcome MUST be 'stay'"
    _on_failure: _halt_and_inform
  - _assert: "if outcome is C, recommendation.backend_shape is one of {A-shaped, B-shaped, null} and is never used to imply a partial OpenNext/SST scaffold"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - assessment-report.html
```

`recommend-rules.md` is a thin orchestrator that loads and follows `references/shared/vercel-recommendation-engine.md` (§3 below) — the actual decision table lives there, not duplicated inline, matching how `design.md` in Heroku loads `design-mapping.md` rather than inlining the mapping logic.

### 1.5 `report` (backbone)

```yaml
_phase: report
_title: "Write & Validate the Assessment Report"
_requires_phase: recommend
_input:
  - discovery.json
  - coupling-score.json
  - preflight-findings.json
  - clarify-answers.json
  - recommendation.json
  - assessment-state.json
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
  - _check_phase_completed: recommend
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: assessment-report.html
    _on_failure: _halt_and_inform
  - _assert: "the report-render.md validator invocation (scripts/validate-assessment-report.py) exited 0 within the 2-retry cap; the shell exit code was branched on, not stdout text pattern-matching"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
```

`report-assemble.md` owns the retry-cap loop (Requirement 12.3-12.4) and the exit-code branch (§4 below). This is prose-driven exactly like GCP's `generate.md` Step 4 — no new DSL primitive.

### 1.6 `scaffold` (checkpoint)

```yaml
_phase: scaffold
_title: "Optional IaC Scaffold"
_kind: checkpoint
_requires_phase: report
_input:
  - recommendation.json
_trigger: { _when: "the founder opts in to a scaffold at the post-report checkpoint" }
_fragments:
  - _id: outcome-a
    _trigger: { _when: "recommendation.outcome is 'A', or 'C' with backend_shape 'A-shaped'" }
    _file: phases/scaffold/scaffold-opennext.md
  - _id: outcome-b
    _trigger: { _when: "recommendation.outcome is 'B', or 'C' with backend_shape 'B-shaped'" }
    _file: phases/scaffold/scaffold-fargate.md
  - _id: peripherals
    _trigger: { _always: true }
    _file: phases/scaffold/scaffold-peripherals.md
_assemble:
  _file: phases/scaffold/scaffold-assemble.md
_produces:
  - { file: "sst.config.ts", _when: "outcome-a fragment fired" }
  - { file: "terraform/", _when: "any fragment fired" }
_preconditions:
  - _check_phase_completed: report
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: "terraform/README.md"
    _on_failure: _warn_and_skip
_forbids_files:
  - "README.md"
```

This is off-backbone (`_kind: checkpoint`, no `_advances_to`), same shape as `heroku-to-aws/feedback.md`. The outcome-a/outcome-b fragments are mutually exclusive per Requirement 8.2-8.4 (never both SST and a from-scratch Next.js Terraform stack); `scaffold-peripherals.md` always runs and applies the Requirement 8.6 mapping table (Blob->S3, Cron->EventBridge Scheduler, etc.) as a `knowledge/peripheral-mappings.json` lookup, identical in spirit to `fast-path-addons.json`.

---

## 2. Assessment State Ledger

`.phase-status.json` (schema: `references/vendored/state/phase-status.schema.json`) stays untouched and skill-agnostic — it only ever tracks `pending`/`in_progress`/`completed` per phase. It cannot express "this one finding's confidence changed because a new input arrived," so `vercel-to-aws` owns a second, sibling file: **`$MIGRATION_DIR/assessment-state.json`**, schema at `skills/vercel-to-aws/references/state/assessment-state.schema.json`.

The two files are read/written independently (Requirement 11.5) — a corrupt `assessment-state.json` never fails the `.phase-status.json` validation path in `INTERPRETER.md` § State-file validation, and vice versa. The `report` phase's `_postconditions` never inspect `assessment-state.json` structure beyond existence; the `discover`/`clarify` assemblers own its content.

### 2.1 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "assessment-state.json",
  "description": "Skill-owned resumability ledger for vercel-to-aws. Tracks inputs received, per-finding confidence, and clarify answers with their design consequence, so a re-invocation can recompute only what a new input affects. Independent of .phase-status.json.",
  "type": "object",
  "required": ["schema_version", "migration_id", "last_updated", "inputs_received", "findings", "clarify_answers", "report_history"],
  "properties": {
    "schema_version": { "const": "1.0" },
    "migration_id": { "type": "string" },
    "last_updated": { "type": "string", "format": "date-time" },
    "inputs_received": {
      "type": "object",
      "required": ["tier1", "tier2", "tier3"],
      "properties": {
        "tier1": { "$ref": "#/definitions/tierInputMap" },
        "tier2": { "$ref": "#/definitions/tierInputMap" },
        "tier3": { "$ref": "#/definitions/tierInputMap" }
      }
    },
    "findings": {
      "type": "object",
      "description": "Keyed by a stable finding_id (e.g. 'preflight.M1', 'coupling.isr', 'discovery.traffic_shape').",
      "additionalProperties": { "$ref": "#/definitions/findingRecord" }
    },
    "clarify_answers": {
      "type": "object",
      "description": "Keyed by question id (e.g. 'Q1_traffic_shape').",
      "additionalProperties": { "$ref": "#/definitions/clarifyAnswerRecord" }
    },
    "report_history": {
      "type": "array",
      "items": { "$ref": "#/definitions/reportHistoryEntry" }
    }
  },
  "definitions": {
    "tierInputMap": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["received", "received_at"],
        "properties": {
          "received": { "type": "boolean" },
          "received_at": { "type": ["string", "null"], "format": "date-time" },
          "source": { "type": "string", "description": "e.g. 'log_drain_export.csv', 'vercel_api_token'" }
        }
      }
    },
    "findingRecord": {
      "type": "object",
      "required": ["value", "confidence", "computed_at", "computed_from_inputs"],
      "properties": {
        "value": {},
        "confidence": { "enum": ["LOW", "MEDIUM", "HIGH"] },
        "upgrade_input": { "type": ["string", "null"] },
        "computed_at": { "type": "string", "format": "date-time" },
        "computed_from_inputs": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Input keys (matching inputs_received leaf keys) this finding's value depends on. Drives selective recompute — see 2.3."
        }
      }
    },
    "clarifyAnswerRecord": {
      "type": "object",
      "required": ["prompt", "answer", "design_consequence", "answered_at"],
      "properties": {
        "prompt": { "type": "string" },
        "answer": { "type": "string" },
        "design_consequence": { "type": "string" },
        "answered_at": { "type": "string", "format": "date-time" }
      }
    },
    "reportHistoryEntry": {
      "type": "object",
      "required": ["generated_at", "recommendation_snapshot"],
      "properties": {
        "generated_at": { "type": "string", "format": "date-time" },
        "recommendation_snapshot": { "type": "object" },
        "diff_from_previous": {
          "type": ["array", "null"],
          "items": {
            "type": "object",
            "properties": {
              "finding_id": { "type": "string" },
              "previous_confidence": { "enum": ["LOW", "MEDIUM", "HIGH"] },
              "new_confidence": { "enum": ["LOW", "MEDIUM", "HIGH"] },
              "previous_value": {},
              "new_value": {}
            }
          }
        }
      }
    }
  }
}
```

### 2.2 Who writes what, and when

| Writer | Fields touched |
|---|---|
| `prescan-assemble.md` | `inputs_received.tier1.*`, initializes empty `findings`/`clarify_answers`/`report_history` |
| `discover-assemble.md` | `inputs_received.tier2.*` / `.tier3.*` (whichever were supplied), all `findings` entries with `computed_from_inputs` populated |
| `clarify-assemble.md` | `clarify_answers.*` |
| `recommend-assemble.md` | may add a synthetic finding entry for `recommendation.fired_rule` (so the traceability appendix in Requirement 10 has one place to read it from) |
| `report-assemble.md` | appends one `report_history` entry per successful report write |

### 2.3 Recompute-on-new-input (Requirement 11.2-11.4)

On a warm start, `prescan-collect.md` re-reads `assessment-state.json.inputs_received` before re-scanning the workspace/API. For each tier-2/tier-3 input:

1. If `inputs_received.<tier>.<input>.received` is already `true` and the underlying source hasn't changed, **skip re-collecting it**.
2. If a previously-`false` input is now present (e.g. a log drain export now exists at the expected path), mark it `received: true` and record it in a `newly_received` list passed forward to `discover`.

`discover-assemble.md` uses `newly_received` to decide what to recompute: it walks `assessment-state.json.findings`, and for any finding whose `computed_from_inputs` intersects `newly_received`, it re-runs only that finding's originating fragment (e.g. a new log drain re-triggers the traffic-shape portion of `discover-coupling.md`'s fragment, not the whole Discover phase). Findings whose `computed_from_inputs` does not intersect `newly_received` are left untouched — their `value`/`confidence`/`computed_at` carry over verbatim from the prior run. This is the mechanism that satisfies Requirement 11.3 without needing `_re_entry_guard`'s blunt "reset everything downstream" behavior; `_re_entry_guard` still applies at the `.phase-status.json` level (Discover as a whole is either `completed` or not), but partial recompute happens *inside* an already-`completed` Discover phase's re-entry, gated by the user confirmation `_re_entry_guard` already requires.

`report-assemble.md` computes the diff for Requirement 11.4 by comparing the new `findings` snapshot against `report_history[-1].recommendation_snapshot` plus the finding values at that time, emitting `diff_from_previous` as a list of changed `finding_id`s.

**Design note (Assessment-State validation is `_assert`-only):** No new closed-vocabulary check kind is needed. `_check_file_exists` / `_validate_json` cover presence/JSON-validity of `assessment-state.json`, and the "is X finding's `computed_from_inputs` intersecting the newly-received set" recompute logic is judgment prose the interpreter evaluates at runtime — the same `_assert` escape hatch every skill already uses for non-mechanically-verifiable predicates (e.g. Heroku's Property-16-style total-equals-sum checks). This keeps the resumability model additive to the DSL rather than requiring a grammar change.

---

## 3. Recommendation Engine (`references/shared/vercel-recommendation-engine.md`)

Modeled directly on `skills/shared/org-recommendation-engine.md`'s shape (signal table -> ordered decision steps -> confidence resolution -> output schema -> worked examples), but a **precedence cascade that stops at first match** (spec §8) rather than a "collect all matching reasons" scorer — Requirement 7.1 requires the engine to evaluate rules in a fixed order and halt at the first that fires, which is a different algorithm shape than the org engine's "gather every matching reason across all rules." This distinction is deliberate and should not be flattened to match the org engine's collect-all-reasons style during implementation.

### 3.1 Signal Sources

| Signal | Artifact | Key path |
|---|---|---|
| Preview dependence | `clarify-answers.json` | `Q4_preview_dependence.answer` |
| Separable AWS-bound surface | `discovery.json` | `peripherals[]` non-empty OR `api_routes[]` non-empty OR `backend_service_detected` |
| Lambda-hostile workload | `discovery.json` + `clarify-answers.json` | `route_analysis.long_running`, `route_analysis.websockets`, `Q3_devops_bandwidth.answer` mentioning an existing separate API service |
| Traffic shape | `clarify-answers.json` (fallback) or `discovery.json.log_drain_analysis` (authoritative) | `traffic_shape.peak_to_median_ratio`, `traffic_shape.confidence` |
| Coupling (ISR/edge) | `coupling-score.json` | `items[].weight` for `isr`, `edge_middleware`, `edge_runtime_routes` |
| Team size / debuggability preference | `clarify-answers.json` | `Q3_devops_bandwidth.answer` |

### 3.2 Decision Steps (evaluated top-to-bottom, first match wins)

**Step 1 — Preview dependence + separability (Requirement 7.1 rule 1).**

| Condition | Result |
|---|---|
| `Q4_preview_dependence.answer` indicates previews are load-bearing AND a separable surface exists | `outcome: C`, `separable: true`, `backend_shape` recurses to Step 2/3 evaluated against the *backend* signals only |
| `Q4_preview_dependence.answer` indicates previews are load-bearing AND no separable surface exists | `outcome: stay`, `separable: false` |
| Previews are not load-bearing | fall through to Step 2 |

If Step 1 resolves to `C`, re-run Steps 2-3 below using only the backend-relevant subset of signals (route analysis, DB/queue peripherals) to set `backend_shape` to `A-shaped` or `B-shaped` — never re-running them against the full Next.js app, since under Outcome C the Next.js app itself never leaves Vercel (Requirement 7.2).

**Step 2 — Lambda-hostile workload (rule 2).**

| Condition | Result |
|---|---|
| Websockets, long-running jobs (>15 min), sustained heavy SSR, or an existing separate API service detected | `outcome: B` (or `backend_shape: B-shaped` if reached via the Step-1 recursion) |
| None detected | fall through to Step 3 |

**Step 3 — Traffic shape + coupling (rule 3).**

| Condition | Result |
|---|---|
| Spiky traffic AND high ISR/edge coupling AND small team | `outcome: A` |
| Sustained traffic (peak:median < ~3:1) OR team states a debuggability preference | `outcome: B` |
| Neither condition clearly matches | fall through to Step 4 |

**Step 4 — Tiebreak (rule 4).**

| Condition | Result |
|---|---|
| Traffic-shape confidence is LOW (no log drain, vague Clarify answer) | `outcome: [A, B]` (both), `tiebreak: true`, `resolving_input: "14 days of log drain data"` |

### 3.3 Output Schema (`recommendation.json`)

```json
{
  "outcome": "A" | "B" | "C" | "stay" | ["A", "B"],
  "fired_rule": 1 | 2 | 3 | 4,
  "tiebreak": false,
  "separable": true,
  "backend_shape": "A-shaped" | "B-shaped" | null,
  "confidence": "high" | "medium" | "low",
  "reasons": ["..."],
  "resolving_input": null
}
```

Constraints (enforced by `recommend`'s `_postconditions`, mirroring the org engine's invariant style):

- `outcome` is `["A","B"]` **only if** `tiebreak == true`; otherwise it is a single string.
- `backend_shape` is non-null **only if** `outcome == "C"`.
- `separable` is present **only if** `outcome ∈ {"C", "stay"}`.
- `fired_rule == 4` **iff** `tiebreak == true`.
- EKS and Amplify are never valid `outcome` values (Requirement 7.4-7.5) — they are report-prose callouts, not recommendation-engine outputs.

### 3.4 Fallback Behavior

Same principle as the org engine: never block on missing signals.

| Scenario | Behavior |
|---|---|
| `Q4_preview_dependence` unanswered | Treat as "not load-bearing," fall through to Step 2, note in `reasons` that this assumption was made by default |
| No log drain and vague traffic-shape answer | Confidence `low`, proceed to Step 4 tiebreak rather than guessing |
| `discovery.json.peripherals` unreadable | Treat separability as `false` (fail toward the more conservative "stay" outcome, never toward silently assuming a migration path exists) |

---

## 4. Validator Adaptation

`migrate/plugins/migration-to-aws/scripts/validate-migration-report.py` (currently on branch `pr-78` / `fix/pr78-review-comments-v2`, not yet on `main`) is ported to a sibling script rather than generalized in place — the two report structures (GCP's infra/AI/billing tracks vs. Vercel's outcome-filtered pre-flight findings) have different enough section sets that a shared script would need a config layer neither skill currently has appetite for. This can be revisited post-v1 if a third skill needs the same script.

### 4.1 New script: `scripts/validate-assessment-report.py`

Same CLI contract and exit-code semantics as the original:

```bash
python3 "$PLUGIN_ROOT/scripts/validate-assessment-report.py" \
  "$MIGRATION_DIR/assessment-report.html" \
  --recommendation "$MIGRATION_DIR/recommendation.json" \
  --preflight-findings "$MIGRATION_DIR/preflight-findings.json" \
  --migration-dir "$MIGRATION_DIR"
```

| Exit code | Meaning | Action |
|---|---|---|
| `0` | pass | proceed |
| `1` | fail-with-errors | rename to `assessment-report.incomplete.html`, surface failures, retry (cap: 2 additional attempts per Requirement 12.3-12.4) |
| anything else | validator did not run | tell the user, never treat as pass |

This is the exact table already documented in `validate-migration-report.md` — copied, not reinvented.

### 4.2 Section IDs (replaces GCP's `REQUIRED_SECTION_IDS`)

| Section ID | Required? | Maps to |
|---|---|---|
| `exec-verdict` | always | Requirement 9.2 verdict banner |
| `exec-tiebreak` | conditional — `recommendation.tiebreak == true` | Requirement 9.2 side-by-side section |
| `inputs-received` | conditional — any finding below HIGH | Requirement 9.3 |
| `what-you-gain` | always | Requirement 9.1 |
| `what-you-lose` | always | Requirement 9.1 |
| `coupling-score` | always | Requirement 5 |
| `preflight-findings` | always | Requirement 6.3 (filtered/reframed) |
| `appendix-m1` | conditional — `tier1-signals.json.has_middleware == true` | Requirement 9.4 |
| `decision-traceability` | always | Requirement 10.1 |
| `out-of-scope` | conditional — outcome is `C` or `stay` | Requirement 9.5 |
| `next-steps` | always, rendered as `<ol>` | Requirement 9.1 |

### 4.3 New checks beyond the ported set

The original 16 checks (section IDs exactly once, TOC/anchor integrity, no stubs, no placeholders, readability/reader-vocabulary, fixture-bleed) port over unchanged in mechanism. Two are re-specified for Vercel's vocabulary:

| Check | PASS when |
|---|---|
| Reader vocabulary (replaces GCP's check 14) | No pre-flight check ID (`M1`, `M2`, `B1`-`B4`, `S1`, `I1`, `O1`, `U1`), no `*.json` filename, no Terraform resource ID (`aws_*.*`), and no literal "route disposition" inside any `exec-*` section |
| Cost-labeling (new) | Every `$`-prefixed or dollar-amount string anywhere in the document body is adjacent to (within the same sentence or table cell as) the phrase "estimated monthly" — enforced even for U1's cost-driver figures per Requirement 9.6 |
| Fixture bleed (re-pointed) | Reference canary is a new constant (e.g. a fixture migration ID distinct from GCP's `0611-0606`) scoped to the Vercel fixture; same mechanism as `_validate_fixture_bleed` |

### 4.4 Fixtures

Per Requirement 12.7, mirror the existing pattern:

- `fixtures/assessment-report-reference.html` — a golden reference report (built from a reference startup) that passes.
- `fixtures/assessment-report-stub.html` — an inverse fixture that deliberately fails with actionable errors (missing sections, a leaked `M1` in the exec flow, an un-labeled dollar figure).
- Both wired into the same CI regression job that already runs `tests/test_validate_migration_report.py`, as a sibling `tests/test_validate_assessment_report.py`.

### 4.5 What is explicitly not done in v1

Per the spec's own out-of-scope note: no new closed-vocabulary `_check_*` kind is added to `INTERPRETER.md`. The validator remains invoked via phase prose in `report-render.md` / `report-assemble.md`, exactly as GCP's `generate.md` Step 4 invokes its validator. Promoting "run script, branch on exit code" into a canonical DSL primitive (available to both skills without prose duplication) is a reasonable v2 cleanup once a third skill needs the same pattern, not a v1 requirement.

---

## File Structure

```
skills/vercel-to-aws/
├── SKILL.md
├── references/
│   ├── phases/
│   │   ├── prescan/
│   │   │   ├── prescan.md
│   │   │   ├── prescan-collect.md
│   │   │   ├── prescan-scan.md
│   │   │   └── prescan-assemble.md
│   │   ├── discover/
│   │   │   ├── discover.md
│   │   │   ├── discover-adapter.md
│   │   │   ├── discover-manifests.md
│   │   │   ├── discover-configs.md
│   │   │   ├── discover-api.md
│   │   │   ├── discover-probe.md
│   │   │   ├── discover-coupling.md
│   │   │   ├── discover-preflight.md
│   │   │   └── discover-assemble.md
│   │   ├── clarify/
│   │   │   ├── clarify.md
│   │   │   ├── clarify-ask.md
│   │   │   └── clarify-assemble.md
│   │   ├── recommend/
│   │   │   ├── recommend.md
│   │   │   ├── recommend-rules.md
│   │   │   └── recommend-assemble.md
│   │   ├── report/
│   │   │   ├── report.md
│   │   │   ├── report-render.md
│   │   │   └── report-assemble.md
│   │   └── scaffold/
│   │       ├── scaffold.md
│   │       ├── scaffold-opennext.md
│   │       ├── scaffold-fargate.md
│   │       ├── scaffold-peripherals.md
│   │       └── scaffold-assemble.md
│   ├── shared/
│   │   └── vercel-recommendation-engine.md
│   ├── state/
│   │   └── assessment-state.schema.json
│   └── vendored/                          # synced from skills/shared/, same as heroku-to-aws
│       ├── dsl/INTERPRETER.md
│       └── state/phase-status.schema.json
├── knowledge/
│   ├── preflight-checks.json
│   ├── coupling-weights.json
│   └── peripheral-mappings.json
scripts/
└── validate-assessment-report.py           # sibling to validate-migration-report.py
fixtures/
├── assessment-report-reference.html
└── assessment-report-stub.html
tests/
└── test_validate_assessment_report.py
```

## Resolved Design Decisions

The three items previously open at this point are resolved as follows.

### 1. Fragment-level partial recompute granularity — resolved: internal short-circuit, not finer fragments

A fragment (e.g. `discover-coupling.md`) keeps computing its full finding family in one file, but on a warm re-entry it internally short-circuits per finding rather than being split into one-fragment-per-finding. Concretely, each fragment's prose gets a standard preamble:

> Before computing any finding this fragment owns, check whether `assessment-state.json.findings.<finding_id>.computed_from_inputs` intersects the `newly_received` list passed in from `prescan-assemble.md`. If a given finding's dependency set does NOT intersect `newly_received`, copy its prior `value`/`confidence`/`computed_at` forward unchanged and skip recomputation for that finding only. If it DOES intersect, recompute normally.

This is a per-fragment prose contract, not a new frontmatter key — `_fragments` stays exactly as declared in §1.2, one entry per signal-class fragment (`discover-adapter`, `discover-coupling`, `discover-preflight`, etc.). The alternative (one fragment per finding) was rejected: Coupling Score alone has 8+ items and Pre-Flight Checks has 10 named checks, so finding-per-fragment would produce ~20 near-empty fragment files with no independent `_trigger` value, which fails the DSL's own "fragments are independent units of work" intent without buying any real isolation. Short-circuiting inside the existing fragment boundary keeps the file count in line with `heroku-to-aws`'s discover fragments (3 files) while still satisfying Requirement 11.3's per-finding recompute granularity.

### 2. `report_history` growth cap — resolved: cap at 5 entries, FIFO eviction

`assessment-state.json.report_history` is capped at the 5 most recent entries. `report-assemble.md` appends the new entry then, if length exceeds 5, drops the oldest (index 0) before writing. Enforced as an `_assert` in `report`'s `_postconditions`:

```yaml
_assert: "assessment-state.json.report_history has at most 5 entries after this write"
_on_failure: _halt_and_inform
```

Rationale: Requirement 11.4 only requires a diff against the *immediately prior* report, so nothing downstream reads deeper into history than index `-2`; 5 is generous headroom without letting the ledger grow unbounded across a long-lived repo.

### 3. `scripts/validate-migration-report.py` merge status — resolved: already on `main`

Confirmed directly against `origin/main` (commit `f6f23f2`, "Enforce comprehensive migration HTML reports with post-write validation (#78)"): `scripts/validate-migration-report.py`, `skills/gcp-to-aws/references/shared/validate-migration-report.md`, and both fixtures are live on `main` today, at the paths §4 already assumes. No branch dependency remains — `validate-assessment-report.py` can be authored as a proper sibling from day one of implementation.
