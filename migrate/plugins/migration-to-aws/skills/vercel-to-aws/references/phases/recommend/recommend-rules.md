---
_fragment: apply-rules
_of_phase: recommend
_contributes:
  - recommendation.json (outcome, fired_rule, tiebreak, separable, backend_shape, confidence, reasons, resolving_input)
---

# Recommend Phase: Apply Rules

> Thin dispatcher. This fragment does NOT contain the decision table itself —
> that lives entirely in `references/shared/vercel-recommendation-engine.md`
> (loaded by `recommend.md`'s `_knowledge`). This fragment's job is to APPLY
> that engine's steps against the real artifacts from this run, in the fixed
> order the engine defines, and produce the contribution below.

**Execute ALL steps in order. Do not skip or deviate. Do not duplicate the
engine's decision table here — load and follow it.**

---

## Step 1: Gather Signals

Read, from disk:

- `clarify-answers.json` — `Q1_traffic_shape`, `Q2_migration_trigger`,
  `Q3_devops_bandwidth`, `Q4_preview_dependence`, and `Q5_nextjs_upgrade` (if
  present).
- `discovery.json` — `peripherals[]`, `api_routes[]`, `backend_service_detected`,
  route analysis for websockets/long-running-job signals, `usage_metrics`.
- `coupling-score.json` — `items[]`, specifically `isr`, `edge_middleware`,
  `edge_runtime_routes`.
- `preflight-findings.json` — not directly consulted by the engine's decision
  steps (Pre-Flight Checks feed the REPORT's filtering, not the Recommendation
  Engine's outcome selection), but available if the engine's fallback behavior
  needs to note anything about check severity in its `reasons`.

Map these onto the engine's "Signal Sources" table (§ of
`vercel-recommendation-engine.md`) exactly as documented there — do not invent
alternate key paths.

---

## Step 2: Apply the Engine's Decision Steps, in Order

Follow `vercel-recommendation-engine.md` § "Decision Steps (evaluated
top-to-bottom, first match wins)" EXACTLY:

1. Evaluate Step 1 (preview dependence + separability). If it fires, apply the
   Step-1 Recursion sub-section to determine `backend_shape` by re-evaluating
   Steps 2-4 (yes, including Step 4 — the backend's own traffic shape can be
   ambiguous independently of the outer decision) against ONLY the
   backend-relevant signal subset — do not skip this recursion, and do not let
   it touch the OUTER `outcome` (stays `"C"`), `fired_rule` (stays `1`), or
   `tiebreak` (stays `false`). If the recursion itself reaches Step 4, record
   `backend_tiebreak: true` and `backend_resolving_input` instead — see the
   engine's Step-1 Recursion field-shape rule and Step 4's backend-recursion
   note for the exact distinction between the outer and backend-scoped
   tiebreak fields.
2. If Step 1 did not fire, evaluate Step 2 (Lambda-hostile workload).
3. If Step 2 did not fire, evaluate Step 3 (traffic shape + coupling) —
   including its row-order rule (spiky/coupling/small-team row evaluated
   before sustained/debuggability row) and its Residual sub-section for a
   clear traffic-shape signal whose secondary conditions don't cleanly
   complete either row.
4. If Step 3 did not fire (its Residual also did not apply — i.e. traffic-shape
   confidence itself is LOW), evaluate Step 4 (tiebreak).

STOP at the first step that fires. Never continue evaluating subsequent steps
once one has fired (except the Step-1-triggered recursion into Steps 2-4, which
is a distinct, explicitly-scoped exception documented in the engine itself).

---

## Step 3: Apply Fallback Behavior for Any Missing Signal

If any signal Step 2 needs is missing/unreadable, apply
`vercel-recommendation-engine.md` § "Fallback Behavior (Never Block on Missing
Signals)" exactly — never fail this fragment due to a missing signal, never
guess beyond what the fallback table specifies.

---

## Step 4: Assign Confidence and Compose `reasons`

Per the engine's § "Confidence Levels": assign `high`/`medium`/`low` based on
how unambiguous the firing rule's signal was. Compose `reasons` citing the
ACTUAL signal values observed this run (the founder's actual Q4 answer content,
the actual peripheral list, the actual coupling items) — never a generic
placeholder string.

---

## Step 5: Confirm EKS/Amplify Never Appear

Before contributing output, confirm `outcome` and `backend_shape` are drawn
strictly from `{"A", "B", "C", "stay"}` / `{"A-shaped", "B-shaped", null}` (or
their 2-element tiebreak array forms) — per the engine's explicit prohibition.
If anything in Step 1-4's evaluation seemed to point toward EKS or Amplify (e.g.
the founder mentioned running Kubernetes elsewhere in Q3), that observation
belongs in `reasons` as CONTEXT, never as the `outcome` value itself.

---

## Step 6: Output Contribution for Parent Orchestrator

```json
{
  "outcome": "A" | "B" | "C" | "stay" | ["A", "B"],
  "fired_rule": 1 | 2 | 3 | 4,
  "tiebreak": false,
  "separable": true,
  "backend_shape": "A-shaped" | "B-shaped" | ["A-shaped", "B-shaped"] | null,
  "backend_tiebreak": false,
  "backend_resolving_input": null,
  "confidence": "high" | "medium" | "low",
  "reasons": ["<cite actual signal values>"],
  "resolving_input": null
}
```

`backend_tiebreak`/`backend_resolving_input` are populated ONLY when
`outcome == "C"` and the Step-1 recursion's own Step 4 fired (see the engine's
Step 4 backend-recursion note) — omit or leave `false`/`null` otherwise. These
fields are DISTINCT from `tiebreak`/`resolving_input`, which describe the
OUTER decision only.

This is the phase's ONLY fragment — the assembler
(`recommend-assemble.md`) writes this contribution directly to
`recommendation.json` with minimal additional processing (adding the
synthetic `assessment-state.json` finding entry).

---

## Error Handling

| Error Category                                                                                                      | Behavior                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Two rules appear to fire simultaneously on the same signal set                                                      | This should not happen given the engine's strict `if/else fall-through` structure — if it does, apply the EARLIER rule (lower step number) and note the ambiguity in `reasons`             |
| A signal value is present but doesn't map cleanly onto the engine's expected categories (e.g. an unusual Q4 answer) | Use judgment to classify per the engine's intent, and note the interpretation explicitly in `reasons` so the report's decision traceability can show the founder how their answer was read |

---

## Scope Boundary

**This fragment covers applying the recommendation engine's rules ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Duplicating or rewriting the engine's decision table (load and follow
  `vercel-recommendation-engine.md`; do not inline it)
- Report rendering or outcome-based filtering (that is Report phase's job)
- Recommending EKS or Amplify as `outcome`/`backend_shape` values

**Your ONLY job: apply the engine's steps in order and produce the
recommendation contribution. Nothing else.**
