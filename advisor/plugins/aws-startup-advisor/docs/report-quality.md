# Migration report quality checks

Report quality is enforced by the plugin’s shipped validator only. Skill users
need **Python 3** — nothing else (no Vale, Pa11y, axe, Chromium, or npm tools).

The agent that generates `migration-report.html` (or `decision-report.html`)
must run `scripts/validate-migration-report.py` after writing the HTML. That
script is stdlib-only and ships with the plugin.

## What the validator covers

- Structure: required section IDs, TOC integrity, appendix depth, no stubs
- Decision UX: verdict before TOC, typography-first verdict (no verdict pills),
  “Stay entirely if”, copy-ready `exec-share` when estimates exist, glossary
  appendix
- Readability: no `Rubric:`, no decorative `Section N` headings, no TCO label,
  no vague intensifiers, ISO dates, reader vocabulary in exec sections
- Accessibility semantics (no browser): `lang` on `<html>`, exactly one `<h1>`,
  table `<caption>` + header `scope`, figure `role="img"` / `aria-label` /
  `<figcaption>`, keyboard `:focus-visible` CSS contract

## How to run (agent / Generate phase)

```bash
python3 scripts/validate-migration-report.py \
  /absolute/path/to/migration-report.html \
  --estimation-infra /absolute/path/to/estimation-infra.json \
  --estimation-ai /absolute/path/to/estimation-ai.json \
  --migration-dir /absolute/path/to/.migration/MMDD-HHMM
```

Omit estimation flags for artifacts that do not exist. Decision reports use
`--mode decision`.

Do **not** ask the user to install prose linters or browser accessibility
suites. If validation fails, fix the HTML and re-run this script.
