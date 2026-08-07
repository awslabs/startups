# Validator checks

The full catalog of structural checks `mise run lint:frontmatter` enforces, drawn
from `tools/frontmatter-validator/check.ts`. Each entry: what it enforces, what trips
it, how to fix. The validator is **skill-agnostic** — every check is a property of
the phase/fragment/assembler grammar, not of any particular skill.

## What the validator does (and does not) guarantee

It parses every `references/phases/<name>/<name>.md` and its referenced
fragments/assemblers into the typed model (`types.ts`), then runs these checks.
**Green means the structure is sound**: closed vocabulary, resolved references, a
consistent phase chain, single-creator artifacts, honest `_produces`. It does **not**
evaluate `_when` conditions or `_assert` bodies — those are opaque prose bound and
transported verbatim, judged by the LLM at runtime. Structure has teeth; judgment
does not. That is by design.

## The partial-rollout tolerance model

The grammar was introduced phase-by-phase into a skill that started as plain prose,
so the validator is deliberately tolerant of a **partial rollout**: a phase file that
carries no frontmatter runs from its prose, as before, and is simply not bound. Many
checks therefore _self-skip when they can't be sure_:

- The valid phase set is **derived** from the phase files that declare frontmatter —
  never hardcoded. A reference to a phase that doesn't yet carry frontmatter is left
  **unverified** rather than failed.
- Membership checks (`_requires_phase`, `_check_phase_completed`,
  `_stale_if_completed`) only fire when **more than one** phase declares frontmatter
  AND the target isn't itself declared.
- The backbone chain-consistency block runs only once the whole backbone is
  frontmatter-present.

The one check that resolves against the **filesystem** rather than the declared set —
the dangling `_advances_to` edge — exists precisely so a truly-absent target still
fails even while the chain block self-skips. Understanding this tolerance explains why
a check you expected sometimes stays quiet on a half-migrated skill.

---

## Closed-vocabulary checks

**Enforces:** every `_`-key is in the closed set for its unit kind.
**Trips on:** a typo or an invented key — `unknown phase frontmatter key '_produce'`,
`unknown fragment frontmatter key '…'`, `unknown assembler frontmatter key '…'`,
`unknown _re_entry_guard sub-key '…'`.
**Fix:** use a real key (see [02-grammar-reference.md](02-grammar-reference.md)). A
typo fails the build rather than being silently ignored — that is the point.

## Backbone / checkpoint contract

**Enforces** (`INTERPRETER.md` § `_kind`):

- a **backbone** phase (default) MUST declare `_advances_to` and MUST NOT declare a
  phase-level `_trigger`;
- a **checkpoint** phase MUST declare a phase-level `_trigger` and MUST NOT declare
  `_advances_to`.

**Trips on:** `backbone phase '…' must declare _advances_to`; `backbone phase '…' must
NOT declare a phase-level _trigger`; `checkpoint phase '…' must declare a phase-level
_trigger`; `checkpoint phase '…' must NOT declare _advances_to`.
**Fix:** decide whether the phase is on the linear spine (backbone) or off it
(checkpoint) and give it the matching keys. Feedback is the canonical checkpoint.

## `_requires_phase` membership

**Enforces:** `_requires_phase` names a declared phase (when >1 phase has
frontmatter).
**Trips on:** `_requires_phase '…' names no declared phase`.
**Fix:** correct the phase name, or add frontmatter to the referenced phase.

## Fragment resolution + back-references

**Enforces:** each `_fragments[]._file` resolves on disk; the target has fragment
frontmatter; its `_fragment` id equals the phase's `_id`; its `_of_phase` equals the
phase.
**Trips on:** `fragment '…' _file does not resolve`; `referenced as a fragment … but
has no fragment frontmatter`; `_fragment id '…' != phase reference _id '…'`;
`_of_phase '…' != '…'`; `fragment '…' has an unrecognized _trigger form`.
**Fix:** correct the path, add the fragment frontmatter, or align the ids.

## Assembler: exactly one, resolves, back-references

**Enforces:** the phase declares `_assemble._file`; it resolves; the target has
assembler frontmatter; its `_of_phase` matches.
**Trips on:** `missing _assemble._file (a phase must have exactly one assembler)`;
`_assemble._file does not resolve`; `referenced as the assembler … but has no
assembler frontmatter`; `_of_phase '…' != '…'`.
**Fix:** every phase needs exactly one assembler, even a no-op validator one.

## Single-creator ownership

