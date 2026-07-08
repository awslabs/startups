# How agent dispatch works (`_exec`)

A deep-dive into the DSL's **agent-dispatch execution mode**: how a phase can run its
work in a fresh, isolated sub-agent instead of inline, why the design is shaped the
way it is, and what actually happens at runtime. This is the _explainer_ — for the
frontmatter keys see [02-grammar-reference.md](02-grammar-reference.md) (`_exec`,
`_interactive`), and for what CI enforces see
[04-validator-checks.md](04-validator-checks.md) (`_exec` checks). Read
[01-concepts.md](01-concepts.md) first for the base model.

> **Status: validated end-to-end on Claude Code (2026-07-08).** A live `heroku-to-aws`
> run dispatched the `discover` phase to a `generic-phase-worker-rw` sub-agent: the
> worker wrote `heroku-resource-inventory.json` into `$MIGRATION_DIR`, and the main
> window ran the completion gate and advanced state — exactly as the contract below
> describes. `discover` and `generate` are the current consumers.

## The problem it solves

The DSL's core premise is that **the LLM is the interpreter** (see
[01-concepts.md](01-concepts.md) §1): a migration runs in one language-model context
that reads each phase file and does the work. That is simple and it is why there is no
engine — but it has one structural cost.

Some phases do **heavy, self-contained work over bulky input**. Discovery is the
clearest case: it reads every `.tf` file, the `Procfile`, `app.json`, and any billing
CSVs, parses them, resolves conflicts, and boils all of it down to one small
`heroku-resource-inventory.json`. The _inputs_ are large and messy; the _output_ is
small and clean. When that runs inline, all of that raw intermediate data — hundreds
of lines of HCL, CSV rows, parse scratch — lands in the main context and stays there
for the rest of the migration, crowding out the phases that follow. The main window
pays a context tax for data it will never look at again.

The obvious fix is to run that work somewhere else and keep only the result. That is
exactly what `_exec` does: it lets a phase declare that its work should run in a
**fresh, isolated sub-agent window** whose entire product is the artifact file it
writes to disk. The bulky intermediate data lives and dies in that window; only the
small artifact crosses back.

## The design constraint that shaped it

We could have made "run this phase in an agent" an all-or-nothing move — hand the
whole phase, gates and state and all, to a sub-agent. We deliberately did **not**.

A migration is a state machine (`.phase-status.json`, the `HANDOFF_OK` handoff, the
`_advances_to` chain — see [01-concepts.md](01-concepts.md) §5). If a sub-agent owned
any of that, you would have **two controllers** racing over one state file, and the
interactive gates (resume-vs-fresh, clarifying questions) would be stranded inside a
non-interactive window. So the rule is:

> **Dispatch the WORK; keep the STATE MACHINE in the main window.**

`_exec` moves only a phase's fragments + assembler — the artifact-producing work. The
entry gate (`_preconditions`), `_init` state setup, the completion gate
(`_postconditions`), the `HANDOFF_OK`/`GATE_FAIL` decision, and the
`.phase-status.json` write **all stay in the main window**, exactly as for an inline
phase. One controller owns the lifecycle; the sub-agent is a pure, replaceable worker
that turns declared inputs into a declared artifact and reports back.

This is also why only **non-interactive** phases are dispatch candidates — the point
`_interactive` makes checkable (below).

## A property worth noticing: the prose body says nothing about execution mode

Whether a phase runs inline or dispatched is decided **entirely by its frontmatter**
(`_exec` present or absent). The Steps in the phase body are written once,
execution-mode agnostic — they describe the work the same way regardless. An author
toggles agent mode by adding or removing a few lines of frontmatter; they never edit
the procedure, and the dispatch semantics live in one place (`INTERPRETER.md`), not
copied into each phase. (The exact keys are in
[02-grammar-reference.md](02-grammar-reference.md).)

## How it works at runtime

When the interpreter (`INTERPRETER.md` § The interpreter loop) reaches a phase, step 5
branches on `_exec`:

