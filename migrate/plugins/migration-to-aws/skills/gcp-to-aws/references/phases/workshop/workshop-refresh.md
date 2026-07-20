# Workshop — Refresh (patch → Design → Estimate → snapshot)

## Inner runs (artifact-only) — mandatory

When re-running Design or Estimate from this file: **rewrite artifacts only**.
Do **not** advance the backbone mid-workshop.

| Allowed | Forbidden |
| ------- | --------- |
| Overwrite `aws-design.json` / `estimation-infra.json` | Set design/estimate to `in_progress` |
| Soft-validate estimate invariants before snapshot | Emit `HANDOFF_OK` from Design or Estimate |
| Brief chat note that reprice finished | Touch `current_phase` or advance to `generate` |
| Keep `phases.workshop` as `in_progress` | Run Estimate's post-Estimate workshop offer (recursion) |

Leave `phases.design` and `phases.estimate` as `"completed"`. Leave
`current_phase` at `"estimate"` until `workshop-assemble.md`.

Concrete slices:

1. **Design** — run `design.md` / `design-infra.md` enough to rewrite
   `aws-design.json` (and siblings if the run uses them). Skip handoff and
   phase-status updates.
2. **Estimate** — run `estimate.md` / `estimate-infra.md` enough to rewrite
   `estimation-infra.json`. Skip `HANDOFF_OK`, phase-status, and the workshop offer.

## Baseline capture

When `scenarios/` or `scenarios/index.json` is absent:

1. `inventory_fingerprint` = SHA-256 hex of `gcp-resource-inventory.json` bytes.
2. Create `scenarios/`.
3. Copy working-tree artifacts:
   - `scenarios/scenario-001.preferences.json`
   - `scenarios/scenario-001.aws-design.json`
   - `scenarios/scenario-001.estimation-infra.json`
4. Write `scenarios/scenario-001.json` (`source: "baseline"`, summary from
   estimation-infra including three monthly tiers).
5. Write `scenarios/index.json` (`baseline` / `active` = `scenario-001`,
   `max_scenarios: 5`).
6. Ensure `preferences.workshop` exists:
   `{ "active": true, "last_sheet_at": "<now>", "active_scenario_id": "scenario-001" }`
7. If baseline-only, return to `workshop.md` for the sheet.

## Apply & reprice

### 1. Inventory guard

If fingerprint ≠ `index.inventory_fingerprint`, **STOP**:

> Inventory changed since baseline. Re-run Discover before workshop reprice.

### 2. Stale Generate guard

If generate completed, require re-entry confirm and reset generate to `pending`.

### 3. Patch preferences

Apply sheet edits. Set `workshop.active: true`, `workshop.last_sheet_at` now.
Leave non-knob fields (including AI/agentic constraints) untouched.

### 4–5. Inner Design then Estimate

Per **Inner runs**. Chat note after Estimate:
"Workshop reprice Estimate complete; returning to workshop loop."

### 6. Snapshot

1. Next id `scenario-00N`.
2. If length would exceed 5, **warn and name** oldest non-baseline before delete.
3. Copy prefs / design / estimation into `scenarios/{id}.*`.
4. `preferences_subset`: differing knob paths vs baseline.
5. Update index + `workshop.active_scenario_id`.

### 7. Hand back

Return to `workshop.md` → `workshop-compare.md`.
