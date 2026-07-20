# Workshop — Refresh (patch → Design → Estimate → snapshot)

## Inner runs (artifact-only) — mandatory

When re-running Design or Estimate from this file: **rewrite artifacts only**.
Do **not** advance the backbone mid-workshop.

| Allowed                                               | Forbidden                                               |
| ----------------------------------------------------- | ------------------------------------------------------- |
| Overwrite `aws-design.json` / `estimation-infra.json` | Set design/estimate to `in_progress`                    |
| Soft-validate estimate invariants before snapshot     | Emit `HANDOFF_OK` from Design or Estimate               |
| Brief chat note that reprice finished                 | Touch `current_phase` or advance to `generate`          |
| Keep `phases.workshop` as `in_progress`               | Run Estimate's post-Estimate workshop offer (recursion) |

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

**Graviton caveat carry-forward:** If the sheet showed a Graviton risk-signal
caveat (any `graviton_profile` entry with `tier` in
`{incompatible, conditional, unknown}`) and the SA set
`cpu_architecture` to `graviton` or `mixed`, set
`preferences.workshop.graviton_note` to a short string naming the counts, e.g.
`"1 incompatible, 0 conditional — graviton applies where tier: ready"`. Clear
`graviton_note` when arch is `x86` or when no risk-signal tiers exist.

### 4–5. Inner Design then Estimate

Per **Inner runs**. Design must follow `design.md` § Inner workshop reprice
(skip handoff / phase-status). Estimate must follow `estimate.md` § Inner
workshop reprice. Chat note after Estimate:
"Workshop reprice Estimate complete; returning to workshop loop."

### 6. Snapshot

1. Next id `scenario-00N`.
2. If length would exceed 5, **warn and name** oldest non-baseline before delete.
3. Copy prefs / design / estimation into `scenarios/{id}.*`.
4. `preferences_subset`: differing knob paths vs baseline.
5. Label: summarize the subset; if `workshop.graviton_note` is set, append
   `(caveat: <graviton_note>)` to the scenario `label` and copy the note into
   the manifest as `graviton_note`.
6. Update index + `workshop.active_scenario_id`.

### 6b. Shareable calculator link (best-effort, never blocks)

If the `aws-pricing-calculator` MCP server is available (try `get_server_info`
once; do NOT retry on failure):

1. Prefer the one-shot `build_estimate` (create + add + lint + save): name
   `"GCP migration — {scenario label} ({target_region})"`, services from the
   scenario's Balanced-tier `estimation-infra.json` breakdown, each with the
   scenario's `target_region` — the calculator computes REGIONAL prices
   server-side, which the us-east-1 cache cannot. On a structured
   needs-field-discovery response, resolve via `get_service_fields` and retry
   ONCE; else fall back to `create_estimate` → `add_service` →
   `export_estimate`.
2. Store the URL as `estimation_summary.calculator_url` in the manifest.
3. Any failure or unmappable service → `calculator_url: null`, one chat note,
   continue. Workshop numbers stay authoritative; the link is a stakeholder
   artifact. (This aligns with #49's Estimate-phase calculator integration —
   same server, same degradation rules.)

### 7. Hand back

Return to `workshop.md` → `workshop-compare.md`.
