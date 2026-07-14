# Contributing to migration-to-aws

This guide is for **contributors** to the `migration-to-aws` plugin — how the plugin
is structured, how to build and validate a change, and which architecture to follow
for new work. For what the plugin does and how to install it, see the
[README](README.md).

## Architecture: two skills, two generations

The plugin ships two migration skills that are built on **different architectures**:

| Skill             | Architecture                          | Status                     |
| ----------------- | ------------------------------------- | -------------------------- |
| **heroku-to-aws** | the **phase DSL** (checkable grammar) | current direction          |
| **gcp-to-aws**    | the **older prose design**            | maintained, not yet ported |

**`heroku-to-aws` is the reference implementation of the phase DSL** — a declarative
frontmatter grammar an LLM interprets at runtime, with a static validator that checks
the structure before anything runs. Each phase file splits into two layers: _structure_
(identity, ordering, inputs, outputs, gates, data deps) lives in a closed-vocabulary
YAML frontmatter block the validator enforces; _judgment_ (how to parse Terraform, how
to size a database) stays in prose the LLM executes. The dividing line is the whole
design: **structure is checkable; judgment is the LLM's.**

**`gcp-to-aws` predates the DSL** and expresses its phases as prose with hand-written
orchestration (phase-order tables, "set status to in_progress" recipes, gate rules
restated per phase). It works and is maintained, but it carries the failure modes the
DSL was built to remove — silent drift between phases and orchestration prose the model
half-follows.

### Future direction — new work uses the DSL

**The intended direction for this plugin is the DSL.** When you author a new migration
skill, or add a phase to an existing one, follow the `heroku-to-aws` DSL pattern, not
the `gcp-to-aws` prose pattern. New skills should be DSL-native from the start; a future
effort will port `gcp-to-aws` onto the DSL. Do not add new prose-orchestration skills.

If you are extending `gcp-to-aws` specifically (a bug fix, a service mapping), match its
existing prose style for consistency within that skill — but net-new skills go DSL.

## The DSL — where to learn it

The grammar is fully documented under [`docs/`](docs/). Point your agent at that
directory and read it top-to-bottom:

- [docs/README.md](docs/README.md) — the index and the canonical sources.
- [docs/01-concepts.md](docs/01-concepts.md) — the mental model (read first).
- [docs/02-grammar-reference.md](docs/02-grammar-reference.md) — every frontmatter key.
- [docs/03-authoring-guide.md](docs/03-authoring-guide.md) — build a phase end-to-end.
- [docs/04-validator-checks.md](docs/04-validator-checks.md) — what CI enforces + fixes.
- [docs/05-exec-agent-dispatch.md](docs/05-exec-agent-dispatch.md) — running a phase in
  an isolated sub-agent (the `_exec` execution mode).

The **authorities** these docs describe (and that win on any disagreement) are in the
plugin: `skills/shared/dsl/INTERPRETER.md` (runtime semantics), the
`tools/frontmatter-validator/` (`types.ts`/`parse.ts`/`check.ts` — shape, closed vocab,
structural checks), and `skills/heroku-to-aws/` (the living example).

## Build and validate

This project uses [mise](https://mise.jdx.dev) for tool management and tasks. Run tasks
from the **repo root** (`mise.toml` lives there; `mise` walks up to find it).

```bash
mise install            # install pinned tools (Node 24, dprint, markdownlint, ...)
mise run build          # the full gate: lint + fmt:check + security
```

`build` is the complete pre-push gate. Its pieces (all runnable individually):

| Task                        | What it checks                                                    |
| --------------------------- | ----------------------------------------------------------------- |
| `mise run lint:md`          | markdownlint over all `.md`                                       |
| `mise run lint:types`       | `tsc --noEmit` (strict) on the frontmatter validator + its test   |
| `mise run lint:frontmatter` | the typed DSL validator over `skills/heroku-to-aws` phase files   |
| `mise run shared:check`     | vendored shared files are byte-identical to canonical (see below) |
| `mise run test`             | the frontmatter-validator test suite (`node --test`)              |
| `mise run fmt:check`        | dprint formatting (run `mise run fmt` to fix)                     |
| `mise run security`         | bandit, semgrep, gitleaks, checkov, grype                         |

The DSL validator is skill-agnostic. To validate a skill other than the default:

```bash
node migrate/plugins/migration-to-aws/tools/frontmatter-validator/validate.ts \
  migrate/plugins/migration-to-aws/skills/<skill-name>
```

## The vendored shared-files contract

Some files are **runtime dependencies shared across skills** — most importantly the DSL
runtime contract `INTERPRETER.md`, plus the estimate schemas and the pricing/complexity
data. Their canonical home is `skills/shared/`. Because these are load-bearing at
runtime (INTERPRETER.md _is_ the program the LLM interprets), a skill that referenced
them via an external `../shared/` climb would **not be self-contained** — lift the skill
folder out on its own and the reference dangles.

So each skill **vendors** byte-identical copies under its own `references/vendored/`,
and CI enforces they stay in sync with the canonical source:

- **Edit the canonical file only** — `skills/shared/<...>`. Never hand-edit a
  `references/vendored/` copy (a banner + the check will tell you; `shared:sync`
  overwrites vendored copies from canonical and would discard an edit made there).
- After editing canonical, re-sync: `mise run shared:sync` (copies canonical → every
  skill's `references/vendored/`), then commit the updated copies.
- `mise run shared:check` (wired into `build`) fails if any vendored copy drifts. It is
  a **check**, not a fixer — it will not auto-sync; it tells you to run `shared:sync`.

See `skills/heroku-to-aws/references/vendored/README.md` for the per-skill marker.

## Adding or changing a validator check

The frontmatter validator (`tools/frontmatter-validator/`) is a zero-dependency TypeScript
program (runs under Node 24 native type-stripping). A new frontmatter key or check
touches, in one change: `types.ts` (the shape) → `parse.ts` (closed vocab + parser) →
`check.ts` (the check) → `tests/tools/frontmatter-validator.test.ts` (a good + a bad
fixture) → `INTERPRETER.md` (the runtime semantics) → the relevant `docs/` pages. Always
prove a new check _bites_ (add a fixture that fails), not just that the real skill still
passes green.

## Submitting a change

1. `mise run build` is green.
2. If you touched `skills/shared/`, you ran `mise run shared:sync` and committed the
   re-synced `references/vendored/` copies.
3. If you added a frontmatter key/check, the docs (`INTERPRETER.md` + `docs/`) and a
   test fixture are updated in the same change.

## Security

For security issue notifications and reporting, see the repo-root
[CONTRIBUTING](../../../CONTRIBUTING.md#security-issue-notifications).

## License

Apache-2.0. See the repo `LICENSE` file.
