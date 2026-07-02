# Shared Infrastructure References

This directory references the shared plugin infrastructure located at:

```
../gcp-to-aws/references/shared/
```

The heroku-to-aws skill reuses these shared files from the gcp-to-aws sibling skill:

| File                       | Purpose                                                     |
| -------------------------- | ----------------------------------------------------------- |
| `handoff-gates.md`         | Fail-closed phase handoff protocol (HANDOFF_OK / GATE_FAIL) |
| `migration-complexity.md`  | Complexity tier definitions (Small/Medium/Large)            |
| `schema-estimate-infra.md` | `estimation-infra.json` schema                              |
| `validate-artifacts.md`    | Pre-report validation (Generate Step 0; read-only)          |

## Usage

When a phase reference instructs you to "Load `references/shared/<file>`", read the file from:

```
migrate/plugins/migration-to-aws/skills/gcp-to-aws/references/shared/<file>
```

This avoids file duplication while maintaining consistent behavior across skills.

> **Note:** the `.phase-status.json` schema is no longer here. It is defined once,
> as a real JSON Schema, at `../../shared/state/phase-status.schema.json` (a
> plugin-neutral home, not owned by any single skill), and referenced by
> `INTERPRETER.md` § The interpreter loop.
