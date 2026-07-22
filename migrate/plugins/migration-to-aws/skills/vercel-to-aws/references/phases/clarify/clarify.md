---
_phase: clarify
_title: "Clarify - Ask What Discovery Can't Answer"
_requires_phase: discover
_input:
  - discovery.json
  - tier1-signals.json
_interactive: true
_fragments:
  - _id: ask
    _trigger: { _always: true }
    _file: phases/clarify/clarify-ask.md
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - clarify-answers.json
_advances_to: recommend
_re_entry_guard:
  _stale_if_completed: recommend
  _stale_artifact: recommendation.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: clarify-answers.json
    _on_failure: _halt_and_inform
  - _validate_json: clarify-answers.json
    _on_failure: _halt_and_inform
  - _assert: "every answer entry has prompt, answer, and design_consequence fields populated (design_consequence may state 'not yet determined - feeds recommend phase rule N' when the consequence depends on a rule that hasn't run)"
    _on_failure: _halt_and_inform
  - _assert: "no question was asked COLD whose answer PreScan or Discover already determined (e.g. no middleware question when tier1-signals.json.has_middleware is false); presenting a discovery-derived value for founder CONFIRMATION (e.g. Q7's size band from storage_integrations sizeBytes) is the sanctioned form, not a violation"
    _on_failure: _halt_and_inform
  - _assert: "the Next.js-upgrade question, if asked, is not gated as a precondition for any other question or for phase completion"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - migration-report.html
---

# Phase 3: Clarify - Ask What Discovery Can't Answer

Interactive phase. Cannot carry `_exec` (the grammar's own rule — a dispatched
worker cannot converse; see `INTERPRETER.md` § `_exec`, "Non-interactive
affirmation"). Runs inline in the main window, always.

**Execute ALL steps in order. Do not skip or deviate.**

**Clarify is mandatory (skill policy — see `SKILL.md` Execution section).** Do
not skip this phase or jump straight to Recommend even if the founder asks —
there is no exception for "quick" or "obvious" assessments. A
`clarify-answers.json` that was not produced by an actual Clarify run does not
count. If asked to skip, refuse briefly and run Clarify. This phase's question
set is deliberately short precisely BECAUSE PreScan and Discover already
answered what they could — running it is cheap, not a formality.

---

## Step 1: Load Prior Signals

Read `tier1-signals.json` and `discovery.json` before asking anything — these
determine which questions in the fixed set are actually askable (Requirement
2.3).

---

## Step 2: Run the Question Fragment

Load `references/phases/clarify/clarify-ask.md` and follow it. It presents a
brief Discovery Summary before asking anything (grounding the founder in what
PreScan/Discover already found), implements the fixed question set
(Requirement 3.1), applies the PreScan/Discover-aware skip logic, uses
confirm-first phrasing for Q1 when a log drain exists, and frames the
Next.js-upgrade question as a confidence-upgrade offer never a gate
(Requirement 3.3-3.5).

---

## Step 3: Assemble

Load `references/phases/clarify/clarify-assemble.md` (the phase's assembler) and
follow it to write `clarify-answers.json`, update `assessment-state.json.
clarify_answers`, and run the completion gate.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter
and enforced per `INTERPRETER.md` § Gate protocol: re-read `clarify-answers.json`
from disk, run the mechanical checks and the `_assert` judgment checks (every
answer has all three fields, no redundant question was asked, the upgrade
question never gated), then emit `GATE_FAIL` or
`HANDOFF_OK | phase=clarify | artifacts=clarify-answers.json` and advance.

---

## Step 4: Update Phase Status and Hand Off

Only after `HANDOFF_OK`, apply the phase-status update protocol
(`INTERPRETER.md` § The interpreter loop) — mark `phases.clarify` completed and
advance per `_advances_to` — in the same turn as the output message.

Output to the founder: "Clarify complete. [N] questions asked, [M] skipped
because Discover already answered them. Next required step: Phase 4 —
Recommend. Load `references/phases/recommend/recommend.md` now."

---

## Error Handling

| Error Category                        | Behavior                                                                                                                                                                        |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Founder declines to answer a question | Record `answer: "declined"`, apply the fallback per `references/shared/vercel-recommendation-engine.md` § Fallback Behavior — never block phase completion on a declined answer |
| Founder asks to skip Clarify entirely | Refuse briefly, explain the question set is already minimized, run Clarify anyway                                                                                               |

---

## Scope Boundary

**This phase covers asking the fixed Clarify question set ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Recommendation logic (that is Phase 4 — Recommend's job; this phase only
  records answers, it does not apply the precedence rules)
- Re-deriving anything PreScan/Discover already determined
- AWS service names or recommendations

**Your ONLY job: ask what discovery can't answer, record it. Nothing else.**
