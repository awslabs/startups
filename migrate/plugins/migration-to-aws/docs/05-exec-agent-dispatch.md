# Agent-dispatch execution mode (`_exec`)

How a phase can run its work in a fresh, isolated sub-agent instead of inline — and
why the grammar was extended to allow it. Read [01-concepts.md](01-concepts.md) for
the base model first; this doc assumes you know what a phase, fragment, and assembler
are.

> **Status: proof of concept.** The grammar, validator, and interpreter contract are
> complete and tested; `heroku-to-aws`'s discover phase is the first (and, today,
> only) consumer. The runtime dispatch has been wired but not yet exercised
> end-to-end in a live host. Treat the runtime behavior as unproven until a real run
> confirms it.

## The problem it solves

The DSL's core premise is that **the LLM is the interpreter** (see
[01-concepts.md](01-concepts.md) §1): a migration runs in one language-model context
that reads each phase file and does the work. That is simple and it is why there is
no engine — but it has one structural cost.

Some phases do **heavy, self-contained work over bulky input**. Discovery is the
clearest case: it reads every `.tf` file, the `Procfile`, `app.json`, and any billing
CSVs, parses them, resolves conflicts, and boils all of it down to one small
`heroku-resource-inventory.json`. The _inputs_ are large and messy; the _output_ is
small and clean. When that runs inline, all of that raw intermediate data — hundreds
of lines of HCL, CSV rows, parse scratch — lands in the main context and stays there
for the rest of the migration, crowding out the design, estimate, and generate phases
that follow. The main window pays a context tax for data it will never look at again.

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

This is also why only **non-interactive** phases are dispatch candidates. If a phase
needs to ask the user something, that question belongs to the main-window controller,
not the isolated worker.

## The grammar — one key, one toggle

The entire author-facing surface is a single phase-level frontmatter key:

```yaml
_exec:
  _agent: rw # capability tier: ro | rw | git
```

- **Absent** → the phase runs inline in the main window, exactly as before. This is
  the default and nothing changes.
- **Present** → the phase's fragments + assembler are dispatched to an isolated
  sub-agent at the named capability tier.

A deliberate property: **the phase's prose body says nothing about execution mode.**
Whether discover runs inline or dispatched is decided entirely by the presence of
`_exec` in the frontmatter — the Steps in the body are written once, execution-mode
agnostic, and describe the work the same way regardless. An author toggles agent mode
by adding or removing four lines of frontmatter; they never edit the procedure. The
dispatch semantics live in one place — `INTERPRETER.md` — not copied into each phase.

### `_agent` — capability tiers

`_agent` names the capability tier the dispatched work runs at. It is an ordered,
closed vocabulary (least → most privileged):

| Tier  | Grants                         | For                                          |
| ----- | ------------------------------ | -------------------------------------------- |
| `ro`  | read-only (Read / Grep / Glob) | analysis phases that produce NO artifact     |
| `rw`  | `ro` + Write / Edit            | a phase that writes its `_produces` artifact |
| `git` | `rw` + git operations          | a phase that mutates the user's repo history |

Pick the **least** tier that covers the phase's real work. The validator enforces a
**derived minimum**: a phase that `_produces` any artifact does write work, so
declaring `ro` on a producing phase is a build error — you cannot claim to produce a
file you have no permission to write. The author declares the tier; CI verifies it is
not below the minimum implied by what the phase produces. This is the same
declare-but-verify pattern the rest of the grammar uses.

## How it works at runtime

When the interpreter (`INTERPRETER.md` § The interpreter loop) reaches a phase, step
5 branches on `_exec`:

1. **Entry gate — main window.** Run `_preconditions`. Dispatch only if it passes.
2. **`_init` setup — main window.** If the phase is the backbone head (`_init:
   true`), bootstrap migration state here first. The sub-agent is handed an
   already-initialized `$MIGRATION_DIR`; it never creates state.
3. **Dispatch the work.** Invoke the tier's generic worker (below) with a context
   block that names the phase to run, the skill root, and `$MIGRATION_DIR`. The
   worker loads the phase file, runs its fragments (each when its `_trigger` fires)
   then its assembler, writes the `_produces` artifact(s) to `$MIGRATION_DIR`, and
   returns a one-line status. Its I/O is **file-only** — it returns nothing but its
   written artifacts.