**Enforces:** each phase `_produces` artifact has exactly one creator. If the
assembler `_produces` it, the assembler is the creator (fragments may still
`_contributes` content to it). Otherwise exactly one fragment must `_contributes` it.
**Trips on:** `phase _produces '…' but no unit creates it … single-creator rule`
(zero creators); `phase _produces '…' is declared by multiple fragments (…) with no
assembler owner — ambiguous creator`.
**Fix:** either have the assembler `_produces` the artifact (making fragment
`_contributes` entries content-contributions), or ensure exactly one fragment claims
it.

## Re-entry guard checks

**Enforces** (`INTERPRETER.md` § `_re_entry_guard`), when a `_re_entry_guard` is
present:

- all four sub-keys present (`_stale_if_completed`, `_stale_artifact`, `_on_reentry`,
  `_on_confirm`);
- `_on_reentry` ∈ {`stop_unless_confirmed`}; `_on_confirm` ∈
  {`reset_downstream_to_pending`};
- the phase has a real downstream (not a terminal / not absent);
- `_stale_if_completed` equals this phase's `_advances_to`;
- `_stale_if_completed` names a declared phase;
- **(hard)** `_stale_artifact` is one of the downstream phase's `_produces`.

**Trips on:** `_re_entry_guard missing _stale_artifact`; `… _on_reentry '…' is not a
recognized value`; `phase '…' has a _re_entry_guard but no downstream backbone
phase`; `_stale_if_completed '…' should equal this phase's _advances_to '…'`;
`_stale_artifact '…' is not in the _produces of the downstream phase '…'`.
**Fix:** align the guard with the chain; make `_stale_artifact` the exact downstream
artifact whose staleness you're guarding against.

## `_exec` checks (execution mode / agent dispatch)

**Enforces** (`INTERPRETER.md` § `_exec`), when a phase declares `_exec`:

- every `_exec` sub-key is in the closed set (`_agent`);
- `_agent` is present and ∈ the closed tier set (`ro` / `rw` / `git`);
- **derived-minimum:** a phase that `_produces` ≥1 artifact does write work, so its
  `_agent` cannot be `ro` — the declared tier must be ≥ the minimum implied by what
  the phase produces (declare-but-verify).
- **non-interactive affirmation:** the phase MUST declare `_interactive: false`. A
  dispatched worker has file-only I/O and cannot prompt the user, so a phase with
  `_interactive: true` — or with no `_interactive` key — cannot carry `_exec`. This
  fires independently of the tier (even when `_agent` is missing or invalid).
- **worker-exists:** the tier's `agents/generic-phase-worker-<tier>.md` agent file
  must be shipped on disk — a phase cannot dispatch to a capability tier whose worker
  the plugin does not ship (it would fail at runtime). Skipped (UNVERIFIED) when the
  plugin `agents/` dir cannot be located, tolerant of a non-standard layout.

The **one-level rule** needs no dedicated check: `_exec` is a PHASE-only key, so a
fragment or assembler carrying it already trips the closed-vocabulary check
(`unknown fragment frontmatter key '_exec'`). Nested dispatch is structurally
unrepresentable.

**Trips on:** `unknown _exec sub-key '…'`; `_exec is present but declares no _agent
tier`; `_exec._agent '…' is not a recognized capability tier`; `_exec._agent 'ro'
(read-only) but phase '…' _produces N artifact(s) … needs at least 'rw'`; `phase '…'
declares _exec but no _interactive declaration / _interactive: true … MUST declare
'_interactive: false'`; `_exec._agent '…' has no worker on disk — expected agent file
'agents/generic-phase-worker-….md'`.
**Fix:** declare `_agent` as the LEAST tier that covers the phase's real work (a
phase that writes an artifact needs `rw`, or `git` if it mutates repo history); add
`_interactive: false` to affirm the work does not prompt the user; and ship the
tier's worker under `agents/`. Note the validator checks the tier is _well-formed,
not under-privileged, affirmed non-interactive, and backed by a shipped worker_ — it
does NOT verify the host actually enforces the tier (on inline-only hosts the tier
fails open; see the judgment-surface note below).

## Gate checks (`_preconditions` / `_postconditions`)

**Enforces:** every check `kind` is in the closed `CHECK_KINDS` set; every
`_on_failure` is in the closed `ON_ERROR_ACTIONS` set; a `_check_phase_completed` arg
names a declared phase.
**Trips on:** `unknown _postconditions check kind '…' (allowed: …)`; `… has an
unrecognized _on_failure action '…' (allowed: …)`; `_check_phase_completed '…' names
no declared phase`.
**Fix:** use a real check kind and a real action. Note `_assert` bodies are NOT
checked for truth — only that the entry is well-formed.

## Postcondition ⊆ `_produces` (hard fail)

