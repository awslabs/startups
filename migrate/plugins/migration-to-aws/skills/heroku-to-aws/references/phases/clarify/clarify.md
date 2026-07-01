---
_phase: clarify
_title: "Clarify Requirements"
_requires_phase: discover
_input:
  - heroku-resource-inventory.json
_fragments:
  - _id: interview
    _trigger: { _always: true }
    _file: phases/clarify/clarify-interview.md
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - preferences.json
_advances_to: design
---

# Phase 2: Clarify Requirements

**Phase 2 of 6** — Ask adaptive questions before design begins, then interpret answers into ready-to-apply design constraints.

> **HARD GATE — Clarify before Design:** Do not load `references/phases/design/design.md` (or any later phase) until this phase finishes **and** `$MIGRATION_DIR/.phase-status.json` records `phases.clarify` as `"completed"`. Writing `preferences.json` without updating phase status is a protocol violation. If the user asks to skip questions, use documented defaults and still complete this phase (including phase status).

The output — `preferences.json` — is consumed directly by Design and Estimate without any further interpretation.

Questions are organized into **three batches** (≤7 per batch) presented sequentially. A standalone **fast-path** mode exists for simple stacks (< 5 apps, no Private Spaces, no Kafka).

---

## Sub-Files

- **clarify-interview.md** → the adaptive interview: prior-run check, fast-path gate, active-question selection, and the progressive-batch Q&A (with the full Question Catalog + Defaults Table). Interprets answers into `preferences.json` fields.
- **clarify-assemble.md** → the assembler: assembles + writes the final `preferences.json`, runs the validation checklist + completion handoff gate, and updates `.phase-status.json`.

---

## Step 1: Run the Interview

Load `references/phases/clarify/clarify-interview.md` and follow it. It handles the
prior-run check, determines fast-path eligibility, selects the active question set,
and presents the questions in progressive batches — interpreting each answer.

---

## Step 2: Assemble and Validate

Load `references/phases/clarify/clarify-assemble.md` (the phase's assembler) and
follow it to assemble the final `preferences.json`, run the validation checklist +
completion handoff gate, and update `.phase-status.json`. It owns the artifact-level
contract for this phase.

---

## Scope Boundary

**This phase covers requirements gathering ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Detailed AWS architecture or service configurations
- Code migration examples or SDK snippets
- Detailed cost calculations
- Migration timelines or execution plans
- Terraform generation
- Dyno-to-Fargate sizing decisions
- Database instance class selection

**Your ONLY job: Understand what the user needs. Nothing else.**
