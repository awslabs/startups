# Migration report reference fixture

`migration-report-reference.html` is a **structural reference** for the comprehensive `migration-report.html` output. It was derived from SF Beach migration artifacts (`0611-0606`) and uses canonical section IDs checked by `scripts/validate-migration-report.py`.

**Do not copy dollar figures** into customer reports unless they match the current `$MIGRATION_DIR` estimation artifacts.

Validate:

```bash
python3 scripts/validate-migration-report.py fixtures/migration-report-reference.html
```
