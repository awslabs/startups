---
_fragment: refresh
_of_phase: workshop
---

# Workshop — Refresh (patch → Recommend? → Estimate → snapshot)

## Inner runs (artifact-only) — mandatory

Follow `references/vendored/workshop/workshop-invariants.md` § 3 (canonical
allowed/forbidden contract) for every inner Recommend/Estimate run. Vercel
specifics: leave `phases.recommend` and `phases.estimate` as `"completed"`;
inner Recommend = fragments + the write portion of `recommend-assemble.md`
only; inner Estimate = `estimate-cost-engine.md` + write + Present Summary,
skipping `HANDOFF_OK`, phase-status, deferred-advance, and the workshop
offer; `current_phase` stays `"estimate"` until `workshop-assemble.md`.

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

Follow `references/vendored/workshop/workshop-invariants.md` § 6 with
`{SKILL_LABEL}` = "Vercel" and the PRIMARY outcome's Balanced services
(skip `tiebreak_alternative`) — probe once, prefer `build_estimate`, store
the URL as `estimation_summary.calculator_url`, null + one chat note on
any failure.

### 7. Hand back

Return to `workshop.md` → `workshop-compare.md`.
