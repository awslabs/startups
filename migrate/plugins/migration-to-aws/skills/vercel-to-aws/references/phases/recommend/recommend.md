---
_phase: recommend
_title: "Apply Precedence Rules -> Outcome"
_requires_phase: clarify
_input:
  - discovery.json
  - coupling-score.json
  - preflight-findings.json
  - clarify-answers.json
_knowledge:
  - { file: references/shared/vercel-recommendation-engine.md, _when: "always" }
_fragments:
  - _id: apply-rules
    _trigger: { _always: true }
    _file: phases/recommend/recommend-rules.md
_assemble:
  _file: phases/recommend/recommend-assemble.md
_produces:
  - recommendation.json
_advances_to: report
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_file_exists: [discovery.json, coupling-score.json, preflight-findings.json, clarify-answers.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: recommendation.json
    _on_failure: _halt_and_inform
  - _validate_json: recommendation.json
    _on_failure: _halt_and_inform
  - _assert: "recommendation.outcome is one of {A, B, C, stay} or the array [A, B]; recommendation.fired_rule names exactly one of the 4 precedence rules and reflects ONLY the outer (top-level) decision - it is never changed by a backend-level tiebreak inside the Step-1 recursion; recommendation.tiebreak is true only when rule 4 fired AT THE OUTER LEVEL (never true when outcome is 'C', since only Rule 1 produces 'C')"
    _on_failure: _halt_and_inform
  - _assert: "if outcome is C, recommendation.separable is true; if separable is false, outcome MUST be 'stay'"
    _on_failure: _halt_and_inform
  - _assert: "if outcome is C, recommendation.backend_shape is one of {A-shaped, B-shaped, [A-shaped, B-shaped], null} and is never used to imply a partial OpenNext/SST scaffold; if backend_shape is the 2-element array, recommendation.backend_tiebreak is true and recommendation.backend_resolving_input is non-null (mirroring tiebreak/resolving_input one level down, per vercel-recommendation-engine.md's Step-1 Recursion field-shape rule); backend_tiebreak and the outer tiebreak are never both true"
    _on_failure: _halt_and_inform
  - _assert: "recommendation.outcome and recommendation.backend_shape are never 'EKS' or 'Amplify' - those are report-prose callouts, never engine outputs"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - assessment-report.html
---

# Phase 4: Apply Precedence Rules -> Outcome

Loads `references/shared/vercel-recommendation-engine.md` as knowledge (always,
per `_knowledge`), then runs a single fragment that applies the engine's 4-step
precedence cascade against every upstream artifact.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Load the Recommendation Engine

Load `references/shared/vercel-recommendation-engine.md` in full. This is the
canonical decision table — do NOT duplicate its content inline anywhere in this
skill. Every phase file that needs the engine's logic loads this same file.

---

## Step 2: Run the Rules Fragment

Load `references/phases/recommend/recommend-rules.md` and follow it. It applies
the engine's Steps 1-4 against `discovery.json`, `coupling-score.json`,
`preflight-findings.json`, and `clarify-answers.json`, in that fixed order,
stopping at the first rule that fires.

---

## Step 3: Assemble

Load `references/phases/recommend/recommend-assemble.md` (the phase's assembler)
and follow it to write `recommendation.json`, add the synthetic `fired_rule`
finding to `assessment-state.json.findings` (for the report's decision
traceability appendix), and run the completion gate.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter
and enforced per `INTERPRETER.md` § Gate protocol: re-read `recommendation.json`
from disk, run the mechanical checks and the `_assert` judgment checks (outcome
enum validity, separable/backend_shape conditional presence, tiebreak-iff-rule-4,
EKS/Amplify never appear as outputs), then emit `GATE_FAIL` or
`HANDOFF_OK | phase=recommend | artifacts=recommendation.json` and advance.

---

## Step 4: Update Phase Status and Hand Off

Only after `HANDOFF_OK`, apply the phase-status update protocol
(`INTERPRETER.md` § The interpreter loop) — mark `phases.recommend` completed
and advance per `_advances_to` — in the same turn as the output message.

Output to the founder — build the message from `recommendation.json`'s
contents, in plain language (never cite `fired_rule` numbers or internal jargon
here — that belongs only in the report's decision-traceability appendix per
Requirement 9.7):

- If `outcome` is a single value: "Recommendation: {outcome-in-plain-language}.
  Confidence: {confidence}."
- If `outcome` is `["A","B"]` (tiebreak): "Your traffic shape is unclear enough
  that I'm not going to force a pick between two solid options — the full
  report lays out both."

Format: "Recommend phase complete. [summary] Next required step: Phase 5 —
Report. Load `references/phases/report/report.md` now."

---

## Error Handling

| Error Category                                                                  | Behavior                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| An upstream artifact is missing (should not happen given `_preconditions`)      | `_preconditions` `_assert` fails `_unrecoverable` — this is caught before Step 1 runs                                                                                                                                    |
| The engine's decision cascade produces an outcome outside the closed vocabulary | This is a bug in `recommend-rules.md`'s application of the engine, not a valid state — the `_postconditions` `_assert` catches it and fails the gate; fix the rules application, do not patch the output to force a pass |

---

## Scope Boundary

**This phase covers applying the precedence cascade to produce `recommendation.json`
ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Report rendering or outcome-based filtering of Pre-Flight Checks (that is
  Phase 5 — Report's job)
- Scaffold/Terraform/SST generation (that is the Scaffold checkpoint's job)
- Recommending EKS or Amplify as an `outcome` value (see the engine's own
  explicit prohibition)

**Your ONLY job: apply the precedence cascade and produce `recommendation.json`.
Nothing else.**
