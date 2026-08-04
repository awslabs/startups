# ATX Custom bundle — agent-advisor

The plugin keeps the **full** skill under `skills/agent-advisor/`, including the Migration Plan
stage that reads the sibling `gcp-to-aws` engine. ATX Custom has no sibling skills to read, so the
transformation published there must be self-contained.

Rather than fork the prose — which drifts, as this repo has learned more than once — the ATX
bundle is a **strict subset** of the canonical skill plus exactly one generated file:

```text
transformation_definition.md = preamble.md + skills/agent-advisor/SKILL.md (frontmatter stripped)
```

Every other file in the bundle is byte-identical to its canonical source. There is no second copy
of any instruction to keep in sync.

| File           | Role                                                                                                                                                                                                                             |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `preamble.md`  | The only ATX-specific text: executor differences (no interactive tools, no subagent dispatch, `${CLAUDE_PLUGIN_ROOT}` fallback), the headless input contract, the exit criteria, and the required `validation_summary.md` format |
| `manifest.txt` | Whitelist of canonical files that ship. A canonical file that is neither listed nor matched by an exclusion rule fails `atx:check` — new files must be classified, never silently dropped                                        |

## Commands

```bash
mise run atx:build   # write the bundle to .tmp/atx-bundle/agent-advisor/, then verify
mise run atx:check   # verify only (part of `mise run lint`)
```

`atx:build` writes a directory of plain text and `.py` files with no build step and no install:
point whatever runs it at `transformation_definition.md` and give it that directory as the root every
relative path resolves against. Publishing to a transformation registry is a deliberate manual step,
and the registry's own CLI owns it — nothing in this repo does it for you.

## What `atx:check` guarantees

1. **Manifest ↔ canonical agree** — no dangling entries, no unclassified canonical files.
2. **No sibling-skill loads** — a resolvable path into another skill (`${CLAUDE_PLUGIN_ROOT}/skills/<other>`, `$GCP_BASE`) is an error everywhere except `references/phases/migration-plan/`, whose Step -1 capability gate resolves the stage to `not_applicable` when the engine is absent. This check is what makes "the ATX build does not depend on gcp-to-aws" a machine-verified property.
3. **The capability gate exists** — `migration-plan.md` must carry its marker, so the bundle degrades honestly instead of trying to read files that are not there.
4. **The phase graph closes inside the bundle** — every `_file:` fragment and `_advances_to:` target resolves within the shipped set.
5. **Runtime scripts load on a bare host** — no top-level third-party import. Lazy imports are reported as warnings, since they only bind on a code path that may be disabled (the live model probe) or provisioned by `uv`.

Warnings are tracked, not fatal: prose that names a sibling skill or a Claude Code slash command
still works, but it dangles for an ATX reader and should be reworded to be environment-neutral.
