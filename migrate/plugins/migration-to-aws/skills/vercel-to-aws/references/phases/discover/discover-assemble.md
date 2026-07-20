---
_assemble: discover-assemble
_of_phase: discover
_reads:
  - adapter-build OR manifest-fallback (route_disposition, adapter_metadata|manifest_metadata)
  - source-configs (next_config, middleware_analysis, vercel_json_config, streaming_routes_with_empty_body_risk)
  - vercel-api (deployments, env_var_names, domains, storage_integrations, peripherals, api_routes, backend_service_detected, usage_metrics)
  - header-probe (header_probe_results, probe_limitations) - when triggered
  - coupling-score (items[], phased_migration_candidate) - unconditional
  - preflight-checks (checks[]) - unconditional
_knowledge:
  - { file: knowledge/preflight-checks.json, _when: "always - cross-reference for completeness check" }
_produces:
  - discovery.json
  - coupling-score.json
  - preflight-findings.json
---

# Discover Phase: Assembler

> Combines all 7 fragment contributions into three artifacts: `discovery.json`
> (general findings), `coupling-score.json` (the Coupling Score inventory), and
> `preflight-findings.json` (all 10 Pre-Flight Checks). Assigns Confidence_Tier
> per finding, writes back to `assessment-state.json`, and runs the completion
> gate. This is the SINGLE creator of all three artifacts.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Assign Confidence_Tier to Every Finding (Requirement 4.4-4.5)

For every finding contributed by any fragment, assign a `confidence` of `LOW`,
`MEDIUM`, or `HIGH`:

- **HIGH** applies in two cases: (a) the finding is backed by log-drain data,
  invoice data, or the Adapter API's typed build output (the highest-authority
  signal per Requirement 4.1) — these are Requirement 4.4's explicitly named
  HIGH-eligible sources for findings whose true value depends on RUNTIME
  behavior (traffic patterns, actual cost, framework-typed routing decisions);
  or (b) the finding is a deterministic, unambiguous fact read directly from a
  single source of truth with no interpretation or heuristic involved (e.g. a
  literal lockfile count, a direct boolean read of a dependency's presence in
  `package.json`, an unambiguous field read from `vercel.json`). Case (b)
  covers facts that Requirement 4.4's "which inputs the finding rests on"
  framing does not really apply to — no additional input could make an
  already-100%-certain source-code fact more certain, so gating it at MEDIUM
  would misrepresent it as less certain than it is. Do NOT use case (b) for
  anything involving interpretation (e.g. each entry in
  `middleware_analysis.per_matcher_pattern[]` — the authoritative middleware
  classification field, per pattern — is a judgment call between behavior
  categories, not a direct read — MEDIUM; the same applies to the collapsed
  top-level `middleware_analysis.classification` on the rare occasion it is
  used instead),
  a build-output ROUTING DECISION under Next.js < 16.2 (the manifest-fallback
  path is explicitly a lower-authority signal than the Adapter API per
  Requirement 4.1 — MEDIUM even though the manifest itself is unambiguous), or
  anything SIMULATED/sourced from an API call rather than a direct file read.
