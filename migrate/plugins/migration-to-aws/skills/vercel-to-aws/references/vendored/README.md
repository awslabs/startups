# Vendored shared files — DO NOT EDIT

These files are **synced copies** of the plugin-level canonical source under
`migrate/plugins/migration-to-aws/skills/shared/`. They are vendored into this skill
so the skill folder is **self-contained** — it runs standalone (lifted out, zipped,
or used on its own) without reaching outside its own directory.

**Do not hand-edit anything in this directory.** Edit the canonical source instead,
then re-sync:

```sh
mise run shared:sync    # copy canonical -> every skill's references/vendored/
```

CI enforces that these copies are byte-identical to the canonical source
(`mise run shared:check`, wired into `build`). A stale copy fails the build.

| Vendored path                    | Canonical source                               |
| -------------------------------- | ---------------------------------------------- |
| `dsl/INTERPRETER.md`             | `skills/shared/dsl/INTERPRETER.md`             |
| `state/phase-status.schema.json` | `skills/shared/state/phase-status.schema.json` |

Note: `estimate/complexity-tiers.json`, `estimate/estimation-infra.schema.json`, and
`pricing/aws-infra-pricing.json` (vendored by `gcp-to-aws` / `heroku-to-aws`) are
**not** vendored here — this skill has no Estimate phase in v1 (cost estimation
parity with the GCP skill is deferred to v2; see `requirements.md` Out of Scope).

This skill also owns `references/state/assessment-state.schema.json`, which is
**NOT** part of this vendored directory — it has no canonical source elsewhere in
the plugin (it is specific to `vercel-to-aws`'s resumability model). Do not add it
to `mise run shared:sync`.
