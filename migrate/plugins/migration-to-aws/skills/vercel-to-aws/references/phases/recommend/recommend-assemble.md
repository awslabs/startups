---
_assemble: recommend-assemble
_of_phase: recommend
_reads:
  - apply-rules (outcome, fired_rule, tiebreak, separable, backend_shape, confidence, reasons, resolving_input)
_produces:
  - recommendation.json
---

# Recommend Phase: Assembler

> Writes `recommend-rules.md`'s contribution to `recommendation.json`, adds a
> synthetic finding entry to `assessment-state.json.findings` (so the report's
> decision-traceability appendix has one place to read `fired_rule` from), and
> runs the completion gate. This is the SINGLE creator of `recommendation.json`.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Write `recommendation.json`

Write `recommend-rules.md`'s contribution directly, adding phase metadata:

```json
{
  "phase": "recommend",
  "timestamp": "<ISO 8601>",
  "outcome": "A" | "B" | "C" | "stay" | ["A", "B"],
  "fired_rule": 1 | 2 | 3 | 4,
  "tiebreak": false,
  "separable": true,
  "backend_shape": "A-shaped" | "B-shaped" | ["A-shaped", "B-shaped"] | null,
  "backend_tiebreak": false,
  "backend_resolving_input": null,
  "confidence": "high" | "medium" | "low",
  "reasons": [...],
  "resolving_input": null
}
```

---

## Step 2: Add the Synthetic Finding to `assessment-state.json`

Read the current `assessment-state.json` (read-merge-write). Add or update a
`findings.recommend.fired_rule` entry:

```json
{
  "value": {
    "fired_rule": 1,
    "outcome": "C",
    "backend_shape": "B-shaped"
  },
  "confidence": "HIGH",
  "upgrade_input": null,
  "computed_at": "<ISO 8601>",
  "computed_from_inputs": ["clarify_q4_preview_dependence", "discovery.peripherals"]
}
```

**Case conversion required:** `recommendation.json`'s own `confidence` field
uses the Recommendation Engine's lowercase vocabulary (`"high"` / `"medium"` /
`"low"`, per `vercel-recommendation-engine.md` § "Confidence Levels" — this
lowercase form is correct and unchanged in `recommendation.json` itself).
`assessment-state.schema.json`'s `findingRecord.confidence`, however, is a
DIFFERENT, uppercase enum (`{"LOW", "MEDIUM", "HIGH"}`, shared across every
other finding in this skill's ledger). When copying `recommendation.json`'s
`confidence` value into this synthetic finding, uppercase it
(`high`→`"HIGH"`, `medium`→`"MEDIUM"`, `low`→`"LOW"`) — do NOT copy the
lowercase string verbatim, or the write will fail
`assessment-state.schema.json` validation.

This gives the report's decision traceability appendix (Requirement 10.1-10.3) a
single, stable place to read "which rule fired and why" from, independent of
re-parsing `recommendation.json` each time. Update `last_updated`, write the
file back.

---

## Completion Gate

Re-read `recommendation.json` from disk, then run the checks declared in
`recommend.md`'s `_postconditions`:

1. The file exists and parses as valid JSON.
2. `outcome` is one of `{A, B, C, stay}` or the array `[A, B]`; `fired_rule`
   names exactly one of the 4 rules AND reflects only the OUTER decision;
   `tiebreak` is `true` only when rule 4 fired AT THE OUTER LEVEL (never `true`
   when `outcome == "C"`, since only Rule 1 produces `"C"`).
3. If `outcome == "C"`, `separable == true`; if `separable == false`, `outcome`
   MUST be `"stay"`.
4. If `outcome == "C"`, `backend_shape` is one of `{A-shaped, B-shaped,
   [A-shaped, B-shaped], null}` and this document's own review confirms it is
   never used anywhere to imply a partial OpenNext/SST scaffold (a documentation
   check, not a runtime one — this constraint is enforced structurally by
   `scaffold-opennext.md`/`scaffold-fargate.md` never being triggered together).
   If `backend_shape` is the 2-element array, `backend_tiebreak == true` and
   `backend_resolving_input` is non-null; `backend_tiebreak` and the outer
   `tiebreak` are never both `true` in the same recommendation.
5. `outcome` and `backend_shape` are never `"EKS"` or `"Amplify"`.

**On any failure:** emit exactly:

```
GATE_FAIL | phase=recommend | field=<failing field> | reason=<missing|invalid>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`.

**On all-pass:** emit exactly:

```
HANDOFF_OK | phase=recommend | artifacts=recommendation.json
```

Then update `.phase-status.json`: mark `phases.recommend` `"completed"`, set
`current_phase` to `report`, update `last_updated` — in the same turn as
`recommend.md`'s Step 4 output message.

---

## Scope Boundary

**This assembler covers writing `recommendation.json`, the synthetic finding,
and the completion gate ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-running `recommend-rules.md`'s own decision logic
- Report rendering
- Advancing `.phase-status.json` before `HANDOFF_OK` is emitted

**Your ONLY job: write, record the synthetic finding, gate, hand off.**
