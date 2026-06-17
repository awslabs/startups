# Validate Migration Report (Post-Write)

> **Read-only validation.** Run immediately after writing `migration-report.html` in `generate-artifacts-report.md` Step 4. Do NOT modify JSON artifacts.

If validation fails: **rename** the incomplete HTML to `migration-report.incomplete.html` (default — preserves output for inspection), emit failures to the user, and retry report generation. Do **not** delete unless the user asks. The Generate phase still completes (report is optional), but the user MUST see `REPORT_FAIL` — never silently accept a stub report.

---

## How to run (deterministic script path)

The validator script ships with the plugin at:

`migrate/plugins/migration-to-aws/scripts/validate-migration-report.py`

**From `$MIGRATION_DIR`** (e.g. `.migration/0611-0606/`), resolve the script relative to the installed plugin root. If the agent knows the plugin checkout path `$PLUGIN_ROOT`:

```bash
python3 "$PLUGIN_ROOT/scripts/validate-migration-report.py" \
  "$MIGRATION_DIR/migration-report.html" \
  --estimation-infra "$MIGRATION_DIR/estimation-infra.json" \
  --estimation-ai "$MIGRATION_DIR/estimation-ai.json"
```

Pass `--estimation-ai` only when that file exists. Omit flags for artifacts that were not generated.

The script also exposes its path via `Path(__file__)` when invoked directly from the plugin copy.

---

## Scope

This validator is a **structural completeness gate**. It does **not** verify that every dollar figure in the HTML matches estimation JSON. Self-check item #6 in `generate-artifacts-report.md` (numeric accuracy) remains a manual step. `REPORT_OK | structure=complete` means the report is ready for human review, not financially audited.

---

## Required checks (REPORT_FAIL on any failure)

| # | Check | PASS when |
|---|-------|-----------|
| 1 | Section IDs | Each required ID appears **exactly once** on a `<section id="...">` element (not `<div>`) |
| 2 | Table of contents | `<nav class="toc">` exists; every `href="#id"` matches a `<section id="id">`; every required section is linked |
| 3 | Appendix content | `appendix-costs` ≥3 data rows; `appendix-services` ≥2 mappings; `appendix-steps` ≥2 phases/rows |
| 4 | No stubs | Appendix B is not only "see estimation-infra.json"; appendix must render numeric costs from artifacts |
| 5 | Security costs | If `security_baseline` in estimate: **GuardDuty** or dollar-formatted component costs appear in `appendix-security` / `appendix-costs` (bare `15` in CSS does not count) |
| 6 | Footer | Contains "draft for review" |
| 7 | No placeholders | No `[placeholder]` or `TODO` in report body |
| 8 | Combined TCO | If **both** `estimation-infra.json` and `estimation-ai.json` are passed: exactly one `<section id="exec-tco">` |

---

## Optional sections (recommended — warn if missing when data exists)

| Section ID | Include when |
|------------|--------------|
| `exec-tco` | Both `estimation-infra.json` and `estimation-ai.json` exist |
| `exec-architecture` | `aws-design.json` with clusters exists |
| `exec-security-teaser` | `estimation-infra.json` has `security_baseline` breakdown |
| `appendix-ai` | `estimation-ai.json` or `aws-design-ai.json` exists |
| `appendix-security` | Full security capabilities table |
| `appendix-security-gap` | Infra track ran |
| `appendix-assumptions` | Pricing confidence, exclusions, validation status |

---

## Output

**Pass:**

```
REPORT_OK | structure=complete | sections=9/9 | optional=exec-tco,appendix-ai | note=verify dollar figures against estimation JSON before sign-off
```

`structure=complete` does **not** mean dollar figures were cross-checked against JSON — only that sections, TOC, appendix depth, and artifact-driven gates passed.

**Fail:**

```
REPORT_FAIL | migration-report.html
  - TOC broken link href="#decision" — no matching <section id="decision">
  - duplicate <section id="exec-costs"> (2 occurrences)
```

---

## Reference fixture

`migrate/plugins/migration-to-aws/fixtures/migration-report-reference.html` — TOC `href` values match `section id` attributes exactly. Validate with:

```bash
python3 "$PLUGIN_ROOT/scripts/validate-migration-report.py" \
  "$PLUGIN_ROOT/fixtures/migration-report-reference.html" \
  --estimation-infra "$PLUGIN_ROOT/fixtures/estimation-infra-reference.json" \
  --estimation-ai "$PLUGIN_ROOT/fixtures/estimation-ai-reference.json"
```
