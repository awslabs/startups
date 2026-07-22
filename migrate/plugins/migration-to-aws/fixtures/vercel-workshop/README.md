# Vercel what-if workshop fixtures

Port of the Heroku workshop pattern for `vercel-to-aws`
(`references/phases/workshop/`, `_kind: checkpoint`). Discovery / coupling /
preflight stay frozen; Recommend (or outcome override) + Estimate refresh under
`scenarios/`.

| Path                         | Role                                                                        |
| ---------------------------- | --------------------------------------------------------------------------- |
| `seed/`                      | Post-Estimate baseline (outcome A, arm64-default skill path)                |
| `after-outcome-b-x86/`       | After Apply: `outcome_override=B`, `cpu_architecture=x86_64`, spiky traffic |
| `expected-workshop.json`     | Asserter expectations                                                       |
| `check_expected_workshop.py` | Stdlib checker                                                              |

## Assert

```bash
python3 check_expected_workshop.py after-outcome-b-x86
```

## Fresh-agent replay bar

Before a workshop PR: fresh agent from `seed/` → enter workshop → set traffic
spiky + outcome B + x86 → Apply & reprice → Compare → Exit → asserter PASS.
Prefer continuing to Report once so decision-traceability reads
`fired_rule: "workshop_override"` (catches invented-field regressions). Record
the replay in the PR.

## SA demo script

1. Copy `seed/*` into `.migration/0719-vw-demo/` (`workshop: pending` in
   `.phase-status.json`).
2. Enter what-if workshop from Estimate offer (or say **workshop mode**).
3. Confirm `scenarios/scenario-001*` baseline capture.
4. Sheet: set traffic to spiky, **Outcome override → B**, **CPU → x86_64**; Apply & reprice.
5. Confirm `recommendation.outcome=B`, `fired_rule=workshop_override` (no
   `rule_id`), `separable` omitted, Q1 has `workshop_note` with original
   sustained, balanced $/mo changes, discovery bytes unchanged;
   `current_phase` stays `estimate`.
6. Compare scenarios → Exit to Generate via `workshop-assemble` (`current_phase:
   generate`).

Partner one-liner: _After Estimate, reprice OpenNext vs Fargate vs hybrid,
region, Multi-AZ, and arch — up to 5 scenarios, no re-discovery. (Region dollar
deltas need awspricing MCP.)_
