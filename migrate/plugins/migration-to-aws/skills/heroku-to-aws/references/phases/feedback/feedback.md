---
_phase: feedback
_title: "Feedback (Optional)"
_requires_phase: discover
_input: "**/.phase-status.json"
_fragments:
  - _id: collect
    _trigger: { _always: true }
    _file: phases/feedback/feedback-collect.md
_assemble:
  _file: phases/feedback/feedback-assemble.md
_produces:
  - feedback.json
  - trace.json
_advances_to: complete
---

# Phase 6: Feedback (Optional)

Collects user feedback and generates a shareable migration plan link. Reuses the shared feedback infrastructure (trace builder, payload encoder) adapted for Heroku-to-AWS's flat resource model.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Sub-Files

- **feedback-collect.md** → the collection work: detect IDE/version, build the anonymized trace, present the survey link, optionally generate a share link, and write `feedback.json`.
- **feedback-assemble.md** → the assembler: output gate, phase-status update, and marking the migration complete.

This is the terminal phase — `_advances_to: complete`. There is no next phase to load.

---

## Prerequisites

Read `$MIGRATION_DIR/.phase-status.json`. Verify `phases.discover == "completed"`.
If not: **STOP**. Output: "Feedback requires at least the Discover phase to be completed."

---

## Step 1: Collect Feedback

Load `references/phases/feedback/feedback-collect.md` and follow it. It detects the
IDE + plugin version, builds the anonymized trace (`trace.json`), presents the survey
link, optionally generates a shareable plan link, and writes `feedback.json`.

---

## Step 2: Assemble and Complete

Load `references/phases/feedback/feedback-assemble.md` (the phase's assembler) and
follow it to enforce the output gate, update `.phase-status.json`, and mark the
migration complete. It owns the final artifact-level contract for this phase.
