# Workshop Scenarios — Artifact Contract (Vercel)

> Port of the Heroku what-if workshop contract for `vercel-to-aws`. Discovery is
> **frozen**; workshop mutates Clarify answers + workshop knobs (with transcript
> provenance), refreshes Recommend (when needed) + Estimate, and snapshots the
> active priced outcome.

## Directory layout

```
$MIGRATION_DIR/
├── discovery.json                 # FROZEN
├── coupling-score.json            # FROZEN
├── preflight-findings.json        # FROZEN
├── capture/                       # FROZEN (if present)
├── clarify-answers.json           # active scenario answers + workshop object
├── recommendation.json            # active scenario recommendation
├── estimation-infra.json          # active scenario estimate
└── scenarios/
    ├── index.json
    ├── scenario-001.json
    ├── scenario-001.clarify-answers.json
    ├── scenario-001.recommendation.json
    ├── scenario-001.estimation-infra.json
    └── …
```

Max **5** scenarios. Warn + name the oldest non-baseline before eviction. Never
delete `baseline_scenario_id` unless the user resets the workshop.

## `clarify-answers.json` → `workshop` object

Clarify interview does **not** write this. Workshop creates/patches it:

```json
"workshop": {
  "active": true,
  "target_region": "us-east-1",
  "availability_multi_az_balanced": false,
  "cpu_architecture": "arm64",
  "outcome_override": null,
  "backend_shape_override": null,
  "last_sheet_at": "2026-07-19T20:00:00Z",
  "active_scenario_id": "scenario-002"
}
```

| Field                            | Type         | Rules                                                                                                                                                                    |
| -------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `active`                         | boolean      | `true` while in workshop mode                                                                                                                                            |
| `target_region`                  | string       | AWS region code; default `us-east-1`                                                                                                                                     |
| `availability_multi_az_balanced` | boolean      | When `true`, Balanced tier prices Multi-AZ data services (Premium already does)                                                                                          |
| `cpu_architecture`               | string       | `"arm64"` (skill default per `graviton.md`) or `"x86_64"`. Cross-skill: heroku-to-aws defaults workshop arch to `x86_64`.                                                |
| `outcome_override`               | string\|null | `null` = re-run precedence engine; `"A"`\|`"B"`\|`"C"`\|`"stay"` forces that outcome with `fired_rule: "workshop_override"` (declared contract — never invent `rule_id`) |
| `backend_shape_override`         | string\|null | Required `"A-shaped"` or `"B-shaped"` when `outcome_override` is `"C"`; otherwise `null`. Offer C only when baseline `recommendation.separable === true`.                |
| `last_sheet_at`                  | string       | ISO 8601 UTC                                                                                                                                                             |
| `active_scenario_id`             | string       | matches `scenarios/index.json`                                                                                                                                           |

Sheet also edits existing Clarify answers when present:

| Knob                                                             | Path                      |
| ---------------------------------------------------------------- | ------------------------- |
| Traffic shape                                                    | `Q1_traffic_shape.answer` |
| DB size (if Postgres)                                            | `Q7_database_size.answer` |
| Vercel spend (only if no `discovery.usage_metrics.billing_data`) | `Q6_vercel_spend.answer`  |

**Transcript provenance:** when any of those answers change, set
`workshop_note` on that question object:
`"edited in what-if workshop <ISO8601>; original: <prior answer>"`.
Recommend `reasons[]` that cite such knobs MUST start with
`workshop assumption:`.

## `recommendation.json` under override

See `workshop-refresh.md` § Outcome override patch. Summary:

- `fired_rule: "workshop_override"` (legal fifth value alongside `1|2|3|4`)
- `tiebreak: false`, `resolving_input: null`
- A/B: omit `separable` and all `backend_*`
- C: `separable: true` + `backend_shape` from `backend_shape_override`
- stay: boolean `separable`; omit `backend_*`

## `scenarios/index.json`

```json
{
  "baseline_scenario_id": "scenario-001",
  "active_scenario_id": "scenario-002",
  "max_scenarios": 5,
  "discovery_fingerprint": "<sha256 hex of discovery.json>",
  "scenarios": [
    {
      "scenario_id": "scenario-001",
      "label": "baseline",
      "created_at": "2026-07-19T19:00:00Z",
      "source": "baseline",
      "manifest": "scenarios/scenario-001.json"
    }
  ]
}
```

Every refresh MUST recompute the fingerprint of `discovery.json` and abort if it
differs (re-Discover required).

## `scenarios/scenario-NNN.json` (manifest)

```json
{
  "scenario_id": "scenario-003",
  "label": "outcome B + x86",
  "created_at": "2026-07-19T20:15:00Z",
  "source": "workshop",
  "preferences_subset": {
    "workshop.cpu_architecture": "x86_64",
    "workshop.outcome_override": "B"
  },
  "clarify_fingerprint": "<sha256>",
  "recommendation_fingerprint": "<sha256>",
  "estimation_summary": {
    "outcome": "B",
    "aws_monthly_premium": 0,
    "aws_monthly_balanced": 0,
    "aws_monthly_optimized": 0,
    "complexity_tier": "small",
    "pricing_source": "cached",
    "region_note": null
  },
  "paths": {
    "clarify_answers": "scenarios/scenario-003.clarify-answers.json",
    "recommendation": "scenarios/scenario-003.recommendation.json",
    "estimation_infra": "scenarios/scenario-003.estimation-infra.json"
  }
}
```

Working tree (`clarify-answers.json`, `recommendation.json`, `estimation-infra.json`)
always reflects the **active** scenario.

## Fingerprints

SHA-256 hex of raw file bytes. Discovery fingerprint guards freeze; clarify +
recommendation fingerprints are recorded for audit only.
