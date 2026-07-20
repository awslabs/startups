---
_fragment: workshop-refresh
_of_phase: workshop
---

# Workshop — Refresh (patch → Recommend? → Estimate → snapshot)

## Inner runs (artifact-only) — mandatory

When this fragment re-runs Recommend or Estimate, treat them like an `_exec`
worker's WORK slice (`INTERPRETER.md` § `_exec`): **fragments + assembler
artifact write only**. Do **not** advance the backbone mid-workshop.

| Allowed                                                   | Forbidden                                                                                                                        |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Overwrite `recommendation.json` / `estimation-infra.json` | Set recommend/estimate to `in_progress`                                                                                          |
| Soft-validate before snapshot                             | Emit `HANDOFF_OK` from Recommend or Estimate                                                                                     |
| Brief chat note that reprice finished                     | Touch `.phase-status.json` `current_phase` or advance to `generate`                                                              |
| Keep `phases.workshop` as `in_progress`                   | Run Estimate's post-Estimate workshop offer (recursion)                                                                          |
|                                                           | Evaluate Recommend/Estimate `_preconditions` that fail on `_check_single_active_phase` because workshop is already `in_progress` |

Leave `phases.recommend` and `phases.estimate` as `"completed"`. Leave
`current_phase` at `"estimate"` until the user exits via `workshop-assemble.md`.

Concrete file slices:

1. **Recommend** (when not using `outcome_override` patch) — run recommend
   fragments + write portion of `recommend-assemble.md`. Skip `HANDOFF_OK` and
   phase-status advance. Also refresh the synthetic
   `findings.recommend.fired_rule` entry in `assessment-state.json` when that
   file exists.
2. **Estimate** — run `estimate-cost-engine.md` + write + Present Summary in
   `estimate-assemble.md`. Skip `HANDOFF_OK`, phase-status, deferred-advance,
   and the what-if workshop offer.

## Baseline capture (no Recommend/Estimate yet)

When `scenarios/` or `scenarios/index.json` is absent:

1. `discovery_fingerprint` = SHA-256 hex of `discovery.json` bytes.
2. Create `scenarios/`.
3. Copy working-tree artifacts:
   - `scenarios/scenario-001.clarify-answers.json`
   - `scenarios/scenario-001.recommendation.json`
   - `scenarios/scenario-001.estimation-infra.json`
4. Write `scenarios/scenario-001.json` with `source: "baseline"`, `label: "baseline"`,
   fingerprints, `estimation_summary` (include `outcome` from recommendation and
   all three monthly tiers).
5. Write `scenarios/index.json` (`baseline` / `active` = `scenario-001`,
   `max_scenarios: 5`).
6. Ensure `clarify-answers.json.workshop` exists with defaults:

   ```json
   {
     "active": true,
     "target_region": "us-east-1",
     "availability_multi_az_balanced": false,
     "cpu_architecture": "arm64",
     "outcome_override": null,
     "backend_shape_override": null,
     "last_sheet_at": "<now>",
     "active_scenario_id": "scenario-001"
   }
   ```

7. If baseline-only, return to `workshop.md` for the sheet.

## Apply & reprice

### 1. Discovery guard

Recompute discovery fingerprint; if ≠ `index.discovery_fingerprint`, **STOP**:

> Discovery changed since baseline. Re-run Discover before workshop reprice.

### 2. Stale Generate guard

If Generate/Report completed, require re-entry confirm and reset those phases to
`pending` before continuing.

### 3. Patch clarify-answers (transcript-safe)

Apply sheet edits with **provenance**:

- For each Clarify answer path the sheet changes (`Q1_traffic_shape.answer`,
  `Q7_database_size.answer`, `Q6_vercel_spend.answer` when allowed): if the new
  value differs from the current `answer`, set/update on that question object:
  `workshop_note: "edited in what-if workshop <ISO8601>; original: <prior answer>"`
  (use the answer value **before** this patch as `<prior answer>`; if a prior
  `workshop_note` already records an original, keep that original string and
  only refresh the timestamp in the note).
- Do **not** silently overwrite without `workshop_note`.
- Set `workshop.active: true`, `workshop.last_sheet_at` now, and other workshop
  knobs from the sheet (`outcome_override`, `backend_shape_override`, region,
  Multi-AZ, arch).
