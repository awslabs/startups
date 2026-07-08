# Grammar reference

Every frontmatter key in the DSL, its shape, its meaning, and a real example pulled
from `skills/heroku-to-aws/`. This is a lookup — read [01-concepts.md](01-concepts.md)
first for the model.

**Authoritative sources** (these win on any disagreement): the shapes are
`tools/frontmatter-validator/types.ts`; the closed vocabulary is
`tools/frontmatter-validator/parse.ts`; the runtime meaning is
`skills/shared/dsl/INTERPRETER.md`.

## The closed vocabulary

Every `_`-prefixed key is closed: a key not in the set for its unit kind is a
`unknown … frontmatter key` finding (a typo fails the build rather than being
silently ignored). The sets, verbatim from `parse.ts`:

- **Phase keys (18):** `_phase`, `_title`, `_kind`, `_requires_phase`, `_init`,
  `_interactive`, `_input`, `_fragments`, `_trigger`, `_assemble`, `_produces`,
  `_advances_to`, `_exec`, `_re_entry_guard`, `_preconditions`, `_postconditions`,
  `_forbids_files`, `_knowledge`.
- **Fragment keys (3):** `_fragment`, `_of_phase`, `_contributes`.
- **Assembler keys (5):** `_assemble`, `_of_phase`, `_reads`, `_produces`,
  `_knowledge`.
- **Check kinds (5):** `_check_phase_completed`, `_check_single_active_phase`,
  `_check_file_exists`, `_validate_json`, `_assert`.
- **`_on_failure` / `_on_error` actions (4):** `_warn_and_skip`, `_default_and_warn`,
  `_halt_and_inform`, `_unrecoverable`.
- **Re-entry guard sub-keys (4):** `_stale_if_completed`, `_stale_artifact`,
  `_on_reentry`, `_on_confirm`.
- **`_exec` sub-keys (1):** `_agent`. Its value is a capability tier from the closed
  set `ro` \| `rw` \| `git`.

## Unit file structure

A unit file (phase orchestrator, fragment, or assembler) is: a `---`-fenced YAML
frontmatter block, then an optional `# H1`, then prose (`## Step:` sections and
orientation). The frontmatter is the only structural source of truth; the prose is
procedure the LLM executes.

---

## Phase frontmatter

The phase orchestrator file `references/phases/<name>/<name>.md` composes the phase.

### Identity & role

| Key               | Shape                      | Meaning                                                                                                           |
| ----------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `_phase`          | string                     | the phase's id (matches the directory/file name)                                                                  |
| `_title`          | string                     | human title                                                                                                       |
| `_kind`           | `backbone` \| `checkpoint` | `backbone` (default when absent) = a step on the linear lifecycle; `checkpoint` = off-backbone, trigger-entered   |
| `_requires_phase` | phase name                 | the phase that must be `completed` before this one starts (omitted on the head phase)                             |
| `_init`           | `true`                     | present only on the backbone head — this phase bootstraps migration state before its fragments run                |
| `_interactive`    | `true` \| `false`          | (optional) does the phase's WORK prompt the user? `_exec` requires `false`; absent/`true` = the phase runs inline |

### Composition

| Key          | Shape                                                   | Meaning                                                                                                                  |
| ------------ | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `_fragments` | ordered list of `{ _id, _trigger, _file }`              | the units of work; each is loaded + run when its `_trigger` fires (below)                                                |
| `_assemble`  | `{ _file }`                                             | the single terminal assembler — **mandatory**, exactly one per phase                                                     |
| `_input`     | scalar or list — `workspace`, a glob, or artifact names | what the phase reads (the initial file scan, the phase-status glob, or upstream artifacts)                               |
| `_knowledge` | list of `{ file, _when? }`                              | JSON data dependencies (sizing/pricing/mapping tables); loaded only when `_when` holds; each `file` must resolve on disk |

### Lifecycle & flow

| Key               | Shape                                                                | Meaning                                                                                                                                                                                                        |
| ----------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_advances_to`    | phase name or a terminal (`complete`)                                | the next phase on success (backbone only; a checkpoint has none)                                                                                                                                               |
| `_exec`           | `{ _agent: ro \| rw \| git }`                                        | (optional) run the phase's WORK (fragments + assembler) in an isolated sub-agent at this tier; gates + `_init` + state transition stay in the main window. Requires `_interactive: false`. Absent = run inline |
| `_trigger`        | a trigger form (below)                                               | **checkpoint phases only** — how the phase is entered; backbone phases have no phase-level trigger                                                                                                             |
| `_re_entry_guard` | `{ _stale_if_completed, _stale_artifact, _on_reentry, _on_confirm }` | stale-downstream guard (backbone phases with a downstream)                                                                                                                                                     |

### Contract

| Key               | Shape                                                | Meaning                                                                                       |
| ----------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `_preconditions`  | ordered list of checks (below)                       | the entry gate — all must pass before the phase does any work                                 |
| `_postconditions` | ordered list of checks (below)                       | the completion gate — all must pass before the phase is `completed` + advances                |
| `_produces`       | list of bare filenames and/or `{ file, _when }` maps | the artifact(s) the phase writes (a mandatory floor, not necessarily exhaustive)              |
| `_forbids_files`  | glob list                                            | files/dirs the phase MUST NOT create (scope boundary; a violation is a postcondition failure) |

### Example — a backbone phase (`design.md`, abridged)

```yaml
_phase: design
_title: "Design AWS Architecture"
_requires_phase: clarify
_input:
  - heroku-resource-inventory.json
  - preferences.json
