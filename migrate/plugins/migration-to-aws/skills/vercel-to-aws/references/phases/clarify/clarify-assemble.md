---
_assemble: clarify-assemble
_of_phase: clarify
_reads:
  - ask (all question entries)
_produces:
  - clarify-answers.json
---

# Clarify Phase: Assembler

> Combines `clarify-ask.md`'s question entries into `clarify-answers.json`,
> writes back to `assessment-state.json.clarify_answers`, and runs the
> completion gate. This is the SINGLE creator of `clarify-answers.json`.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Merge Question Entries

Combine every entry `clarify-ask.md` contributed into one object:

```json
{
  "phase": "clarify",
  "timestamp": "<ISO 8601>",
  "Q1_traffic_shape": { "prompt": "...", "answer": "...", "design_consequence": "..." },
  "Q2_migration_trigger": { "prompt": "...", "answer": "...", "design_consequence": "..." },
  "Q3_devops_bandwidth": { "prompt": "...", "answer": "...", "design_consequence": "..." },
  "Q4_preview_dependence": { "prompt": "...", "answer": "...", "design_consequence": "..." },
  "Q5_nextjs_upgrade": { "prompt": "...", "answer": "...", "design_consequence": "..." }
}
```

`Q5_nextjs_upgrade` is present ONLY if it was actually asked (i.e.
`tier1-signals.json.next_version < "16.2.0"`) — per `clarify-ask.md`'s own
output-contribution rule, a skipped question has no entry at all.

---

## Step 2: Handle "Not Yet Determined" Consequences

Some `design_consequence` values legitimately cannot be fully resolved until
`recommend` has run (e.g. Q1's consequence depends on which precedence rule
fires, which depends on Q4's answer too). Where `clarify-ask.md` recorded a
placeholder like "feeds recommend phase rule 3... rule 4 tiebreak fires if
vague," that IS an acceptable, complete `design_consequence` value — it names
which rule(s) the answer feeds, even though the actual outcome is unresolved
until `recommend` runs. Do not treat this as incomplete; the `_assert` in
`clarify.md`'s `_postconditions` explicitly allows "not yet determined - feeds
recommend phase rule N" as a valid value.

---

## Step 3: Write `clarify-answers.json`

Write the merged object to `$MIGRATION_DIR/clarify-answers.json`.

---

## Step 4: Write Back to `assessment-state.json`

Read the current `assessment-state.json` (read-merge-write):

1. For each question entry, write or update `clarify_answers.<question_id>` per
   the schema in `references/state/assessment-state.schema.json`
   (`{prompt, answer, design_consequence, answered_at}`).
2. Update `last_updated` to the current timestamp. Write the full file back.

---

## Completion Gate

Re-read `clarify-answers.json` from disk, then run the checks declared in
`clarify.md`'s `_postconditions`:

1. The file exists and parses as valid JSON.
2. Every answer entry has `prompt`, `answer`, and `design_consequence`
   populated (per Step 2's allowance above).
3. No question was asked whose answer PreScan or Discover already determined —
   spot-check: confirm no entry exists that duplicates a fact already in
   `tier1-signals.json` or `discovery.json` (e.g. no redundant middleware
   question, since `has_middleware` was already known).
4. If `Q5_nextjs_upgrade` is present, confirm it was not treated as a
   precondition anywhere in this phase's own gates, and confirm the phase
   completed regardless of its answer value.

**On any failure:** emit exactly:

```
GATE_FAIL | phase=clarify | field=<failing entry> | reason=<missing|invalid>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`.

**On all-pass:** emit exactly:

```
HANDOFF_OK | phase=clarify | artifacts=clarify-answers.json
```

Then update `.phase-status.json`: mark `phases.clarify` `"completed"`, set
`current_phase` to `recommend`, update `last_updated` — in the same turn as
`clarify.md`'s Step 4 output message.

---

## Scope Boundary

**This assembler covers merging Clarify's question entries and the completion
gate ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Applying the Recommendation Engine's precedence rules (that is
  `recommend-rules.md`'s job)
- Re-asking or re-validating answer CONTENT (that already happened in
  `clarify-ask.md`)
- Advancing `.phase-status.json` before `HANDOFF_OK` is emitted

**Your ONLY job: merge, write, gate, hand off.**
