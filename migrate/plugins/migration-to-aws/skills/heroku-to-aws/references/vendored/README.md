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

| Vendored path                           | Canonical source                                      |
| --------------------------------------- | ----------------------------------------------------- |
| `dsl/INTERPRETER.md`                    | `skills/shared/dsl/INTERPRETER.md`                    |
| `state/phase-status.schema.json`        | `skills/shared/state/phase-status.schema.json`        |
| `estimate/complexity-tiers.json`        | `skills/shared/estimate/complexity-tiers.json`        |
| `estimate/estimation-infra.schema.json` | `skills/shared/estimate/estimation-infra.schema.json` |
| `pricing/aws-infra-pricing.json`        | `skills/shared/pricing/aws-infra-pricing.json`        |
