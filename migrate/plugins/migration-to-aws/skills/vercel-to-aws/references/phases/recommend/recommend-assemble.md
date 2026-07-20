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
  "fired_rule": 1 | 2 | 3 | 4 | "workshop_override",
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

`fired_rule: "workshop_override"` is legal **only** when produced by
`workshop-refresh.md`'s outcome-override path (not by the precedence engine).
Field surgery for that path is owned by `workshop-refresh.md` § Outcome override
patch — do not invent parallel fields such as `rule_id` / `rule_rationale`.

When `fired_rule` is `"workshop_override"`: `tiebreak` is always `false`,
`resolving_input` is always `null`. For outcomes `A`/`B`, omit `separable` and
all `backend_*` keys. For `C`, require `separable: true` and
`backend_shape` of `"A-shaped"` or `"B-shaped"`. For `stay`, require a boolean
`separable` and omit `backend_*`.

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
   is exactly one of `{1, 2, 3, 4, "workshop_override"}` AND reflects only the
   OUTER decision. When `fired_rule` is numeric: `tiebreak` is `true` only when
   rule 4 fired AT THE OUTER LEVEL (never `true` when `outcome == "C"`). When
   `fired_rule == "workshop_override"`: `tiebreak` MUST be `false` and
   `resolving_input` MUST be `null`.
3. If `outcome == "C"`, `separable == true`; if `separable == false`, `outcome`
   MUST be `"stay"`. If `outcome` is `A` or `B`, `separable` and `backend_*`
   keys MUST be absent.
4. If `outcome == "C"`, `backend_shape` is one of `{A-shaped, B-shaped,
   [A-shaped, B-shaped]}` (non-null) and this document's own review confirms it is
   never used anywhere to imply a partial OpenNext/SST scaffold (a documentation
   check, not a runtime one — this constraint is enforced structurally by
   `scaffold-opennext.md`/`scaffold-fargate.md` never being triggered together).
   If `backend_shape` is the 2-element array, `backend_tiebreak == true` and
   `backend_resolving_input` is non-null; `backend_tiebreak` and the outer
   `tiebreak` are never both `true` in the same recommendation. For
   `workshop_override` + `C`, `backend_shape` MUST be exactly `A-shaped` or
   `B-shaped`.
5. `outcome` and `backend_shape` are never `"EKS"` or `"Amplify"`.

**On any failure:** emit exactly:

```
GATE_FAIL | phase=recommend | field=<failing field> | reason=<missing|invalid>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`.

**On all-pass (outer Recommend only):** emit exactly:

```
HANDOFF_OK | phase=recommend | artifacts=recommendation.json
```

Then update `.phase-status.json`: mark `phases.recommend` `"completed"`, set
`current_phase` to `estimate`, update `last_updated` — in the same turn as
`recommend.md`'s Step 4 output message.

> **Inner workshop reprice:** When Recommend is invoked from
> `workshop-refresh.md`, stop after writing `recommendation.json` (and soft
> validation). Do **not** emit `HANDOFF_OK` or update `.phase-status.json` —
> see `workshop-refresh.md` § Inner runs.

---

## Scope Boundary

**This assembler covers writing `recommendation.json`, the synthetic finding,
and the completion gate ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-running `recommend-rules.md`'s own decision logic
- Report rendering
- Advancing `.phase-status.json` before `HANDOFF_OK` is emitted

**Your ONLY job: write, record the synthetic finding, gate, hand off.**