4. **Completion gate — main window.** Re-read the artifact(s) from disk (never trust
   the worker's summary), run `_postconditions`, then emit `HANDOFF_OK` or
   `GATE_FAIL` and write the state transition — identical to an inline phase.

The worker reports one of:

- `WORKER_DONE | phase=<phase> | artifacts=<paths>` → proceed to the completion gate.
- `WORKER_BLOCKED | phase=<phase> | reason=<...>` → do not advance; the completion
  gate fails on the missing/partial artifact and the user is told which phase to
  re-run.

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
`generic-phase-worker-rw` exists — the one discover needs. A tier with no worker file
on disk simply means no phase uses it yet.

Keeping the worker generic is the point: the same `rw` shell serves discover today,
and any future `rw` phase tomorrow, with no new agent file — the phase identity is a
runtime parameter, not a compile-time one. The worker parses a labeled context block:

```
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

### Why `rw` has no shell

`generic-phase-worker-rw`'s allow-list is `Read, Grep, Glob, Write, Edit` — with **no
Bash**. That is deliberate. Bash can shell out to `git`, which would silently collapse
the `rw`/`git` tier distinction (an `rw` worker with Bash could commit to the repo).
Withholding Bash keeps the `rw` tier genuinely unable to touch repo history, so the
lattice means what it says. Discovery is pure file parsing, so the native
Read/Grep/Glob/Write/Edit tools cover it with room to spare.

## What the validator checks (and does not)

`mise run lint:frontmatter` enforces the structure of `_exec` (see
[04-validator-checks.md](04-validator-checks.md) for the full catalog):

- `_exec` sub-keys are in the closed set (`_agent`);
- `_agent` is present and ∈ `{ro, rw, git}`;
- **derived minimum:** a producing phase cannot be `ro`;
- the **one-level rule** falls out for free — `_exec` is a _phase-only_ key, so a
  fragment or assembler carrying it trips the closed-vocabulary check. Nested
  dispatch (a worker spawning a worker) is structurally unrepresentable.

What it does **not** check: whether the host actually enforces the tier. That is the
next section, and it is the most important caveat.

## The platform-asymmetry caveat — the tier is a hint, not a guarantee

The capability tier is only _enforced_ where the host harness has a real sub-agent
allow-list. On **Claude Code**, the worker's `tools:` frontmatter is a genuine
restriction — a `generic-phase-worker-rw` literally cannot invoke a tool outside its
allow-list. On a host with **no sub-agent mechanism** (inline-only platforms such as
Codex or Cursor), there is nothing to dispatch to: the phase runs inline in the main
session at full access, and the tier is **inert — it fails open**.

Two consequences follow, and both are by design:

1. **`_exec` never fails.** On a host without dispatch, the interpreter runs the
   phase's fragments + assembler inline, exactly like a non-`_exec` phase. Behavior is
   identical; only the context isolation is lost (which is the very cost `_exec` was
   meant to avoid). A skill authored with `_exec` still runs correctly everywhere.
2. **Do not treat the tier as a security boundary.** `_exec._agent` records a
   least-privilege _intent_ the harness honors when it can. Never put a
   safety-critical permission restriction behind a tier and assume it holds
   everywhere. This is the same fail-open discipline as `_when` and `_assert`:
   structure records the intent; enforcement is the interpreter's or the harness's
   job (see [04-validator-checks.md](04-validator-checks.md) § the judgment surface).

## Files this touches

| File                                               | What it holds                                                   |
| -------------------------------------------------- | --------------------------------------------------------------- |
| `skills/shared/dsl/INTERPRETER.md` § `_exec`       | the runtime dispatch contract (the authority)                   |
| `tools/frontmatter-validator/types.ts`, `check.ts` | the typed model, closed vocab, and structural checks            |
| `agents/generic-phase-worker-rw.md`                | the generic `rw` worker shell (phase passed at dispatch)        |
| `skills/heroku-to-aws/.../discover/discover.md`    | the first consumer — `_exec: { _agent: rw }` in its frontmatter |

---

Back to the [README](README.md) · the model in [01-concepts.md](01-concepts.md) · the
keys in [02-grammar-reference.md](02-grammar-reference.md) · the checks in
[04-validator-checks.md](04-validator-checks.md).
