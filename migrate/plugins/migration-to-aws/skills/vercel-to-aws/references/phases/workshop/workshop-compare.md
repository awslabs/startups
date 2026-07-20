---
_fragment: workshop-compare
_of_phase: workshop
---

# Workshop — Compare Scenarios (Vercel)

> Read-only table from `scenarios/index.json`.

## Steps

1. Load `scenarios/index.json` (if missing, tell user to Apply once for baseline).
2. For each scenario (baseline first, then by `created_at`), read the manifest +
   clarify/recommendation copies and build columns:
   - Outcome ← `recommendation.outcome` (or estimation_summary.outcome)
   - Region ← `workshop.target_region`
   - Arch ← `workshop.cpu_architecture`
   - Multi-AZ (Balanced) ← `workshop.availability_multi_az_balanced`
   - Traffic ← short form of `Q1_traffic_shape.answer` when present
   - Premium / Balanced / Optimized $/mo ← `estimation_summary` tiers
   - Complexity ← `estimation_summary.complexity_tier`
3. Mark the active row.
4. Present:

| Scenario | Outcome | Region | Arch | Multi-AZ | Traffic | Premium $/mo | Balanced $/mo | Optimized $/mo | Complexity |
| -------- | ------- | ------ | ---- | -------- | ------- | ------------ | ------------- | -------------- | ---------- |

Under the table: active vs baseline `preferences_subset`; any `region_note`
(remind: regional deltas need awspricing MCP); one `{scenario}: {url}` line
per non-null `estimation_summary.calculator_url` (shareable, editable
calculator.aws estimate — AWS computes regional prices server-side there);
reminder that discovery/coupling/preflight are frozen. Keep under 25 lines.
