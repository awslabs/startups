# heroku-to-aws Shared References

This directory holds references shared _within_ the heroku-to-aws skill (across its
phases). It no longer symlinks the gcp-to-aws sibling skill — heroku-to-aws is
self-contained.

| File                        | Purpose                                                     |
| --------------------------- | ----------------------------------------------------------- |
| `heroku-pricing-cache.md`   | Heroku plan pricing (source-side baseline for the estimate) |
| `schema-discover-heroku.md` | `heroku-resource-inventory.json` schema                     |

## Plugin-neutral shared data

Cross-skill data that other DSL migration skills also use lives in the plugin-neutral
`skills/shared/` tree (not owned by any single skill), referenced by phase frontmatter
`_knowledge` or `INTERPRETER.md`:

| Path                                                 | Purpose                                      |
| ---------------------------------------------------- | -------------------------------------------- |
| `../../shared/state/phase-status.schema.json`        | `.phase-status.json` schema (JSON Schema)    |
| `../../shared/estimate/estimation-infra.schema.json` | `estimation-infra.json` schema (JSON Schema) |
| `../../shared/estimate/complexity-tiers.json`        | Migration complexity-tier thresholds         |
| `../../shared/pricing/aws-infra-pricing.json`        | Cached AWS infrastructure pricing            |

The gate protocol, re-entry, and phase-status lifecycle that used to live in shared
gcp prose are now defined in `INTERPRETER.md` (§ Gate protocol, § `_re_entry_guard`,
§ The interpreter loop) and each phase's `_preconditions` / `_postconditions`
frontmatter.