- **LOW** applies when a finding rests SOLELY on header probes
  (`discover-probe.md`) or coarse usage aggregates
  (`discover-api.md`'s `usage_metrics` without a log drain).
- **MEDIUM** applies to everything else (source-config/manifest-fallback-derived
  findings without log-drain/invoice corroboration).

For every finding below HIGH, set `upgrade_input` to the SPECIFIC missing input
that would upgrade it (Requirement 4.5) — never a generic "more data would help."
Pull the exact input name from the fragment's own `computed_from_inputs`
contribution (each fragment already recorded which inputs a finding depends on;
the assembler cross-references `assessment-state.json.inputs_received` to
determine which of those are still missing, and that gap IS the `upgrade_input`).

---

## Step 2: Write `discovery.json`

Merge `adapter-build`/`manifest-fallback`, `source-configs`, `vercel-api`, and
(if triggered) `header-probe` contributions:

```json
{
  "phase": "discover",
  "timestamp": "<ISO 8601>",
  "signal_source_used": "adapter_api" | "manifest_fallback",
  "route_disposition": [...],
  "next_config": {...},
  "middleware_analysis": {...},
  "vercel_json_config": {...},
  "streaming_routes_with_empty_body_risk": [...],
  "deployments": [...],
  "env_var_names": [...],
  "domains": [...],
  "crons": [...],
  "storage_integrations": [...],
  "peripherals": [...],
  "api_routes": [...],
  "backend_service_detected": false,
  "usage_metrics": {...},
  "header_probe_results": [...],
  "probe_limitations": [...]
}
```

Every leaf finding within this object carries its assigned `confidence` and
(when sub-HIGH) `upgrade_input`, per Step 1.

---

## Step 3: Write `coupling-score.json`

```json
{
  "phase": "discover",
  "timestamp": "<ISO 8601>",
  "items": [ /* the 9 items from discover-coupling.md, each with confidence assigned */ ],
  "phased_migration_candidate": { ... } // if flagged
}
```

---

## Step 4: Write `preflight-findings.json`

```json
{
  "phase": "discover",
  "timestamp": "<ISO 8601>",
  "checks": [/* all 10 checks from discover-preflight.md, each with confidence assigned */]
}
```

**Before writing, verify all 10 check IDs are present** (M1, M2, B1, B2, B3, B4,
S1, I1, O1, U1) — cross-reference against `knowledge/preflight-checks.json`'s
own check list to confirm nothing was dropped during assembly. This mirrors
`discover-preflight.md`'s own Step 4 internal check, as defense in depth.

---

## Step 5: Write Back to `assessment-state.json`

Read the current `assessment-state.json` (read-merge-write, never blind
overwrite):

1. For each Tier 2/3 input actually consumed by any fragment this run, set
   `inputs_received.tier2`/`tier3.<input>.received = true` and `received_at` if
   newly received.
2. For EVERY finding produced this run (across all three artifacts), write or
   update its entry in `findings`, keyed by a stable `finding_id`:
   - `discovery.*` findings: e.g. `"discovery.route_disposition"`,
     `"discovery.backend_service_detected"`.
   - `coupling.*` findings: e.g. `"coupling.isr"`, `"coupling.edge_middleware"`
     (one entry per Coupling Score item id).
   - `preflight.*` findings: e.g. `"preflight.M1"`, `"preflight.U1"` (one entry
     per check id).
   - Each entry: `{ value, confidence, upgrade_input, computed_at,
     computed_from_inputs }` per the schema in
     `references/state/assessment-state.schema.json`.
3. For any finding that was SHORT-CIRCUITED this run (per
   `discover-coupling.md`/`discover-preflight.md`'s recompute preambles), leave
   its `computed_at` and `value`/`confidence` UNCHANGED — do not touch its entry
   at all if it was skipped.
4. Update `last_updated` to the current timestamp. Write the full file back.

---

## Completion Gate

Re-read all three artifacts AND `assessment-state.json` from disk, then run the
checks declared in `discover.md`'s `_postconditions`:

1. `discovery.json`, `coupling-score.json`, `preflight-findings.json` all exist
   and parse as valid JSON.
2. Every finding in `discovery.json` and `preflight-findings.json` carries a
   `confidence` field in `{LOW, MEDIUM, HIGH}` and, when not `HIGH`, an
   `upgrade_input` field naming the specific missing input.
3. `preflight-findings.json` contains an entry for all 10 named checks
   regardless of which outcome will eventually be recommended.
4. `assessment-state.json`'s `findings` map was updated with this phase's
   outputs and `computed_from_inputs` recorded per finding.

**On any failure:** emit exactly:

```
GATE_FAIL | phase=discover | field=<failing file/field> | reason=<missing|invalid>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`.

**On all-pass:** emit exactly:

```
HANDOFF_OK | phase=discover | artifacts=discovery.json,coupling-score.json,preflight-findings.json
```

Then update `.phase-status.json`: mark `phases.discover` `"completed"`, set
`current_phase` to `clarify`, update `last_updated` — in the same turn as
`discover.md`'s Step 6 output message.

---

## Scope Boundary

**This assembler covers merging Discover's 7 fragments, Confidence_Tier
assignment, and the completion gate ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-running any fragment's own detection logic
- Filtering or reframing Pre-Flight Check findings by outcome (that is
  `report-render.md`'s job — this assembler writes everything, unconditionally)
- Advancing `.phase-status.json` before `HANDOFF_OK` is emitted

**Your ONLY job: merge, assign confidence, write, gate, hand off.**
