# Validate Migration Report (Post-Write)

> **Read-only validation.** Run immediately after writing `migration-report.html` in `generate-artifacts-report.md` Step 4. Do NOT modify JSON artifacts.

If validation fails: **delete or do not ship** the incomplete HTML, emit failures to the user, and retry report generation. The Generate phase still completes (report is optional), but the user MUST see `REPORT_FAIL` — never silently accept a stub report.

---

## How to run

From the plugin root (or with absolute paths):

```bash
python3 migrate/plugins/migration-to-aws/scripts/validate-migration-report.py \
  "$MIGRATION_DIR/migration-report.html" \
  --estimation-infra "$MIGRATION_DIR/estimation-infra.json"
```

On macOS/Linux when `$MIGRATION_DIR` is the migration output folder (e.g. `.migration/0611-0606/`).

---

## Required checks (REPORT_FAIL on any failure)

| # | Check | PASS when |
|---|-------|-----------|
| 1 | Section IDs | All required IDs present exactly once: `decision-summary`, `exec-services`, `exec-costs`, `exec-timeline`, `exec-risks`, `appendix-services`, `appendix-costs`, `appendix-steps`, `appendix-artifacts` |
| 2 | Appendix tables | `appendix-costs` has ≥3 `<tr>` in `<tbody>`; `appendix-services` ≥2; `appendix-steps` ≥2 |
| 3 | No stubs | Appendix B is not only "see estimation-infra.json"; appendix must render numeric costs from artifacts |
| 4 | Security costs | If `estimation-infra.json` → `projected_costs.breakdown.security_baseline` exists: report mentions **GuardDuty** OR includes `security_baseline` mid cost |
| 5 | Footer | Contains "draft for review" |
| 6 | No placeholders | No `[placeholder]` or `TODO` in report body |
| 7 | Combined TCO | If `estimation-ai.json` exists AND `appendix-ai` section present: `exec-tco` section exists with infra + AI totals |

---

## Optional sections (recommended — warn if missing when data exists)

| Section ID | Include when |
|------------|--------------|
| `exec-tco` | Both `estimation-infra.json` and `estimation-ai.json` exist |
| `exec-architecture` | `aws-design.json` with clusters exists |
| `exec-security-teaser` | `estimation-infra.json` has `security_baseline` breakdown |
| `appendix-ai` | `estimation-ai.json` or `aws-design-ai.json` exists |
| `appendix-security` | Appendix G full capabilities table (or merge into `appendix-security`) |
| `appendix-security-gap` | Infra track ran |
| `appendix-assumptions` | Always recommended: pricing confidence, exclusions, `validation-report.json` status |

If optional sections are missing but data exists, log:

```
REPORT_WARN | section=<id> | reason=recommended_for_complete_report
```

Do **not** fail Generate on `REPORT_WARN` alone.

---

## Output

**Pass:**

```
REPORT_OK | sections=9/9 | optional=exec-tco,appendix-ai,appendix-security-gap
```

**Fail:**

```
REPORT_FAIL | migration-report.html
  - missing required section id=appendix-costs
  - appendix section id=appendix-services has 0 table rows, need >= 2
```

---

## Reference fixture

See `migrate/plugins/migration-to-aws/fixtures/migration-report-reference.html` for a complete report shape derived from SF Beach migration artifacts. Use it as a structural reference when generating HTML — **do not copy numbers** unless they match the current `$MIGRATION_DIR` artifacts.
