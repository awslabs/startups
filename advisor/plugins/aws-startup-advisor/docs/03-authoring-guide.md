# Authoring guide

How to build a migration skill on the DSL, or add/extend a phase in one. Assumes
you've read [01-concepts.md](01-concepts.md) and have
[02-grammar-reference.md](02-grammar-reference.md) open for lookups.

The running example is a fictional `render-to-aws` skill, but every pattern is drawn
from the real `skills/heroku-to-aws/`. When in doubt, read the corresponding file
there — it is the reference implementation.

## The skill layout

A DSL skill lives under `skills/<name>/` with this shape:

```
skills/<name>/
├── SKILL.md                        ← entry point; names the cold-start entry phase
├── references/
│   ├── phases/
│   │   └── <phase>/
│   │       ├── <phase>.md           ← the phase ORCHESTRATOR (phase frontmatter)
│   │       ├── <phase>-<work>.md    ← a FRAGMENT (fragment frontmatter)
│   │       └── <phase>-assemble.md  ← the ASSEMBLER (assembler frontmatter)
│   └── schemas/                     ← *.json output contracts
├── knowledge/<name>/                ← *.json lookup data (referenced by _knowledge)
└── templates/<phase>/               ← output skeletons the generate phase emits
```

The validator discovers phases by scanning `references/phases/<name>/<name>.md` — the
orchestrator file **must** be named after its directory.

## Step 1 — decide the backbone

List your phases in order and pick, for each, what it consumes and produces. The
chain is wired by two keys that must agree in both directions:

- each phase's `_advances_to` = the next phase (last phase → `complete`)
- each phase's `_requires_phase` = the previous phase (first phase → omit it)

The **head** phase (no `_requires_phase`) also carries `_init: true` — it bootstraps
migration state on a cold start. Exactly one phase per skill has each of: `_init:
true`, no `_requires_phase`, and `_advances_to: complete`. Anything off this linear
spine (an optional feedback survey) is a **checkpoint**, not a backbone phase.

Sketch for `render-to-aws`:

```
discover (_init) → clarify → design → generate → complete
                                    ↖ feedback (checkpoint, off-backbone)
```

## Step 2 — write the phase orchestrator

Create `references/phases/discover/discover.md`. The frontmatter declares the
contract; the prose delegates to the units.

```yaml
---
_phase: discover
_title: "Discover Render Resources"
_init: true
_input: workspace
_fragments:
  - _id: services
    _trigger: { _always: true }
    _file: phases/discover/discover-services.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - render-resource-inventory.json
_advances_to: clarify
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: render-resource-inventory.json
    _on_failure: _halt_and_inform
  - _validate_json: render-resource-inventory.json
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - "*.txt"
  - "terraform/**"
---

# Phase 1: Discover Render Resources

Lightweight orchestrator that delegates to the discovery fragment(s), then the
assembler. Execute steps in order.

## Step 1: Run discovery
Load `references/phases/discover/discover-services.md` and follow it.

## Step 2: Assemble
Load `references/phases/discover/discover-assemble.md` and follow it.

## Scope Boundary
This phase inventories Render resources ONLY — no AWS mapping, cost, or Terraform.
```

Notes:

- The orchestrator body is thin — it points at units. Do NOT restate gate rules,
  phase-order tables, or "set status to in_progress" recipes; the interpreter owns
  all of that (`INTERPRETER.md`). Restating them is duplication and a drift surface.
- `_input: workspace` means "the initial file scan" (only valid on the `_init`
  phase). Downstream phases list upstream artifacts by name instead.
- A `_postconditions._check_file_exists` may only name a file in this phase's
  `_produces` — CI hard-fails otherwise (it forces `_produces` to be honest).

## Step 3 — write the fragment(s)

Create `references/phases/discover/discover-services.md`. This is where the real work
lives — the deterministic how-to, worked examples, parsing rules.

```yaml
---
_fragment: services
_of_phase: discover
_contributes:
  - render-resource-inventory.json
---

# Discover: Render services

## Step: scan
Glob for `render.yaml`; for each service block, extract name, type, plan, env.
[…the actual extraction rules + a worked example…]
```

Rules the validator enforces:

- `_fragment` **must equal** the `_id` the phase's `_fragments` list used
  (`services`). `_of_phase` **must equal** the owning phase's `_phase` (`discover`).
- Split by **reason to change**: one source per fragment. Two independent sources
  (say `render.yaml` vs a billing CSV) → two fragments, never one fragment with a
  dependency on another. A fragment never reads another fragment's output.

## Step 4 — write the assembler

Create `references/phases/discover/discover-assemble.md`. Every phase has exactly
one, and it is terminal.

```yaml
---
_assemble: assemble-inventory
_of_phase: discover
_reads:
  - services (fragment contribution)
_produces:
  - render-resource-inventory.json
---

# Discover: assemble inventory

## Step: combine
Merge the fragment contributions into render-resource-inventory.json.
[…assembly rules; the artifact's field definitions / schema reference…]
```

The assembler owns the **artifact-level contract**. Even a no-op assembler (fragments
already wrote the file) earns its place: its postconditions are the phase's contract.

