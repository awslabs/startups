# Migration report reference fixtures

| File | Purpose |
| --- | --- |
| `migration-report-reference.html` | Complete report shape (passes validator with estimation JSON below) |
| `migration-report-stub.html` | Executive-summary-only stub (172 lines) — **must fail** manual validation |
| `estimation-infra-reference.json` | Trimmed infra estimate aligned with reference HTML |
| `estimation-ai-reference.json` | Trimmed AI estimate aligned with reference HTML |

`migration-report-reference.html` is a **structural reference** for the comprehensive `migration-report.html` output. It uses canonical section IDs checked by `scripts/validate-migration-report.py`.

`migration-report-stub.html` is a **before** artifact: summary-only HTML with a JSON-link appendix stub. Use the CLI command below to confirm incomplete reports fail loudly (not exercised by pytest — see `STUB_FAIL` in `tests/test_validate_migration_report.py`).

**Do not copy dollar figures** into customer reports unless they match the current `$MIGRATION_DIR` estimation artifacts.

## Validate (full contract — must pass)

```bash
python3 scripts/validate-migration-report.py \
  fixtures/migration-report-reference.html \
  --estimation-infra fixtures/estimation-infra-reference.json \
  --estimation-ai fixtures/estimation-ai-reference.json
```

## Validate stub (must fail)

```bash
python3 scripts/validate-migration-report.py \
  fixtures/migration-report-stub.html \
  --estimation-infra fixtures/estimation-infra-reference.json \
  --estimation-ai fixtures/estimation-ai-reference.json
```

`estimation-*-reference.json` are trimmed snapshots aligned with the reference HTML. Together they exercise security-baseline cross-checks and combined-TCO (`exec-tco`) requirements.

## What REPORT_OK means

`REPORT_OK | structure=complete` means required sections, TOC links, and appendix depth checks passed. It does **not** verify that every dollar figure in the HTML matches the JSON — verify numerics manually or in a future accuracy gate before executive sign-off.
