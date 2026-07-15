---
_fragment: poc-report
_of_phase: poc
_contributes:
  - poc/poc-report.html
---

# POC sub-step: Build the HTML POC report

> Loaded by poc.md Step 4.5 after the POC files are written (Step 3) — for BOTH modes.
> Produces `$RUN_DIR/poc/poc-report.html` and opens it in the browser. Non-blocking: if
> generation fails, log a warning and continue; the files themselves are the deliverable.

## Overview

A single self-contained HTML file summarizing the POC: what was generated, what changed from
the original app, how to deploy it, the deployment architecture, and what still needs
verifying. Inline CSS + SRI-pinned Mermaid — no other external dependencies. Same visual
language as `recommendation-report.html` (dark header, `#FF9900` accent, card layout).

The report sits in `$RUN_DIR/poc/`, so artifact download links are relative to that dir.

## Step P0 — Gather data

| Variable           | Source                                                                                                                                                     |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POC_FILES`        | the files actually written under `$RUN_DIR/poc/` (walk the dir; EXCLUDE `__pycache__/`, `*.pyc`, and the report itself)                                    |
| `DEPLOYMENT_MODEL` | `confirm.json.deployment_model`                                                                                                                            |
| `MODEL_DISPLAY`    | resolved Bedrock model (Step 2 of poc.md)                                                                                                                  |
| `PLAN_BACKED`      | true if this POC came from a migration plan (3-F / 3-H plan-backed)                                                                                        |
| `CHANGES`          | when plan-backed: `aws-design-ai.json.ai_architecture.code_migration.files_to_modify[].changes[]` and `before_after_example` — the applied migration edits |
| `SOURCE_MODEL`     | when plan-backed: the source model replaced (from the plan)                                                                                                |
| `MODE`             | Mode A (deliverables) or Mode B (assisted build) from Gate 2b                                                                                              |
| `DEPLOY_STEPS`     | the staged steps from `$RUN_DIR/plan.md`                                                                                                                   |
| `DIAGRAM_MERMAID`  | compose a POC-deployment diagram (see Step P2)                                                                                                             |
| `TODOS`            | every `TODO: verify` / deferred / drift note left in the generated files + plan.md                                                                         |
| `LEDGER`           | Mode B only: `$RUN_DIR/poc/created-resources.json` (deployed resources)                                                                                    |
| `RUN_ID`           | from `.phase-status.json`                                                                                                                                  |

## Step P1 — File purpose map

For each file in `POC_FILES`, write a one-line purpose. Infer from the filename/role:

- `app/app.py` → "Migrated app (original UI/handler; local-dev only after migration)"
- `app/core.py` → "Shared LLM logic — used by both the UI and the entrypoint server"
- `app/agentcore_app.py` → "AgentCore Runtime entrypoint server (/invocations + /ping)"
- `app/pyproject.toml` / `requirements.txt` → "Dependencies (provider swap applied)"
- `Dockerfile` → "Container image for AgentCore Runtime"
- `deploy.sh` → "One-command deploy (creates real AWS resources)"
- `README.md` → "Runbook"
- `harness.json` → "Declarative Harness agent definition (the deploy artifact)"
- otherwise → infer a short purpose from the file's first comment/docstring.

## Step P2 — POC deployment diagram

Compose a `flowchart TD` Mermaid block showing the POC's RUNTIME shape (what actually runs
after `deploy.sh`), using the same topology discipline as build-diagram.md:

- Primary flow (solid): User → AgentCore Runtime (hosting the container / `agentcore_app.py`
  entrypoint) → Bedrock model (`MODEL_DISPLAY`).
- Session memory (solid to a store node) if the app has it.
- Enabled AgentCore services as a dotted-attached subgraph (from `confirm.json`).
- For plan-backed framework POCs: annotate the original UI (e.g. "Chainlit UI — local dev
  only") as a dashed node OFF the production path.
  Include an ASCII fallback in a `<details>` block, same as build-diagram.md.

## Step P3 — Write `$RUN_DIR/poc/poc-report.html`

Structure (hide any section whose data is absent — do not emit empty cards):

1. **Header** — "Deployable POC" + model + deployment model + Run ID.
2. **Status banner** — a one-line status: "Generated deliverables (Mode A) — run ./deploy.sh
   yourself" OR "Assisted build (Mode B) — resources deployed, see teardown". If any TODO is
   a correctness blocker (e.g. an unverified model id), a `⚠️` warning banner first.
   2.5. **Help banner (TOP placement)** — load `references/report-help-banner.md`, copy its CSS
   into the `<style>` block, and emit its HTML block (with `{{ HELP_URL }}` substituted) here,
   right after the status banner and before the first content section. This is the shared
   "Need help?" CTA that appears at the top of every report.
3. **Migration changes (before/after)** — when plan-backed: a two-column before/after per
   key change from `CHANGES` (e.g. `from langchain_openai import ChatOpenAI` →
   `from langchain_aws import ChatBedrockConverse`; `gpt-3.5-turbo` → the target model;
   `api_key=...` removed; `/invocations` entrypoint added; UI → local-dev). Use `<pre>` code
   blocks, red-ish for "before", green-ish for "after". When NOT plan-backed, skip this
   section.
4. **Files** — the `POC_FILES` map from P1 as a list, each file a relative download link
   (`<a class="dl-link" href="<relative path>" download>`). Directories: link each file
   individually (browsers can't download a folder).
5. **Deploy steps** — the `DEPLOY_STEPS` as a numbered vertical list, each with its command
   (in a `<code>`/`<pre>`) and its verification. Mark real-resource / billable steps.
6. **Architecture** — the P2 Mermaid diagram (with ASCII fallback in `<details>`).
7. **Known issues / TODO** — `TODOS` as a checklist. Group by severity if clear (blocker vs
   nice-to-have). Be honest — this is what the user must confirm before relying on the POC.
8. **Mode B resources** (Mode B only) — the `LEDGER` as a table (type / name / region /
   status) + a note pointing at `cleanup.sh`.
9. **Footer** — "This POC is a disposable deployment-proof — your original repo was not
   modified. For the authoritative in-repo migration (git branch, tests, eval), run
   /migration-to-aws:llm-to-bedrock." + generation date.

**Styling:** reuse the CSS from `generate-report.md` (copy the same `<style>` block: header,
cards, `.dl-link`, banners, tables, Mermaid theme). The Mermaid `<script>` tag MUST use the
same SRI-pinned version as generate-report.md:
`<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js" integrity="sha384-R63zfMfSwJF4xCR11wXii+QUsbiBIdiDzDbtxia72oGWfkT7WHJfmD/I/eeHPJyT" crossorigin="anonymous"></script>`
Add a before/after style pair:

```css
.diff-before { background:#fef2f2; border-left:3px solid #ef4444; }
.diff-after  { background:#f0fdf4; border-left:3px solid #16a34a; }
.diff-block { font-family: ui-monospace, monospace; font-size:12px; padding:12px 14px;
              border-radius:6px; white-space:pre-wrap; margin:6px 0; }
```

## Step P4 — Open in browser

```bash
open "$RUN_DIR/poc/poc-report.html"    # macOS
xdg-open "$RUN_DIR/poc/poc-report.html"  # Linux
```

If it fails (no GUI), print: `POC report ready — open: file://$RUN_DIR/poc/poc-report.html`

## Step P5 — Report completion

Return to poc.md. Do NOT update `.phase-status.json` — poc.md Step 6 handles phase state.
