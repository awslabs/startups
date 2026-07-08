# The Migration DSL — plugin documentation

This folder documents the **phase DSL** that the `migration-to-aws` skills are
built on: a declarative frontmatter grammar an LLM interprets at runtime to drive
a multi-phase migration, with a static validator (`mise run lint:frontmatter`) that
checks the structure before anything runs.

If you are about to author a new migration skill (or extend an existing one) and
you want your agent to understand the grammar, **point it at this directory.** The
docs are written to be read top-to-bottom by a human and loaded wholesale by an
agent.

## Why this exists

A migration ("move a Heroku app to AWS", "move a GCP project to AWS") is a long,
multi-step process: discover what exists, clarify intent, design the target,
estimate cost, generate artifacts, collect feedback. Two failure modes dominate
when you express that as a plain prose skill:

1. **Silent drift between phases.** A phase claims to produce an artifact the next
   phase needs, but the wiring is only in prose — nothing catches a rename, a typo,
   or a hollow "produces" list until a run fails halfway through.
2. **Orchestration prose the model half-follows.** Hardcoded phase-order tables,
   "set status to in_progress" recipes, and gate-rule restatements pile up in every
   phase file, drift out of sync with each other, and add load cost without adding
   behavior.

The DSL answers both by splitting each phase file into two layers:

- **Structure → frontmatter (checkable).** The phase's identity, ordering, inputs,
  outputs, gates, and data dependencies live in a closed-vocabulary YAML block. A
  zero-dependency validator parses every phase/fragment/assembler file and fails the
  build on a broken reference, an unknown key, a dangling phase edge, a hollow
  `_produces`, an ambiguous artifact creator, and more.
- **Judgment → prose (interpreted).** The actual work — how to parse Terraform, how
  to size a database, how to word a question — stays in markdown the LLM reads and
  executes. The grammar deliberately does **not** try to make judgment checkable.

The dividing line is the whole design: **structure is checkable; judgment is the
LLM's.** See [01-concepts.md](01-concepts.md) for the full rationale.

## What it is (and is NOT)

- It **is** a declarative grammar the LLM interprets. The markdown _is_ the program;
  the LLM _is_ the interpreter. There is **no engine and no server** — nothing
  executes the phase files except a language model reading them.
- It **is** statically validated. `mise run lint:frontmatter` runs a typed parser +
  structural checks over a skill's phase files. Green means the _structure_ is sound
  (closed vocab, resolved references, a consistent phase chain, single-creator
  artifacts). It does **not** mean the prose is correct — opaque conditions
  (`_when`) and judgment assertions (`_assert`) are bound but never evaluated by CI.
- It is **not** the MCP engine. A separate effort explores deterministic runtime
  tools (provision, dump/restore, verify). That is _execution_; this DSL is
  _planning_. Keep the two apart: the DSL plans a migration; it does not run one.

## Getting started

1. Read [01-concepts.md](01-concepts.md) — the mental model (10 min). Without it the
   grammar looks arbitrary.
2. Skim [02-grammar-reference.md](02-grammar-reference.md) — every frontmatter key,
   its shape, and a real example. This is the lookup you return to.
3. Follow [03-authoring-guide.md](03-authoring-guide.md) — build a phase (its
   orchestrator + a fragment + the assembler), wire it into the backbone, and get to
   a green `lint:frontmatter`.
4. Keep [04-validator-checks.md](04-validator-checks.md) open while authoring — when
   a check fails, it tells you what the check enforces and how to fix it.
5. Read [05-exec-agent-dispatch.md](05-exec-agent-dispatch.md) for how a phase can run
   its work in an isolated sub-agent (the `_exec` execution mode) — the mechanism,
   the generic worker, and the platform caveats.

## The canonical sources (what these docs answer to)

These docs are a _teaching layer_. The authorities they describe — and that win on
any disagreement — are all in the plugin:

| Source                                 | Role                                                                         |
| -------------------------------------- | ---------------------------------------------------------------------------- |
| `skills/shared/dsl/INTERPRETER.md`     | the **runtime semantics** — what the LLM does with each key (the spec)       |
| `tools/frontmatter-validator/types.ts` | the **shape** of every frontmatter key (the typed model the parser binds to) |
| `tools/frontmatter-validator/parse.ts` | the **closed vocabulary** (which keys/verbs/actions are legal)               |
| `tools/frontmatter-validator/check.ts` | the **structural checks** the build enforces                                 |
| `skills/heroku-to-aws/`                | the **living example** — a complete 6-phase skill authored to this grammar   |

If a doc here and one of those sources disagree, the source is right — please open a
fix to the doc.

## The living example

`skills/heroku-to-aws/` is a full migration skill built on this DSL: six phases
(discover → clarify → design → estimate → generate, plus an off-backbone feedback
checkpoint). Every construct in these docs is used there. When an explanation is
abstract, go read the corresponding phase file — the examples in these docs are
pulled from it verbatim.