**Enforces:** a `_postconditions._check_file_exists` may only name a file the phase
declares in `_produces` — a phase can only gate on artifacts it says it produces.
**Trips on:** `_postconditions asserts _check_file_exists '…' but it is not in this
phase's _produces (declared: …)`.
**Fix:** add the file to `_produces` (if the phase really produces it) or drop the
gate. This guards against a hollow `_produces` that omits real outputs.

## Dangling `_advances_to` edge

**Enforces:** `_advances_to` names either a terminal (`complete`/`done`/`end`) or a
phase that **exists on disk** (`references/phases/<name>/<name>.md`). Resolves against
the directory, not the declared set — so it still fires for a truly-absent target even
during partial rollout.
**Trips on:** `_advances_to '…' names neither a terminal … nor an existing phase …
dangling forward edge`.
**Fix:** correct the target, or create the phase directory/file.

## Backbone chain-consistency

**Enforces** (once >1 backbone phase is present and all forward edges resolve):

- **exactly one head** (a backbone phase with no `_requires_phase`);
- **exactly one terminal** (a backbone phase whose `_advances_to` is
  `complete`/`done`/`end`);
- **forward ⇒ back:** if A `_advances_to` B, then B `_requires_phase` A;
- **back ⇒ forward:** if B `_requires_phase` A, then A `_advances_to` B.

**Trips on:** `backbone must have exactly one head … found N`; `backbone must have
exactly one terminal … found N`; `chain inconsistency: '…' _advances_to '…', but '…'
_requires_phase '…'`.
**Fix:** make the two directional edges agree. A consistent chain with one head and
one terminal is necessarily a single acyclic line — which is what a migration
backbone is.

## `_init` uniqueness + backbone head

**Enforces** (`INTERPRETER.md` § interpreter loop / `_init`):

- at most one phase with `_init: true`;
- the `_init` phase is a **backbone** phase (not a checkpoint);
- the `_init` phase has no `_requires_phase` (it is the head);
- once the backbone is fully present, an `_init` phase MUST exist.

**Trips on:** `multiple phases declare '_init: true' (…)`; `checkpoint phase '…'
declares '_init: true'`; `entry phase '…' declares '_init: true' but also
'_requires_phase: …'`; `no phase declares '_init: true' — the backbone has no entry
phase`.
**Fix:** put `_init: true` on the single head phase and nowhere else. SKILL.md names
this phase so a cold start loads it directly.

## `_knowledge` + `_input` resolution

**Enforces:**

- every `_knowledge` `file` (on a phase or an assembler) resolves on disk, relative
  to the skill root;
- every `_input` entry is `workspace`, a glob, or an artifact some declared phase
  `_produces` (the produced-by check fires only when >1 phase has frontmatter).

**Trips on:** `_knowledge file does not resolve: …`; `_input '…' is not produced by
any declared phase`.
**Fix:** correct the path, or ensure the input artifact is declared in some phase's
`_produces`.

## Conditional-artifact well-formedness

**Enforces:** a conditional `_produces` / `_contributes` entry (the `{ file, _when }`
map form) carries a parseable, non-empty `file:`. CI does NOT evaluate `_when` (opaque
prose, same as `_knowledge._when`).
**Trips on:** `_produces has a conditional entry with no parseable 'file:' (expected
'{ file: <path>, _when: <prose> }')`.
**Fix:** write the map as `{ file: path/to/artifact, _when: "the predicate" }`.

---

## Where checks run out — the judgment surface

These are **not** bugs; they are the deliberate edge of "structure is checkable":

- **`_when` conditions** (triggers, knowledge guards, conditional artifacts) are
  bound but never evaluated. A misjudged `_when` fails **open** — it can silently
  skip a fragment or a data load. Put high-consequence branching behind mechanical
  triggers (`_glob`, `_always`) where you can.
- **`_assert` bodies** are checked only for "non-empty string in the right list". The
  entire judgment half of the postcondition contract rides on prose the validator
  never reads. Reserve `_assert` for genuine judgment; prefer the mechanical check
  kinds (`_check_file_exists`, `_validate_json`) wherever the property is mechanical.
- **`_exec._agent` tier enforcement** is the host harness's job, not the validator's.
  CI checks the tier is well-formed and not under-privileged for what the phase
  produces, but on a host with no sub-agent allow-list the tier is inert — the phase
  runs at full access and the restriction fails **open**. The tier records
  least-privilege _intent_; it is not a portable security boundary.

The value of the grammar is that it **isolates** these to named, greppable places —
so a reviewer knows exactly where the LLM's judgment is load-bearing.

---

Back to the [README](README.md) · the model in [01-concepts.md](01-concepts.md) · the
keys in [02-grammar-reference.md](02-grammar-reference.md) · building in
[03-authoring-guide.md](03-authoring-guide.md) · agent dispatch in
[05-exec-agent-dispatch.md](05-exec-agent-dispatch.md).
