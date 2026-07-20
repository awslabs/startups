---
_phase: workshop
_title: "What-If Workshop (Optional)"
_kind: checkpoint
_requires_phase: estimate
_trigger:
  {
    _when: "user opts in post-Estimate (estimate-assemble offer [A], or says what if / reprice / workshop mode / compare scenarios)",
  }
_input:
  - heroku-resource-inventory.json
  - preferences.json
  - aws-design.json
  - estimation-infra.json
_knowledge:
  - { file: references/shared/schema-workshop-scenarios.md }
_fragments:
  - _id: sheet
    _trigger: { _always: true }
    _file: phases/workshop/workshop-sheet.md
  - _id: refresh
    _trigger: { _when: "user chose Apply & reprice" }
    _file: phases/workshop/workshop-refresh.md
  - _id: compare
    _trigger: { _when: "user chose Compare scenarios OR after a successful refresh" }
    _file: phases/workshop/workshop-compare.md
_assemble:
  _file: phases/workshop/workshop-assemble.md
_produces:
  - scenarios/index.json
_interactive: true
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_file_exists:
      [
        heroku-resource-inventory.json,
        preferences.json,
        aws-design.json,
        estimation-infra.json,
      ]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: scenarios/index.json
    _on_failure: _warn_and_skip
---

# Phase: What-If Workshop (Checkpoint)

> **Checkpoint** (`_kind: checkpoint`), not a backbone step — same class as
> `feedback`. Entered only when its `_trigger` fires; has **no** `_advances_to`;
> never becomes `current_phase`. Returns control to the Estimate→Generate flow.
> Contract: `references/shared/schema-workshop-scenarios.md`.

**Execute ALL steps in order. Do not skip or deviate.**

## Entry

1. Preconditions above must pass. Do **not** re-run Discover / live CLI / Terraform parse.
2. If `phases.generate` (or later) is `completed`, apply Estimate `_re_entry_guard`
   confirm → `reset_downstream_to_pending` before refreshing.
3. Set `phases.workshop` to `"in_progress"` (do not change `current_phase` —
   checkpoints never own it). Prefer leaving `current_phase` at `estimate` until
   the user exits workshop to Generate (see `estimate-assemble.md` deferred
   advance).

## Loop

1. If `scenarios/index.json` missing → `workshop-refresh.md` § Baseline capture.
2. `workshop-sheet.md` — present knobs + actions.
3. Branch:
   - **Apply & reprice** → `workshop-refresh.md` (inner Design/Estimate) →
     `workshop-compare.md`
   - **Compare scenarios** → `workshop-compare.md`
   - **Exit to Generate** → `workshop-assemble.md` (resolve checkpoint) → return
   - **Exit to full Clarify** → danger; Clarify re-entry only on explicit confirm

## Hard rules

| Rule                  | Behavior                                                       |
| --------------------- | -------------------------------------------------------------- |
| Inventory frozen      | Never write inventory or `capture/`                            |
| Inner Design/Estimate | Artifact rewrite only — see `workshop-refresh.md` § Inner runs |
| Max 5 scenarios       | Warn + name eviction before delete                             |
| Working tree = active | prefs / design / estimation match active scenario              |
| No Generate in loop   | Mark stale via re-entry; user confirms                         |

## Decline without entering

When Estimate offer **[B] Proceed toward Generate** is chosen, do not enter this
phase's fragments — mark `phases.workshop` `"completed"` (resolved/declined) per
checkpoint semantics in `INTERPRETER.md`, then advance `current_phase` to
`generate`.