**Single-creator rule.** Each `_produces` artifact needs exactly one creator:

- If the **assembler** `_produces` it → the assembler is the creator; fragments that
  also name it in `_contributes` are content-contributors (fine).
- Otherwise **exactly one fragment** must `_contributes` it. Zero → "no unit creates
  it". Two+ fragments with no assembler owner → "ambiguous creator". Both fail CI.

## Step 5 — knowledge, schemas, templates

Don't inline data or artifact shapes in prose:

- **Lookup tables / tunable constants** → `knowledge/<skill>/*.json`, referenced from
  the phase's `_knowledge` with an optional `_when` guard. Load only when the guard
  holds; don't speculatively load a table for a resource type absent from the input.
- **Artifact shape** → `schemas/*.json`; the assembler references it (a
  `_validate_json` / `_assert`), it does not re-list fields in prose.
- **Output skeletons** (generate phase) → `templates/<phase>/`, referenced not
  inlined.

Every `_knowledge` file must resolve on disk, or CI fails.

## Step 6 — wire checkpoints (optional)

An off-backbone phase (a feedback survey) is a checkpoint: `_kind: checkpoint`, a
phase-level `_trigger` (how it's entered), and NO `_advances_to`. It returns control
instead of advancing. Where it's offered is orchestration prose in SKILL.md, not part
of the phase contract. See `skills/heroku-to-aws/references/phases/feedback/`.

## Step 7 — the re-entry guard (optional)

If re-running a phase would leave a downstream artifact stale, add a
`_re_entry_guard`. All four sub-keys are required, and two must agree with the chain:
`_stale_if_completed` must equal this phase's `_advances_to`, and `_stale_artifact`
must be one of that downstream phase's `_produces`. See `design.md` for a live one.

## Step 8 — run a phase in a sub-agent (optional)

If a phase does heavy, self-contained work over bulky input (parsing, generation) and
asks the user nothing, you can dispatch its WORK to a fresh isolated sub-agent so the
intermediate data never floods the main context. Two frontmatter keys, both on the
phase:

```yaml
_interactive: false # affirm the work does not prompt the user (REQUIRED to dispatch)
_exec:
  _agent: rw # capability tier: ro | rw | git
```

Pick the LEAST tier that covers the work (`rw` for a phase that writes artifacts). You
do not touch the phase's prose body, gates, `_input`, or `_produces` — `_exec` changes
only _where_ the work runs, never the contract. The interpreter keeps the gates,
`_init`, and the state transition in the main window; only the fragments + assembler
move to the worker. `discover` and `generate` are the live examples. See
[05-exec-agent-dispatch.md](05-exec-agent-dispatch.md) for the full mechanism and
caveats.

## Step 9 — validate

Run the typed validator against your skill root:

```bash
mise run lint:frontmatter
```

(The shipped task points at `skills/heroku-to-aws`; to check another skill, run the
validator directly: `node tools/frontmatter-validator/validate.ts skills/<name>`.)

It discovers your phases, binds the frontmatter, and reports findings — exit non-zero
on any. See [04-validator-checks.md](04-validator-checks.md) for what each finding
means. Then run the full build before pushing:

```bash
mise run build
```

`build` runs `lint:md` (markdownlint), `lint:types` (tsc on the validator),
`lint:frontmatter`, `fmt:check` (dprint), and the security scanners.

## Common mistakes (and the check that catches each)

| Mistake                                                          | Finding                                                                                |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Typo'd a key (`_produce:`)                                       | `unknown … frontmatter key '_produce'`                                                 |
| Fragment `_fragment`/`_of_phase` doesn't match the phase's ref   | `_fragment id '…' != phase reference _id '…'`                                          |
| Forgot the assembler                                             | `missing _assemble._file`                                                              |
| `_produces` an artifact no unit creates                          | `no unit creates it — single-creator rule`                                             |
| Two fragments `_contributes` the same file, no assembler owner   | `ambiguous creator (single-creator rule)`                                              |
| `_postconditions` gates a file not in `_produces`                | `not in this phase's _produces`                                                        |
| `_advances_to` names a phase dir that doesn't exist              | `dangling forward edge`                                                                |
| `_advances_to`/`_requires_phase` disagree between two phases     | `chain inconsistency`                                                                  |
| Backbone phase missing `_advances_to`, or has a phase `_trigger` | `backbone phase must declare _advances_to` / `must NOT declare a phase-level _trigger` |
| Two phases with `_init: true`, or none once the backbone is full | `multiple phases declare '_init: true'` / `no phase declares '_init: true'`            |
| `_knowledge` file path is wrong                                  | `_knowledge file does not resolve`                                                     |

### The markdownlint gotcha (MD031)

`dprint fmt:check` does NOT flag a fenced code block nested inside a bullet list, but
`markdownlint` MD031 (blanks-around-fences) DOES — so `fmt:check` can pass locally
while CI's `lint:md` fails. Always run the full `mise run build` (or at least `mise
run lint:md`) before pushing prose that nests code fences in bullets. Fix: pull the
fence out to a top-level block with blank lines around it.

---

Next: [04-validator-checks.md](04-validator-checks.md) — the full check catalog.