- Leave non-knob Clarify answers untouched.
- Mirror workshop-relevant answers into `assessment-state.json.clarify_answers`
  when that file exists (same keys, including `workshop_note`).

### 4. Recommend refresh

#### Outcome override patch (when `workshop.outcome_override` is set)

Do **not** run the precedence engine. Patch `recommendation.json` in place using
the **declared** contract fields only (no `rule_id` / `rule_rationale`):

Common fields for every override:

```json
{
  "phase": "recommend",
  "timestamp": "<now>",
  "outcome": "<A|B|C|stay from override>",
  "fired_rule": "workshop_override",
  "tiebreak": false,
  "resolving_input": null,
  "confidence": "medium",
  "reasons": [
    "workshop assumption: SA forced outcome <X> in what-if workshop"
  ]
}
```

Per-target field surgery (engine Constraints):

| Override   | Required surgery                                                                                                                                                                                                                                                                                                                                                 |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `A` or `B` | **Omit** `separable`, `backend_shape`, `backend_tiebreak`, `backend_resolving_input`. Append a reason naming the target (OpenNext vs Fargate).                                                                                                                                                                                                                   |
| `C`        | Set `separable: true`. Set `backend_shape` from `workshop.backend_shape_override` (`A-shaped` or `B-shaped` only — never the tiebreak array). Set `backend_tiebreak: false`, `backend_resolving_input: null`. If baseline `recommendation.separable === false` or `backend_shape_override` is missing/invalid, **STOP** and re-present the sheet (do not write). |
| `stay`     | Set `separable` to baseline's boolean if present, else `false`. **Omit** all `backend_*` keys.                                                                                                                                                                                                                                                                   |

Also update `assessment-state.json.findings.recommend.fired_rule` (when the
file exists) so the report's decision-traceability appendix sees
`fired_rule: "workshop_override"` with the new `outcome` / `backend_shape`.

#### Engine re-run (when `outcome_override` is `null`)

Execute Recommend per **Inner runs** above against frozen discovery + patched
clarify answers. Overwrite `recommendation.json`. Reasons that cite
`workshop_note`-bearing answers MUST use the `workshop assumption:` prefix
(`recommend-rules.md` Step 4).

### 5. Estimate refresh (inner)

Execute Estimate per **Inner runs** above. Overwrite `estimation-infra.json`.
Skip the post-Estimate workshop **offer** on this inner run (avoid recursion).

Cost-engine MUST honor `workshop.target_region`,
`workshop.availability_multi_az_balanced`, and `workshop.cpu_architecture`
(see `estimate-cost-engine.md` workshop section).

### 6. Snapshot

1. Next id `scenario-00N`.
2. If length would exceed 5, **warn and name** the oldest non-baseline scenario
   (id + label) before deleting its files and dropping it from the index.
3. Copy clarify / recommendation / estimation into `scenarios/{id}.*`.
4. `preferences_subset`: differing workshop knobs + Q1/Q6/Q7 vs baseline.
5. Update `index.json` + `workshop.active_scenario_id`.

### 6b. Shareable calculator link (best-effort, never blocks)

If the `aws-pricing-calculator` MCP server is available (try `get_server_info`
once; do NOT retry on failure):

1. Prefer the one-shot `build_estimate` (create + add + lint + save): name
   `"Vercel migration — {scenario label} ({target_region})"`, services from
   the scenario's Balanced-tier `estimation-infra.json` breakdown (the
   PRIMARY outcome's set; skip `tiebreak_alternative`), each with the
   scenario's `target_region` — the calculator computes REGIONAL prices
   server-side, which the us-east-1 cache cannot. On a structured
   needs-field-discovery response, resolve via `get_service_fields` and retry
   ONCE; else fall back to `create_estimate` → `add_service` →
   `export_estimate`.
2. Store the URL as `estimation_summary.calculator_url` in the manifest.
3. Any failure or unmappable service → `calculator_url: null`, one chat note,
   continue. Workshop numbers stay authoritative; the link is a stakeholder
   artifact.

### 7. Hand back

Return to `workshop.md` → `workshop-compare.md`.
