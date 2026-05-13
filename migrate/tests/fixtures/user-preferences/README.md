# Fixture: user-preferences

Tests that user-provided answers in Clarify override defaults and influence Design output.

## Resources

Same as minimal-cloud-run-sql (Cloud Run + Cloud SQL) but with user-overridden preferences.

## Pre-seeded preferences

| Constraint         | Value        | chosen_by |
| ------------------ | ------------ | --------- |
| `target_region`    | `us-west-2`  | **user**  |
| `availability`     | `single-az`  | **user**  |
| `cutover_strategy` | `blue-green` | **user**  |
| All others         | defaults     | default   |

## Key invariants tested

- `chosen_by: "user"` entries exist in preferences.json
- Design output uses `us-west-2` (not default `us-east-1`)
- Design output reflects single-AZ (no multi-AZ resources)
- At least one preference has `chosen_by: "user"`
