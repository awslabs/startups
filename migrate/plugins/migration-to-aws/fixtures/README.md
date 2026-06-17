# Migration report reference fixture

`migration-report-reference.html` is a **structural reference** for the comprehensive `migration-report.html` output. It was derived from SF Beach migration artifacts (`0611-0606`) and uses canonical section IDs checked by `scripts/validate-migration-report.py`.

**Do not copy dollar figures** into customer reports unless they match the current `$MIGRATION_DIR` estimation artifacts.

## Validate (full contract)

```bash
python3 scripts/validate-migration-report.py \
  fixtures/migration-report-reference.html \
  --estimation-infra fixtures/estimation-infra-reference.json \
  --estimation-ai fixtures/estimation-ai-reference.json
```

`estimation-*-reference.json` are trimmed snapshots aligned with the HTML fixture. Together they exercise security-baseline cross-checks and combined-TCO (`exec-tco`) requirements.

## What REPORT_OK means

`REPORT_OK | structure=complete` means required sections, TOC links, and appendix depth checks passed. It does **not** verify that every dollar figure in the HTML matches the JSON — verify numerics manually or in a future accuracy gate before executive sign-off.
