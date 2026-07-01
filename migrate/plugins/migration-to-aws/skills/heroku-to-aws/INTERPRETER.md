# Interpreter

How to read and act on the structured frontmatter that phase files carry. This is
the runtime contract: when a phase file begins with a `---` YAML block, read it
first and act on the keys below, then execute the phase's prose body.

Frontmatter is being introduced phase-by-phase. A phase file with no frontmatter
runs entirely from its prose, as before.

## Phase frontmatter keys

| Key                 | Meaning                                                                                                                                        |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `_phase` / `_title` | the phase's id and human title                                                                                                                 |
| `_requires_phase`   | the phase that must be `completed` before this one may start (omitted for the first phase)                                                     |
| `_init`             | `true` only on the first phase — this phase establishes migration state before its fragments run (see below)                                   |
| `_input`            | what the phase reads — prior-phase artifacts, or `workspace` for the initial file scan                                                         |
| `_fragments`        | the ordered units of work the phase composes. Each is `{ _id, _trigger, _file }`. Load + follow a fragment's `_file` when its `_trigger` fires |
| `_assemble`         | the single terminal unit (`{ _file }`) that combines the fragment outputs into the phase's artifact(s)                                         |
| `_produces`         | the artifact file(s) the phase writes                                                                                                          |
| `_advances_to`      | the phase that runs next on success                                                                                                            |

### `_trigger` forms

- `{ _always: true }` — the fragment always runs.
- `{ _glob: "<pattern>" }` — the fragment runs when one or more files matching the glob exist in the workspace; otherwise it is skipped.
- `{ _when: "<condition>" }` — the fragment runs when the prose condition holds (evaluated by you, the interpreter, against the phase's inputs); otherwise it is skipped. The condition is opaque prose — CI validates only that the form is well-formed, not the condition's truth. Used for fragments gated on a preference or a design-artifact shape (e.g. the EKS branches, gated on the Kubernetes preference / an `eks_cluster` design entry).

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
     If the `_init` phase is already `completed`, apply the re-entry rules (see the
     phase's prose and `shared/handoff-gates.md`) before proceeding.
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
