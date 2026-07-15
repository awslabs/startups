# Concepts — the mental model

Read this before the grammar reference. The keys make sense only once you hold the
model behind them.

## 1. The LLM is the interpreter. There is no engine.

At runtime the markdown files **are** the program and the language model **is** the
machine that runs them. Nothing parses a phase file and executes it except an LLM
reading it and following its instructions.

That single fact drives everything else:

- A phase file's frontmatter is not config for some runtime — it is a set of
  instructions the LLM reads and acts on, using the shared `INTERPRETER.md` as its
  operating manual.
- An opaque condition like `_when: "inventory has a heroku-postgresql addon"` is not
  code. The LLM reads it, looks at the inventory, and decides. No regex, no
  evaluator.
- Because the LLM behaves by **reading instructions**, anything a key does
  differently in different places must be written down in `INTERPRETER.md` — that is
  the only place per-context behavior can live. (This is why `INTERPRETER.md`
  explains `_when` several times: the four contexts genuinely differ.)

There is a separate, unrelated effort — the MCP engine — that builds deterministic
runtime tools (provision a database, dump/restore, verify). That is _execution_.
This DSL is _planning_: it produces a plan (inventory, design, cost estimate,
generated Terraform) that a human or an engine then acts on. Don't conflate the two.

## 2. Structure is checkable; judgment is the LLM's.

Every phase file has two layers, with a hard line between them.

**Structure** — identity, ordering, inputs, outputs, gates, data dependencies — is
declared in a **closed-vocabulary frontmatter block**. A typed validator
(`tools/frontmatter-validator/`) parses it and enforces structural rules the build
fails on. This is the layer with teeth.

**Judgment** — how to parse Terraform, how to size an RDS instance, how to word a
clarifying question — stays in **markdown prose** the LLM reads and executes. The
grammar deliberately does not try to check this. Two escape hatches carry judgment
_inside_ the structured layer, and both are bound-but-never-evaluated by CI:

- `_when: "<prose>"` — an opaque condition (a fragment trigger, a knowledge-load
  guard). The LLM decides if it holds.
