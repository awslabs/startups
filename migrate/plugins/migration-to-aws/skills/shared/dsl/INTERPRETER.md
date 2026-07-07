# Interpreter

The plugin-shared contract for DSL-driven migration skills: how to read and act on
the structured frontmatter that phase files carry. It is skill-AGNOSTIC — any
migration skill under this plugin can author its phases to this grammar and drive
execution from this one interpreter. When a phase file begins with a `---` YAML
block, read it first and act on the keys below, then execute the phase's prose body.

Frontmatter is being introduced phase-by-phase. A phase file with no frontmatter
runs entirely from its prose, as before.

## The interpreter loop

This is the execution controller — how you drive a migration from invocation to
completion. It is skill-agnostic: the phase set, ordering, and per-phase behavior
are all DERIVED from the phase files' frontmatter (never hardcoded here).

**On each invocation:**

1. **Load state.** Find the run directory under `.migration/` and read its
   `.phase-status.json`. If none exists, this is a COLD START: load the skill's
   DECLARED entry phase (the skill's SKILL.md names it) and run it — it carries
   `_init: true` and establishes state (see § `_init`). Do NOT scan every phase's
   frontmatter to find the root; the skill declares its own entry so this is a
   single, direct load. (The entry phase is, by contract, the backbone head — the
   one phase with no `_requires_phase` and with `_init: true`; CI enforces that
   these coincide, so the declared entry is unambiguous.)
2. **Determine the current phase (deterministic):**
   - If `current_phase` is present in `.phase-status.json`, use it (it is
     authoritative). This is the normal WARM-START path.
   - Otherwise (state exists but has no `current_phase`) walk the backbone in order
     (see § Backbone vs checkpoint) and pick the FIRST phase whose
     `phases.<phase>` is not `"completed"`. If all backbone phases are
     `"completed"`, the state is the terminal (`complete`). (On a cold start there
     is no state to read — step 1's declared entry phase is used directly.)
3. **Validate state before proceeding.** See § State-file validation below. STOP
   on any inconsistency rather than guessing.
4. **Load the phase orchestrator.** A phase's orchestrator file is, by convention,
   `references/phases/<phase>/<phase>.md`. Load it in full and read its
   frontmatter first.
5. **Run the phase.** Run its `_preconditions` entry gate (§ Gate protocol); if it
   passes, set the phase `in_progress`, run its `_fragments` (each when its
   `_trigger` fires) then its `_assemble`; then run its `_postconditions`
   completion gate.
6. **Advance only on `HANDOFF_OK`.** A phase is complete ONLY when its completion
   gate emits the `HANDOFF_OK` line (§ Gate protocol). On `GATE_FAIL`, STOP — do
   not update `.phase-status.json`, do not load the next phase; tell the user
   which phase to re-run. Never load the next phase from a completion message that
   lacks `HANDOFF_OK`.
7. **Update state.** After `HANDOFF_OK`, apply the phase-status update protocol
   below, then load the next phase — the current phase's `_advances_to` — and
   repeat from step 4. When `_advances_to` is a terminal (`complete`), the
   migration is complete.

Checkpoint phases (§ Backbone vs checkpoint) are OFF this loop — they are entered
by their own `_trigger` at a point the skill's orchestrator (SKILL.md) chooses,
and return control without changing `current_phase`.

### State discipline

- **Single run directory.** Use ONE `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`)
  for the entire migration; do not mix artifacts across `.migration/*/` sessions.
- **Re-read from disk.** Before each phase and before each gate, read the required
  artifacts from `$MIGRATION_DIR/`. Do not rely on chat memory.

### Phase-status update protocol (read-merge-write)

Update `.phase-status.json` with read-merge-write, never a blind overwrite:

1. Read the current file before every update.
2. Change only the phase key(s) being advanced and `last_updated`.
3. Leave prior completed phases unchanged.
4. Set `current_phase` to the next phase (the completed phase's `_advances_to`),
   or the terminal (`complete`) when the backbone is exhausted.
5. Write the full file in the same turn as the phase's final output message.

Status values progress `"pending"` → `"in_progress"` → `"completed"` and never go
backward (except a confirmed re-entry reset — see § `_re_entry_guard`). At most one
backbone phase is `"in_progress"` at a time.

### State-file validation

When reading `.phase-status.json`, STOP (surface the diagnostic, do not proceed or
guess) on any of:

1. **Multiple run directories** under `.migration/`: list them with their phase
   status and ask `[A] Resume latest / [B] Start fresh / [C] Cancel`.
2. **Invalid JSON:** "State file corrupted (invalid JSON). Delete the file and
   restart the current phase."
3. **Unrecognized phase name** in `phases` (not a phase the skill declares).
4. **Unrecognized status** (not `pending` / `in_progress` / `completed`).
5. **Invalid `current_phase`** (present but not a declared phase or the terminal).
6. **Out-of-order completion:** a later backbone phase is `"completed"` while an
   earlier one is not — "Inconsistent phase ordering detected. Reconcile
   `.phase-status.json` before resuming."

(The single-active-phase invariant is enforced structurally by the first phase's
`_preconditions._check_single_active_phase`; see § Gate protocol.)

## Phase frontmatter keys

| Key                 | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_phase` / `_title` | the phase's id and human title                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `_kind`             | `backbone` (default when absent) or `checkpoint`. A **backbone** phase is a step on the linear lifecycle (see below). A **checkpoint** phase is off-backbone — optional, entered by a phase-level `_trigger`, returns control instead of advancing. `feedback` is a checkpoint.                                                                                                                                                                                                                                                                  |
| `_requires_phase`   | the phase that must be `completed` before this one may start (omitted for the first phase; on a checkpoint, its minimum precondition)                                                                                                                                                                                                                                                                                                                                                                                                            |
| `_init`             | `true` only on the first phase — this phase establishes migration state before its fragments run (see below)                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `_input`            | what the phase reads — prior-phase artifacts, or `workspace` for the initial file scan                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `_knowledge`        | the reference/data files the phase consults (`knowledge/**.json` sizing/mapping/pricing tables). Each entry is `{ file, _when? }`; each `file` must resolve on disk. Load a knowledge file ONLY when its `_when` holds — see § `_knowledge`.                                                                                                                                                                                                                                                                                                     |
| `_trigger`          | (checkpoint phases only) how the phase is ENTERED — same forms as a fragment `_trigger` (below). `feedback` uses `_when: "user opts in"`. Backbone phases have no phase-level `_trigger` (they are advanced INTO via a predecessor's `_advances_to`).                                                                                                                                                                                                                                                                                            |
| `_fragments`        | the ordered units of work the phase composes. Each is `{ _id, _trigger, _file }`. Load + follow a fragment's `_file` when its `_trigger` fires                                                                                                                                                                                                                                                                                                                                                                                                   |
| `_assemble`         | the single terminal unit (`{ _file }`) that combines the fragment outputs into the phase's artifact(s)                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `_produces`         | the artifact file(s) the phase writes. Each entry is either a bare filename (unconditional) or an inline conditional map `{ file: <path>, _when: <prose> }` — an artifact produced ONLY when the design predicate holds (e.g. `terraform/eks.tf` only when EKS is in the design). Same `{ file, _when }` shape as `_knowledge`; `_when` is opaque prose the interpreter reads at runtime and CI does NOT evaluate. A trailing-slash `file` (e.g. `kubernetes/`) names a produced DIRECTORY when the unit emits a set of dynamically-named files. |
| `_advances_to`      | (backbone phases only) the phase that runs next on success — or a terminal (`complete`). A checkpoint has NO `_advances_to`.                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `_re_entry_guard`   | (backbone phases with a downstream only) the stale-downstream guard — STOP re-running this phase if its downstream phase already completed, unless the user confirms (see below). Terminal phases and checkpoints have none.                                                                                                                                                                                                                                                                                                                     |
| `_preconditions`    | the entry gate — an ordered list of checks that MUST pass before the phase does any work (predecessor completed, single active phase, inputs present/valid). See § Gate protocol.                                                                                                                                                                                                                                                                                                                                                                |
| `_postconditions`   | the completion gate — an ordered list of checks that MUST pass before the phase is marked `completed` and control advances. See § Gate protocol.                                                                                                                                                                                                                                                                                                                                                                                                 |
| `_forbids_files`    | a glob list of files/dirs this phase MUST NOT create (scope boundary). See § Gate protocol.                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

### `_knowledge` — conditional data loading

`_knowledge` declares a phase's (or assembler's) data dependencies: the
`knowledge/**.json` lookup tables it consults (sizing, mapping, pricing). Each
entry is `{ file, _when? }` — the same shape as `_produces` conditional artifacts.

- Load a knowledge file **only when its `_when` predicate holds** against the
  phase's inputs. Do NOT speculatively load knowledge for resource types absent
  from the inventory. A bare entry (no `_when`) is always loaded.
- `_when` is opaque prose the interpreter evaluates at runtime; CI validates only
  that each `file` resolves on disk (skill-root relative, handling the `../shared/`
  climb), never the predicate's truth (same policy as `_trigger._when`).

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
phase (or the `complete` terminal). The backbone is the chain of backbone phases
wired by `_advances_to` (forward) and `_requires_phase` (backward), from the first
phase (no `_requires_phase`) to the one whose `_advances_to` is the terminal
`complete`. The interpreter derives this chain from the phase frontmatter; it is
not hardcoded. The head of the backbone (the phase with no `_requires_phase`) is
the skill's entry phase and carries `_init: true`; the skill names it in SKILL.md
so a cold start loads it directly rather than scanning to find it (see § The
interpreter loop, step 1).

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

A phase has 1..N fragments and exactly one assembler. A fragment does one unit of
work and writes its own contribution; fragments are independent (none reads
another's output). The assembler runs last and combines/validates the fragments'
contributions into the phase's artifact(s).

Each fragment file (named by a phase's `_fragments[]._file`) carries its own frontmatter:

| Key            | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_fragment`    | the fragment's id — must match the `_id` the phase's `_fragments` list uses to reference it                                                                                                                                                                                                                                                                                                                              |
| `_of_phase`    | the phase this fragment belongs to                                                                                                                                                                                                                                                                                                                                                                                       |
| `_contributes` | the artifact section(s) this fragment writes into (fragments contribute to the phase's artifact; they do not each create a standalone file). Same entry forms as `_produces`: a bare filename, or a conditional `{ file: <path>, _when: <prose> }` when the fragment only emits that artifact under a design predicate (e.g. the EKS fragment contributes `terraform/eks.tf` / `kubernetes/` only when EKS is selected). |

## Assembler unit keys

The assembler file (named by a phase's `_assemble._file`) carries:

| Key          | Meaning                                                                                                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_assemble`  | the assembler's id                                                                                                                                                                         |
| `_of_phase`  | the phase this assembler belongs to                                                                                                                                                        |
| `_reads`     | the fragment contributions it combines                                                                                                                                                     |
| `_knowledge` | reference/data files it loads (same shape as a phase's `_knowledge`: `{ file, _when? }`); each `file` must resolve on disk                                                                 |
| `_produces`  | the artifact file(s) it creates — the assembler is the single creator of the phase's artifact. Same entry forms as a phase's `_produces` (bare filename or conditional `{ file, _when }`). |

## `_init: true` — establish migration state

When the phase being entered has `_init: true`, perform migration-state setup
BEFORE running any of its fragments. This replaces what was previously written
out as a per-phase "initialize" step. Exactly one phase per skill carries `_init:
true` — the backbone head / declared entry phase — so this setup runs once, on the
cold start that begins a migration.

1. Check for an existing `.migration/` directory at the project root.
   - **If existing runs are found:** list them with their phase status and ask:
     - `[A] Resume: Continue with [latest run]`
     - `[B] Fresh: Create new migration run`
     - `[C] Cancel`
   - **If resuming:** set `$MIGRATION_DIR` to the selected run's directory. Read
     its `.phase-status.json` and validate it per § The interpreter loop
     (State-file validation). If the `_init` phase is already `completed`, apply
     the re-entry rules (see the phase's `_re_entry_guard` frontmatter and
     § `_re_entry_guard` above) before proceeding.
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

4. Write `.phase-status.json` per the schema
   `../shared/state/phase-status.schema.json`. Seed `phases` with ONE entry per
   phase the skill declares (its phase files), all `"pending"` EXCEPT this `_init`
   phase which is `"in_progress"`; set `migration_id` to `[MMDD-HHMM]`,
   `last_updated` to the current ISO 8601 timestamp, and `current_phase` to this
   `_init` phase. (The schema does not enumerate phase names — the valid names are
   the skill's declared phases.)

5. Confirm both `.migration/.gitignore` and `.phase-status.json` exist before
   running the phase's fragments.