1. **Entry gate — main window.** Run `_preconditions`. Dispatch only if it passes.
2. **`_init` setup — main window.** If the phase is the backbone head (`_init: true`),
   bootstrap migration state here first. The sub-agent is handed an already-initialized
   `$MIGRATION_DIR`; it never creates state.
3. **Dispatch the work.** Invoke the tier's generic worker (below) with a context
   block that names the phase to run, the skill root, and `$MIGRATION_DIR`. The worker
   loads the phase file, runs its fragments (each when its `_trigger` fires) then its
   assembler, writes the `_produces` artifact(s) to `$MIGRATION_DIR`, and returns a
   one-line status. Its I/O is **file-only** — it returns nothing but its written
   artifacts.
4. **Completion gate — main window.** Re-read the artifact(s) from disk (**never trust
   the worker's summary**), run `_postconditions`, then emit `HANDOFF_OK` or
   `GATE_FAIL` and write the state transition — identical to an inline phase.

The worker reports one of:

- `WORKER_DONE | phase=<phase> | artifacts=<paths>` → proceed to the completion gate.
- `WORKER_BLOCKED | phase=<phase> | reason=<...>` → do not advance; the completion gate
  fails on the missing/partial artifact and the user is told which phase to re-run.

`$MIGRATION_DIR` is the **only** channel between the main window and the worker. The
worker shares no context, no variables, no memory with the controller — it receives
its inputs as file paths on disk and returns its output as files on disk. That single
shared directory is what lets the controller keep the state machine while the work
runs in genuine isolation.

### The generic tiered worker

The dispatched agent is **generic and phase-agnostic**. There is not one agent per
phase; there is one worker shell per capability tier, and the _phase to run_ is passed
in at dispatch time. The only thing baked into a worker is its tool allow-list — the
tier. The plugin ships these under `agents/`, and the tier maps to the worker name:

| `_agent` | Worker                                      | Allow-list                    |
| -------- | ------------------------------------------- | ----------------------------- |
| `ro`     | `migration-to-aws:generic-phase-worker-ro`  | Read, Grep, Glob              |
| `rw`     | `migration-to-aws:generic-phase-worker-rw`  | Read, Grep, Glob, Write, Edit |
| `git`    | `migration-to-aws:generic-phase-worker-git` | rw + git                      |

Only the workers a skill actually needs are shipped. Today only
`generic-phase-worker-rw` exists — the one `discover` and `generate` need. A phase may
only name a tier whose worker file is present (CI enforces this — see
[04-validator-checks.md](04-validator-checks.md)), so a phase can never dispatch to a
worker the plugin doesn't ship.

Keeping the worker generic is the point: the same `rw` shell serves `discover`,
`generate`, and any future `rw` phase, with no new agent file — the phase identity is a
runtime parameter, not a compile-time one. The worker parses a labeled context block:

```text
Skill: <skill name, e.g. heroku-to-aws>
Skill root: <absolute path to the skill directory>
Phase: <the _phase id, e.g. discover>
Phase file: <path, relative to Skill root, of the phase orchestrator>
Migration dir: <absolute $MIGRATION_DIR>
Input artifacts (Read these): <comma-joined upstream artifact paths — omit if none>
```

Upstream artifacts are passed as **file paths**, never inlined — the worker reads them
from disk. It runs only the phase's WORK, explicitly skipping the `_init` / gate /
handoff scaffolding that stays in the main window.

### Why the worker does not touch state

The worker MUST NOT write `.phase-status.json`, emit `HANDOFF_OK`, or run the gates.
Every completion decision is earned by the main window's completion gate, which
re-reads the produced artifacts from disk and verifies them independently — it does
not trust the worker's `WORKER_DONE` line. This is what keeps the "one controller owns
the state machine" guarantee true: a broken or dishonest worker run cannot leave the
state file claiming progress it didn't make, because only the gate advances state.

### Why `rw` has no shell

`generic-phase-worker-rw`'s allow-list is `Read, Grep, Glob, Write, Edit` — with **no
Bash**. That is deliberate. Bash can shell out to `git`, which would silently collapse
the `rw`/`git` tier distinction (an `rw` worker with Bash could commit to the repo).
Withholding Bash keeps the `rw` tier genuinely unable to touch repo history, so the
lattice means what it says. Discovery and generation are pure file work, so the native
Read/Grep/Glob/Write/Edit tools cover them with room to spare.

## Why a phase must affirm it is non-interactive

`_exec` dispatches a phase's work to a **file-only, non-interactive** worker — it never
prompts the user. So a phase can only be dispatched if its work genuinely needs no user
interaction, and the author must **affirm** that with `_interactive: false`. A phase
with `_interactive: true`, or with no `_interactive` key at all, cannot be dispatched
(CI rejects it — see [04-validator-checks.md](04-validator-checks.md)).

This is a deliberate fail-safe: forgetting to think about interactivity leaves the
phase inline, never silently dispatched into a worker that would hang waiting on a
prompt it can't issue. The interactive phases whose whole purpose is questioning the
user (`clarify`, `feedback`) therefore stay inline, always — and the grammar makes that
a checkable property rather than a convention.

## The tier is a scoping HINT, not a portable guarantee

The capability tier is only _enforced_ where the host harness has a real sub-agent
allow-list. On **Claude Code**, the worker's `tools:` frontmatter is a genuine
restriction — a `generic-phase-worker-rw` literally cannot invoke a tool outside its
allow-list. On a host with **no sub-agent mechanism** (inline-only platforms such as
Codex or Cursor), there is nothing to dispatch to: the phase runs inline in the main
session at full access, and the tier is **inert — it fails open**.

Two consequences follow, both by design:

1. **`_exec` never fails.** On a host without dispatch, the interpreter runs the
   phase's fragments + assembler inline, exactly like a non-`_exec` phase. Behavior is
   identical; only the context isolation is lost (the very cost `_exec` was meant to
   avoid). A skill authored with `_exec` still runs correctly everywhere.
2. **Do not treat the tier as a security boundary.** `_exec._agent` records a
   least-privilege _intent_ the harness honors when it can. Never put a safety-critical
   permission restriction behind a tier and assume it holds everywhere. This is the
   same fail-open discipline as `_when` and `_assert`: structure records the intent;
   enforcement is the interpreter's or the harness's job.

## Terminal phases: a note on the context win

`discover` is mid-chain — isolating it keeps the main window lean for every phase that
follows, so the benefit compounds. `generate` is **terminal** (`_advances_to:
complete`): nothing runs after it, so dispatching it does not protect any downstream
phase. Its win is narrower — it isolates the (large) generation reasoning and template
scratch so that never crowds the run's tail. Note too that `generate`'s completion gate
inspects artifact _content_ (e.g. "no `{{VARIABLE}}` placeholder tokens remain in the
`.tf` files"), so the main window re-reads the generated files at the gate regardless.
`_exec` removes the generation _reasoning_ from the main window, not the artifact
_bytes_ — which the gate must see either way. It is still a net win (and never worse
than inline), just a smaller and different one than the raw output size suggests.

## Files this touches

| File                                               | What it holds                                                    |
| -------------------------------------------------- | ---------------------------------------------------------------- |
| `skills/shared/dsl/INTERPRETER.md` § `_exec`       | the runtime dispatch contract (the authority)                    |
| `tools/frontmatter-validator/types.ts`, `check.ts` | the typed model, closed vocab, and structural checks             |
| `agents/generic-phase-worker-rw.md`                | the generic `rw` worker shell (phase passed at dispatch)         |
| `skills/heroku-to-aws/.../discover/discover.md`    | first consumer — `_exec: { _agent: rw }` + `_interactive: false` |
| `skills/heroku-to-aws/.../generate/generate.md`    | second consumer — same shape (terminal phase)                    |

---

Back to the [README](README.md) · the model in [01-concepts.md](01-concepts.md) · the
keys in [02-grammar-reference.md](02-grammar-reference.md) · the checks in
[04-validator-checks.md](04-validator-checks.md).