_knowledge:
  - { file: knowledge/design/dyno-fargate-sizing.json, _when: "inventory has a formation AND kubernetes is ecs-fargate or absent" }
  - { file: knowledge/design/postgres-rds-sizing.json, _when: "inventory has a heroku-postgresql addon" }
_fragments:
  - _id: mapping-engine
    _trigger: { _always: true }
    _file: phases/design/design-mapping.md
  - _id: eks-mapping
    _trigger: { _when: "preferences kubernetes is 'eks-managed' or 'eks-or-ecs'" }
    _file: phases/design/design-eks.md
_assemble:
  _file: phases/design/design-assemble.md
_produces:
  - aws-design.json
_advances_to: estimate
_re_entry_guard:
  _stale_if_completed: estimate
  _stale_artifact: estimation-infra.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_phase_completed: clarify
    _on_failure: _halt_and_inform
  - _check_file_exists: [heroku-resource-inventory.json, preferences.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: aws-design.json
    _on_failure: _halt_and_inform
  - _assert: "every services[] entry has service_id, source_resource_id, aws_service, aws_config"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "terraform/**"
  - estimation-infra.json
```

### Example — a checkpoint phase (`feedback.md`, abridged)

Note: `_kind: checkpoint`, a phase-level `_trigger`, and NO `_advances_to`.

```yaml
_phase: feedback
_title: "Feedback (Optional)"
_kind: checkpoint
_requires_phase: discover
_input: "**/.phase-status.json"
_trigger: { _when: "the user opts in to providing feedback at a feedback checkpoint" }
_fragments:
  - _id: collect
    _trigger: { _always: true }
    _file: phases/feedback/feedback-collect.md
_assemble:
  _file: phases/feedback/feedback-assemble.md
_produces:
  - feedback.json
  - trace.json
_preconditions:
  - _check_phase_completed: discover
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: feedback.json
    _on_failure: _warn_and_skip
```

---

## Fragment frontmatter

A fragment file does one unit of work and writes its contribution to disk.

| Key            | Shape                                                | Meaning                                                                         |
| -------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------- |
| `_fragment`    | string                                               | the fragment's id — **must match** the `_id` the phase's `_fragments` list uses |
| `_of_phase`    | phase name                                           | the phase this fragment belongs to — **must match** the owning phase's `_phase` |
| `_contributes` | list of bare filenames and/or `{ file, _when }` maps | the artifact section(s) this fragment writes into                               |

### Example (`design-mapping.md`)

```yaml
_fragment: mapping-engine
_of_phase: design
_contributes:
  - aws-design.json
```

**`_contributes` rule:** list what the fragment writes _unconditionally given it
runs_. A fragment that is itself trigger-gated (the eks fragment fires only via its
`_when`) lists its outputs **bare** — the conditionality is already captured by the
fragment's trigger. Outputs a fragment emits only under an _internal_ branch (e.g.
"emit `database.tf` only if a DB is present") are the _open tail_ and are NOT listed
at all — they are governed by the fragment's step prose and the phase's `_assert`s.

---

## Assembler frontmatter

Exactly one per phase; runs last; the single creator/mutator of the phase artifact.

| Key          | Shape                                                | Meaning                                                         |
| ------------ | ---------------------------------------------------- | --------------------------------------------------------------- |
| `_assemble`  | string                                               | the assembler's id                                              |
| `_of_phase`  | phase name                                           | the phase this assembler belongs to                             |
| `_reads`     | list                                                 | the fragment contributions it combines                          |
| `_produces`  | list of bare filenames and/or `{ file, _when }` maps | the artifact(s) it creates — the assembler is the creator       |
| `_knowledge` | list of `{ file, _when? }`                           | reference/data files it loads; each `file` must resolve on disk |

### Example (`design-assemble.md`)

```yaml
_assemble: assemble-design
_of_phase: design
_reads:
  - mapping-engine (fragment contribution)
  - eks-mapping (fragment contribution, when EKS selected)
_produces:
  - aws-design.json
```

---

## Shared value grammars

### Trigger forms

A `_trigger` (on a `_fragments[]` entry, or a checkpoint phase's `_trigger`) is one of:

| Form                     | Meaning                                                                          | Checkable?            |
| ------------------------ | -------------------------------------------------------------------------------- | --------------------- |
| `{ _always: true }`      | always runs                                                                      | mechanical            |
| `{ _glob: "<pattern>" }` | runs when ≥1 file matching the glob exists in the workspace                      | mechanical            |
| `{ _when: "<prose>" }`   | runs when the prose condition holds (the LLM decides against the phase's inputs) | **judgment (opaque)** |
| anything else            | parsed as `unknown` → a check flags it                                           | —                     |

A false `_when` trigger skips the fragment silently _and does not even load its file_
(lazy). A misjudged `_when` fails open — it can silently drop an entire fragment — so
put high-consequence branching behind mechanical triggers where you can.

### Check kinds (used in `_preconditions` / `_postconditions`)

Each list entry is one check plus an `_on_failure` action. Six are mechanical
(deterministic recipes); `_assert` is the judgment escape hatch.

| Check                        | Arg                   | Passes when                                         | Kind         |
| ---------------------------- | --------------------- | --------------------------------------------------- | ------------ |
| `_check_phase_completed`     | a phase name          | `.phase-status.json` `phases.<name> == "completed"` | mechanical   |
| `_check_single_active_phase` | `true`                | at most one backbone phase is `in_progress`         | mechanical   |
| `_check_file_exists`         | filename or `[names]` | each named file exists in `$MIGRATION_DIR/`         | mechanical   |
| `_validate_json`             | filename or `[names]` | each named file parses as valid JSON                | mechanical   |
| `_assert`                    | opaque prose          | the LLM judges the prose true against the artifact  | **judgment** |

`_assert` is where the whole postcondition contract can go soft: a `_validate_json`
has real teeth, but an `_assert` body is only checked for "is a non-empty string in
the right list" — CI never reads it. Use mechanical checks where you can; reserve
`_assert` for genuine judgment (per-entry field presence, enum-over-content,
conditionals CI can't evaluate).

### `_on_failure` / `_on_error` actions

Every check's `_on_failure` names one of these. Two STOP, two CONTINUE:

| Action              | Effect                                     | Phase status         |
| ------------------- | ------------------------------------------ | -------------------- |
| `_warn_and_skip`    | record a warning; skip this item; continue | remain `in_progress` |
| `_default_and_warn` | apply a documented default; warn; continue | remain `in_progress` |
| `_halt_and_inform`  | stop; surface a diagnostic                 | retain `in_progress` |
| `_unrecoverable`    | stop; surface an error                     | revert to `pending`  |

### `_exec._agent` — capability tiers

`_exec` runs a phase's work (its fragments + assembler) in an isolated sub-agent;
`_agent` names the tier that work runs at. Ordered, closed vocabulary (least → most
privileged):

| Tier  | Grants                                   | For                                          |
| ----- | ---------------------------------------- | -------------------------------------------- |
| `ro`  | read-only (Read / Grep / Glob / ro Bash) | analysis phases that produce NO artifact     |
| `rw`  | `ro` + Write / Edit                      | a phase that writes its `_produces`          |
| `git` | `rw` + git ops                           | a phase that mutates the user's repo history |

The author DECLARES the tier; CI verifies it is not below the minimum derivable from
what the phase produces (a producing phase can't be `ro`), that the tier's
`agents/generic-phase-worker-<tier>.md` worker is shipped, and that the phase
declares `_interactive: false` (a dispatched worker is file-only and cannot prompt
the user). The runtime ENFORCEMENT of the tier is platform-dependent — on a host
with no sub-agent allow-list it fails open (the phase runs at full access). See
`INTERPRETER.md` § `_exec`.

### `_re_entry_guard` sub-keys

Present on a backbone phase with a downstream; all four are required together.

| Sub-key               | Value (closed)                  | Meaning                                                                            |
| --------------------- | ------------------------------- | ---------------------------------------------------------------------------------- |
| `_stale_if_completed` | a phase name (= `_advances_to`) | the downstream phase whose completion makes re-running THIS phase unsafe           |
| `_stale_artifact`     | a filename                      | the downstream artifact named in the `GATE_FAIL` line (∈ that phase's `_produces`) |
| `_on_reentry`         | `stop_unless_confirmed`         | what to do on a stale re-entry (the only value today)                              |
| `_on_confirm`         | `reset_downstream_to_pending`   | what to do when the user confirms the re-run (the only value today)                |

### Conditional artifacts — `{ file, _when }`

`_produces` and `_contributes` (and `_knowledge`) accept, per entry, either a bare
filename or an inline `{ file: <path>, _when: <prose> }` map — the artifact is
produced only when the design predicate holds. `_when` is opaque (bound, not
evaluated). A trailing-slash `file` (e.g. `kubernetes/`) names a produced
**directory** — used when a unit emits a set of dynamically-named files with no fixed
name. CI checks only that a map entry carries a parseable, non-empty `file:`.

---

Next: [03-authoring-guide.md](03-authoring-guide.md) — build a phase end to end.
