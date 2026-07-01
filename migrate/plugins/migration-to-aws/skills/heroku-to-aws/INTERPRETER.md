# Interpreter

How to read and act on the structured frontmatter that phase files carry. This is
the runtime contract: when a phase file begins with a `---` YAML block, read it
first and act on the keys below, then execute the phase's prose body.

Frontmatter is being introduced phase-by-phase. A phase file with no frontmatter
runs entirely from its prose, as before.

## Phase frontmatter keys

| Key                 | Meaning                                                                                                                                                                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_phase` / `_title` | the phase's id and human title                                                                                                                                                                                                                                                  |
| `_kind`             | `backbone` (default when absent) or `checkpoint`. A **backbone** phase is a step on the linear lifecycle (see below). A **checkpoint** phase is off-backbone — optional, entered by a phase-level `_trigger`, returns control instead of advancing. `feedback` is a checkpoint. |
| `_requires_phase`   | the phase that must be `completed` before this one may start (omitted for the first phase; on a checkpoint, its minimum precondition)                                                                                                                                           |
| `_init`             | `true` only on the first phase — this phase establishes migration state before its fragments run (see below)                                                                                                                                                                    |
| `_input`            | what the phase reads — prior-phase artifacts, or `workspace` for the initial file scan                                                                                                                                                                                          |
| `_trigger`          | (checkpoint phases only) how the phase is ENTERED — same forms as a fragment `_trigger` (below). `feedback` uses `_when: "user opts in"`. Backbone phases have no phase-level `_trigger` (they are advanced INTO via a predecessor's `_advances_to`).                           |
| `_fragments`        | the ordered units of work the phase composes. Each is `{ _id, _trigger, _file }`. Load + follow a fragment's `_file` when its `_trigger` fires                                                                                                                                  |
| `_assemble`         | the single terminal unit (`{ _file }`) that combines the fragment outputs into the phase's artifact(s)                                                                                                                                                                          |
| `_produces`         | the artifact file(s) the phase writes                                                                                                                                                                                                                                           |
| `_advances_to`      | (backbone phases only) the phase that runs next on success — or a terminal (`complete`). A checkpoint has NO `_advances_to`.                                                                                                                                                    |
| `_re_entry_guard`   | (backbone phases with a downstream only) the stale-downstream guard — STOP re-running this phase if its downstream phase already completed, unless the user confirms (see below). Terminal phases and checkpoints have none.                                                    |
| `_preconditions`    | the entry gate — an ordered list of checks that MUST pass before the phase does any work (predecessor completed, single active phase, inputs present/valid). See § Gate protocol.                                                                                               |
| `_postconditions`   | the completion gate — an ordered list of checks that MUST pass before the phase is marked `completed` and control advances. See § Gate protocol.                                                                                                                                |
| `_forbids_files`    | a glob list of files/dirs this phase MUST NOT create (scope boundary). See § Gate protocol.                                                                                                                                                                                     |

### `_trigger` forms

- `{ _always: true }` — the fragment always runs.
- `{ _glob: "<pattern>" }` — the fragment runs when one or more files matching the glob exist in the workspace; otherwise it is skipped.
- `{ _when: "<condition>" }` — the fragment runs when the prose condition holds (evaluated by you, the interpreter, against the phase's inputs); otherwise it is skipped. The condition is opaque prose — CI validates only that the form is well-formed, not the condition's truth. Used for fragments gated on a preference or a design-artifact shape (e.g. the EKS branches, gated on the Kubernetes preference / an `eks_cluster` design entry).

### `_re_entry_guard` — stale-downstream re-entry

A backbone phase whose downstream phase has already completed is unsafe to re-run
silently: its artifact feeds the downstream, so overwriting it leaves the
downstream artifact stale. `_re_entry_guard` encodes that check. It has four keys,
all required when the guard is present:

| Key                   | Meaning                                                                                                    |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `_stale_if_completed` | the downstream phase whose `"completed"` status makes re-running THIS phase unsafe (equals `_advances_to`) |
| `_stale_artifact`     | the downstream artifact named in the `GATE_FAIL` line (one of that downstream phase's `_produces`)         |
| `_on_reentry`         | what to do on re-entry — `stop_unless_confirmed` (the only value today)                                    |
| `_on_confirm`         | what to do when the user confirms the re-run — `reset_downstream_to_pending` (the only value today)        |

**Enforcement (at this phase's completion gate, BEFORE the phase's checks):**

1. Read `.phase-status.json`. If `phases.<_stale_if_completed>` is NOT
   `"completed"`, the guard does not fire — proceed normally.
2. If it IS `"completed"` **and** the user has not explicitly confirmed re-running
   this phase: **STOP**. Emit exactly:

   ```
   GATE_FAIL | phase=<this phase's _phase> | field=<_stale_artifact> | reason=stale_downstream
   ```

   Do NOT modify artifacts. Do NOT update `.phase-status.json`. Tell the user the
   downstream work may be stale and they must confirm the re-run.
3. If the user HAS explicitly confirmed the re-run (`_on_confirm:
   reset_downstream_to_pending`): before proceeding, set every phase downstream of
   this one (its `_advances_to` and everything after it on the backbone) back to
   `"pending"` in `.phase-status.json`. Then run the phase normally.

`phase=` and `reason=stale_downstream` are NOT stored in the frontmatter — you
reconstruct the `GATE_FAIL` line from this phase's `_phase` plus the constant
`stale_downstream` reason. This guard is the single source of truth for
stale-downstream re-entry; there is no separate per-phase prose or shared-file
table for it.

## Gate protocol

The LLM runs two gates around each phase, reading them from frontmatter. This is
heroku-to-aws's own gate contract — phases do NOT load any shared gate file.

### Check kinds (used in `_preconditions` and `_postconditions`)

Each entry is a single check plus an `_on_failure` action (see the `_on_error`
dictionary below). Closed vocabulary of check kinds:

| Check                        | Arg                       | Passes when                                                    |
| ---------------------------- | ------------------------- | -------------------------------------------------------------- |
| `_check_phase_completed`     | a phase name              | `.phase-status.json` `phases.<name> == "completed"`            |
| `_check_single_active_phase` | `true`                    | at most one core phase is `in_progress`                        |
| `_check_file_exists`         | filename or `[names]`     | each named file exists in `$MIGRATION_DIR/`                    |
| `_validate_json`             | filename or `[names]`     | each named file parses as valid JSON                           |
| `_assert`                    | an opaque prose predicate | you (the interpreter) evaluate the prose against the artifacts |

`_assert` is the JUDGMENT escape hatch: arithmetic (e.g. the Property-16 total ==
sum invariant), enum-membership over an artifact's runtime content (e.g.
`recommendation.path ∈ {...}`), and conditionals (e.g. "if Postgres in inventory
→ `database_ha` set") are `_assert` prose, NOT structured checks — CI cannot open a
runtime artifact to verify them, so the interpreter evaluates them. CI validates
only that the `_assert` form is well-formed, never the predicate's truth (same
policy as `_when`).

### `_on_error` actions

Every `_on_failure:` names one of these. Each is an effect plus a phase-status
transition:

| Action              | Effect                                     | Phase status         |
| ------------------- | ------------------------------------------ | -------------------- |
| `_warn_and_skip`    | record a warning; skip this item; continue | remain `in_progress` |
| `_default_and_warn` | apply a documented default; warn; continue | remain `in_progress` |
| `_halt_and_inform`  | stop; surface a diagnostic to the user     | retain `in_progress` |
| `_unrecoverable`    | stop; surface an error                     | revert to `pending`  |

### `_preconditions` — the entry gate

Before the phase does ANY work, run each `_preconditions` check in order. On a
failure, apply that check's `_on_failure` action. A `_halt_and_inform` /
`_unrecoverable` failure STOPS the phase (it does not proceed to its fragments).
Only when all preconditions pass does the phase set itself `in_progress` and run.

### `_postconditions` — the completion gate

Before the phase is marked `"completed"` and control advances, **re-read the
relevant artifacts from disk** (do not trust chat memory), then run each
`_postconditions` check in order.

- **On any failure:** apply the `_on_failure` action and emit exactly:

  ```
  GATE_FAIL | phase=<this phase's _phase> | field=<the failing file/field> | reason=<missing|invalid>
  ```

  Do NOT modify artifacts to force a gate to pass. Do NOT update
  `.phase-status.json`. Do NOT advance. Tell the user which phase to re-run.

- **On all-pass:** emit exactly:

  ```
  HANDOFF_OK | phase=<this phase's _phase> | artifacts=<comma-separated files verified>
  ```

  then update `.phase-status.json` (set this phase `"completed"`, set
  `current_phase` to `_advances_to`, update the timestamp) in the same turn.

`phase=` is reconstructed from the phase's own `_phase` (not stored in each check).
The orchestrator (SKILL.md) MUST NOT load the next phase until it sees the
`HANDOFF_OK` line; a completion message without it is not a valid handoff.

### `_forbids_files` — scope boundary

A glob list of files/directories the phase MUST NOT create. After the phase runs,
if any path matching a `_forbids_files` glob was written, that is a scope
violation — treat it as a `_postconditions` failure. This encodes the per-phase
"do not emit README.md / *.txt / downstream artifacts" boundaries.

### Backbone vs checkpoint phases

A **backbone** phase (the default) is a step on the linear lifecycle: it is
advanced into by its predecessor's `_advances_to`, and it advances to the next
phase (or the `complete` terminal). The backbone is
`discover → clarify → design → estimate → generate → complete`.

A **checkpoint** phase (`_kind: checkpoint`, e.g. `feedback`) is OFF the backbone.
It is optional, entered only when its phase-level `_trigger` fires (e.g. the user
opts in), and it returns control to the flow rather than advancing `current_phase`
— so it has no `_advances_to`, and it never appears as a `current_phase` value.
WHERE a checkpoint is offered is orchestration prose (see SKILL.md), not part of
the phase contract.

**Checkpoint status semantics (important):** marking a checkpoint's
`phases.<checkpoint>` as `"completed"` means the checkpoint was RESOLVED (offered
and dealt with) — NOT that the user participated. A declined checkpoint is still
`"completed"` (the lifecycle is resolved, so the migration can terminate cleanly).
Whether the user actually participated is a SEPARATE signal, carried by the
presence of the checkpoint's artifact (e.g. `feedback.json` exists only if the
user engaged). Do not conflate "checkpoint resolved" with "user participated."

## Fragment unit keys

Each fragment file (named by a phase's `_fragments[]._file`) carries its own frontmatter:

| Key            | Meaning                                                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `_fragment`    | the fragment's id — must match the `_id` the phase's `_fragments` list uses to reference it                                                 |
| `_of_phase`    | the phase this fragment belongs to                                                                                                          |
| `_contributes` | the artifact section(s) this fragment writes into (fragments contribute to the phase's artifact; they do not each create a standalone file) |

## Assembler unit keys

The assembler file (named by a phase's `_assemble._file`) carries:

| Key         | Meaning                                                                                       |
| ----------- | --------------------------------------------------------------------------------------------- |
| `_assemble` | the assembler's id                                                                            |
| `_of_phase` | the phase this assembler belongs to                                                           |
| `_reads`    | the fragment contributions it combines                                                        |
| `_produces` | the artifact file(s) it creates — the assembler is the single creator of the phase's artifact |

## `_init: true` — establish migration state

When the phase being entered has `_init: true`, perform migration-state setup
BEFORE running any of its fragments. This replaces what was previously written
out as a per-phase "initialize" step.

1. Check for an existing `.migration/` directory at the project root.
   - **If existing runs are found:** list them with their phase status and ask:
     - `[A] Resume: Continue with [latest run]`
     - `[B] Fresh: Create new migration run`
     - `[C] Cancel`
   - **If resuming:** set `$MIGRATION_DIR` to the selected run's directory. Read
     its `.phase-status.json` and validate it per the State Machine in `SKILL.md`.
     If the `_init` phase is already `completed`, apply the re-entry rules (see
     the phase's `_re_entry_guard` frontmatter and § `_re_entry_guard` above)
     before proceeding.
   - **If fresh, or no existing runs:** continue to step 2.

2. Create `.migration/[MMDD-HHMM]/` (e.g. `.migration/0315-1030/`) using the
   current timestamp (MMDD = month/day, HHMM = hour/minute). Set `$MIGRATION_DIR`
   to this new directory.

3. Create `.migration/.gitignore` (if not already present) with exact content:

   ```
   # Auto-generated migration state (temporary, do not commit)
   *
   !.gitignore
   ```

   This prevents accidental commits of migration artifacts.

4. Write `.phase-status.json` with the exact schema (schema reference:
   `shared/schema-phase-status.md`):

   ```json
   {
     "migration_id": "[MMDD-HHMM]",
     "last_updated": "[ISO 8601 timestamp]",
     "current_phase": "discover",
     "phases": {
       "discover": "in_progress",
       "clarify": "pending",
       "design": "pending",
       "estimate": "pending",
       "generate": "pending",
       "feedback": "pending"
     }
   }
   ```

5. Confirm both `.migration/.gitignore` and `.phase-status.json` exist before
   running the phase's fragments.