- `_assert: "<prose>"` — an opaque postcondition ("every services[] entry has a
  service_id…"). The LLM evaluates it against the produced artifact.

**A green `lint:frontmatter` validates structure, never values.** It confirms the
wiring is sound — closed vocab, resolved references, a consistent phase chain,
single-creator artifacts. It says nothing about whether an `_assert` body is true or
a `_when` was judged correctly. That is the deal: you get static guarantees on the
skeleton, and you trust the model on the flesh. Knowing _where_ the judgment is (it
is isolated to `_when`/`_assert` prose) is itself the safety property — nothing else
invites interpretation.

## 3. Knowledge vs procedure vs contract — three homes, no inlining.

A unit's `.md` file is **procedure** (the algorithm). Two other kinds of content
must live elsewhere so they can change independently:

| Content       | Test — "would you change this for a reason unrelated to the algorithm?" | Home                       |
| ------------- | ----------------------------------------------------------------------- | -------------------------- |
| **Knowledge** | Yes — a lookup table, a tunable constant, a default                     | `knowledge/<skill>/*.json` |
| **Procedure** | No — it _is_ the branch/order/error-policy                              | the unit `.md` `## Step:`  |
| **Contract**  | It is the _shape_ of a produced artifact                                | `schemas/*.json`           |

The procedure **references** knowledge and schemas; it never re-lists them. A datum
lives in exactly one place — duplication is a drift surface and a validator concern.
(A fourth home, `templates/<phase>/`, holds output skeletons the generate phase
emits — HCL, docs, scripts.) The guardrail cuts both ways: extract _data_ and
_tunable constants_; never extract _logic_ or _contract_ (that would hollow the
procedure into "look up X in file Y" and it stops reading as an algorithm).

## 4. The three unit kinds.

A phase's work decomposes into **fragments** plus exactly one **assembler**. Three
kinds, three contracts:

| Kind          | Role                                    | Reads            | Writes                                    |
| ------------- | --------------------------------------- | ---------------- | ----------------------------------------- |
| **Phase**     | lifecycle + composition                 | —                | — (composes the units below)              |
| **Fragment**  | one unit of work, single responsibility | source inputs    | contributes to 1..N artifacts (to disk)   |
| **Assembler** | combine / enrich fragment contributions | fragment outputs | creates and/or mutates the phase artifact |

The rules that make this a real taxonomy (not just three file types):

- **Fragments are a flat, independent set.** A fragment never reads another
  fragment's output. If output B derives from output A, that coupling is a _signal
  they belong in the same fragment_ — not two fragments with a dependency edge.
  There is no fragment DAG, no ordering contract between fragments.
- **One responsibility per fragment.** A fragment may write several files, but only
  if they share one _reason to change_ (one source). Two sources → two fragments
  (heroku's `terraform` vs `billing` discovery). The test is "two reasons to change
  → two fragments", not "two files → two fragments".
- **Exactly one assembler per phase, and it is terminal.** Its job spans a spectrum:
  merge several fragment outputs into one file, enrich a fragment's file in place,
  derive new cross-cutting files, or — when fragments already wrote the artifact —
  just validate it. Even a no-op assembler earns its place: _its postconditions are
  the phase's artifact-level contract._
- **Single creator, last-writer owns.** Every artifact has exactly one creator (a
  fragment or the assembler) and zero-or-more mutators (the assembler only). Whoever
  writes a file last owns its final postconditions. The validator enforces this.

Why split at all? Because the three have genuinely different contracts, and
separating them keeps each file small and each responsibility checkable. A phase
orchestrator reads as "what runs when"; a fragment reads as "what I produce and must
satisfy"; the assembler reads as "the artifact's final shape".

## 5. The phase lifecycle — backbone, gates, and the handoff.

A migration is a linear chain of **backbone** phases, wired by two frontmatter keys:
`_advances_to` (forward) and `_requires_phase` (backward). The chain runs from the
**head** (the one phase with no `_requires_phase`, which also carries `_init: true`)
to the **terminal** (the one phase whose `_advances_to` is `complete`). The
interpreter _derives_ this chain from the frontmatter — it is never hardcoded in a
phase-order table.

Each phase runs behind two gates (see `INTERPRETER.md` § Gate protocol):

- **Entry gate (`_preconditions`).** Checked before any work: predecessor completed,
  single active phase, inputs present and valid. A failure stops the phase.
- **Completion gate (`_postconditions`).** Checked before the phase is marked
  `completed` and control advances: the artifact exists, is valid JSON, and satisfies
  the `_assert` judgments. On all-pass the LLM emits `HANDOFF_OK | phase=… |
  artifacts=…` and advances; on any failure it emits `GATE_FAIL`, stops, and does not
  patch the artifact to force a pass.

**Golden rule: never advance without `HANDOFF_OK`.** `_produces` is the phase's
return contract, `_postconditions` assert it, `HANDOFF_OK` is the return statement,
`_advances_to` is the tail call. A phase is a function; the gate is its boundary.

Two more lifecycle constructs:

- **Checkpoint phases** (`_kind: checkpoint`, e.g. feedback) are _off_ the backbone.
  They are entered by a phase-level `_trigger` (the user opts in), return control
  instead of advancing, and have no `_advances_to`. A resolved checkpoint is
  "completed" even if the user declined — participation is a separate signal (the
  artifact's presence).
- **Re-entry guard** (`_re_entry_guard`) protects against re-running a phase whose
  downstream already completed (which would leave the downstream artifact stale). It
  stops unless the user confirms, and on confirm resets the downstream phases to
  pending.

And one execution-mode construct, orthogonal to the lifecycle:

- **Agent dispatch** (`_exec`) lets a phase run its WORK (fragments + assembler) in a
  fresh isolated sub-agent window instead of inline — for heavy, self-contained,
  non-interactive phases (discovery is the case) whose bulky intermediate data would
  otherwise flood the main context. The interpreter keeps the gates, `_init` setup,
  and the state transition in the main window; only the artifact-producing work moves
  out. A dispatch candidate must affirm `_interactive: false` (a file-only worker
  cannot prompt the user — CI rejects `_exec` without it). It carries a capability
  tier (`_agent: ro|rw|git`) the validator floors against what the phase produces —
  but that tier is enforced only where the host harness has a real sub-agent
  allow-list, so it is a least-privilege _hint_, not a portable guarantee. Dispatch
  is one level deep (a fragment can't re-dispatch). See
  [05-exec-agent-dispatch.md](05-exec-agent-dispatch.md).

## 6. Derive, don't declare.

A recurring principle you will see enforced: when the validator needs a closed set to
check against, it **derives** it from the existing declarations rather than reading a
separate manifest. The set of valid phase names is `{ the _phase of every phase file
}` — there is no `phases:` list to keep in sync. A second source of truth is a drift
surface, and eliminating drift surfaces is the reason this grammar exists. When you
extend the grammar, resist the urge to add a manifest; derive the fact from what is
already declared.

---

Next: [02-grammar-reference.md](02-grammar-reference.md) — every key, its shape, and a
real example.
