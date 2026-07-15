---
_fragment: generate-report
_of_phase: generate
_contributes:
  - recommendation-report.html
---

# Generate Phase: HTML Recommendation Report

> Loaded by `generate.md` after Steps 3–5 complete (diagram written, recommendation.md
> written, scaffold written, mini-brief printed, gates set). Execute ALL steps in order.

## Overview

Generate a single self-contained HTML file (`$RUN_DIR/recommendation-report.html`) that
presents the agent architecture recommendation visually — a consulting-style report that
mirrors ALL 12 sections of recommendation.md. The file uses inline CSS and a CDN-loaded
Mermaid.js for the diagram — no other external dependencies. Users can open it in any
browser and use "Print to PDF" if needed.

**Before writing the HTML:** load two shared single-source files:

- `references/report-shell.md` — inline its CSS block (the shared chrome: reset & base,
  `.page`, `.site-header`, `.hero-panel`, `.kpi-row`, `.chip-row`/`.chip`, `.card`,
  `.section-title`, `.feat-grid`, `.timeline`, `.banner*`, base table, `.two-col`,
  `.report-footer`, and the chart color tokens `--chart-accent`/`--chart-muted`) into the
  `<style>` block at the `{{ SHARED_SHELL_CSS ... }}` marker, and inline its SRI-pinned
  mermaid@10.9.3 script tag at the `{{ SHARED_SHELL_MERMAID_TAG ... }}` marker in `<head>`.
  The remaining rules in the `<style>` block below are this report's OWN content CSS.
- `references/report-help-banner.md` — copy its CSS rules into the `<style>` block and emit
  its HTML block at the `<!-- HELP BANNER -->` marker below (with `{{ HELP_URL }}`
  substituted). This is the shared "Need help?" CTA banner that appears in every report.

**Non-blocking:** if HTML generation fails for any reason, log a warning, do NOT fail the
Generate phase, and continue. The recommendation.md is the authoritative document.

## Step R0 — Gather data

Read all available sources. Mark each as present or absent — absent fields use the fallback
rules below.

| Variable                 | Source                                                                                                                                                                                                                                                    | Fallback                         |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `VERDICT`                | `design.json.verdict`                                                                                                                                                                                                                                     | —                                |
| `DEPLOYMENT_MODEL`       | `confirm.json.deployment_model`                                                                                                                                                                                                                           | `design.json.deployment_model`   |
| `SERVICES`               | `confirm.json.agentcore_services`                                                                                                                                                                                                                         | `design.json.agentcore_services` |
| `MODEL_KEY`              | `design.json.model_recommendation.model`                                                                                                                                                                                                                  | —                                |
| `MODEL_DISPLAY`          | Map from MODEL_KEY: `claude_sonnet_4_6`→"Claude Sonnet 4.6", `claude_haiku_4_5`→"Claude Haiku 4.5", `nova_pro`→"Amazon Nova Pro", `nova_lite`→"Amazon Nova Lite", `nova_micro`→"Amazon Nova Micro", `llama4_maverick`→"Llama 4 Maverick", other→MODEL_KEY |                                  |
| `MODEL_REASONING`        | `design.json.model_recommendation.reasoning` (the model-reason line; recommendation.md §9 has the prose form)                                                                                                                                             | ""                               |
| `MODEL_ALTERNATES`       | `design.json.model_recommendation.alternates` / recommendation.md §9 alternate models (display names)                                                                                                                                                     | []                               |
| `EXEC_LEAD`              | recommendation.md §1 Executive summary — 1–2 plain-language sentences (trim to at most two)                                                                                                                                                               | ""                               |
| `PROFILE`                | The driver answers from recommendation.md §2 / `answers.json.answers` — max 8 entries, each a `label: value` pair in plain words (e.g. "Traffic: bursty", "Memory: cross-session")                                                                        | []                               |
| `SIX_DIMS`               | recommendation.md §7 — the 6 dimension one-liners, keyed Identity / Observability / Guardrails / Scaling / Tools & Gateway / Protocols                                                                                                                    | null                             |
| `ALTERNATIVES`           | Each non-winning runtime + a one-line reason, from recommendation.md §5 / `scoring-result.json`: for eliminated runtimes the elimination reason (`ELIMINATED[runtime]`); for scored-but-lower runtimes the main scoring gap vs the winner                 | []                               |
| `NEXT_STEPS`             | recommendation.md §11 — each step: title, one-line body, optional command                                                                                                                                                                                 | []                               |
| `SCORES`                 | `scoring-result.json.scores` (object: runtime→score)                                                                                                                                                                                                      | —                                |
| `ELIMINATED`             | `scoring-result.json.eliminated` (object: runtime→reason)                                                                                                                                                                                                 | {}                               |
| `WARNINGS`               | `scoring-result.json.warnings`                                                                                                                                                                                                                            | []                               |
| `IO_WAIT_NOTE`           | `design.json.io_wait_tco_note`                                                                                                                                                                                                                            | false                            |
| `FEDRAMP_NOTE`           | `design.json.fedramp_note`                                                                                                                                                                                                                                | false                            |
| `REGION_NOTE`            | `design.json.region_availability_note`                                                                                                                                                                                                                    | null                             |
| `VOLATILE_FACTS`         | `design.json.volatile_facts`                                                                                                                                                                                                                              | {}                               |
| `COST_BAND`              | `estimate.json.monthly_magnitude_usd` if file exists                                                                                                                                                                                                      | null                             |
| `COST_ASSUMPTIONS`       | `estimate.json.assumptions` if file exists                                                                                                                                                                                                                | []                               |
| `SCAFFOLD_EXISTS`        | true if `$RUN_DIR/scaffold/` directory exists and is non-empty                                                                                                                                                                                            | false                            |
| `DIAGRAM_MERMAID`        | Extract the fenced ```mermaid block from `diagram.md`                                                                                                                                                                                                     | null                             |
| `DIAGRAM_ASCII`          | Extract the ASCII block inside `<details>` from `diagram.md`                                                                                                                                                                                              | null                             |
| `RUN_DATE`               | From `design.json` or current date                                                                                                                                                                                                                        | "2026"                           |
| `ENTRY_POINT`            | `answers.json.entry_point`                                                                                                                                                                                                                                | "build"                          |
| `ANSWERS`                | `answers.json.answers`                                                                                                                                                                                                                                    | {}                               |
| `MANAGED_ALTERNATIVE`    | `design.json.managed_alternative`                                                                                                                                                                                                                         | null                             |
| `RECOMMENDATION_MD_PATH` | `$RUN_DIR/recommendation.md`                                                                                                                                                                                                                              | —                                |

## Step R1 — Build score bar data

Sort SCORES descending by value. The highest score is the winner (= VERDICT).

For the bar chart, compute each runtime's percentage relative to the max score:
`pct = round(score / max_score * 100)`.

Bar fill colors come from the shell's chart tokens: the winner's bar uses
`var(--chart-accent)`, every other bar uses `var(--chart-muted)`.

Runtime display names:

- `agentcore` → "AgentCore Runtime"
- `lambda_microvms` → "Lambda MicroVMs"
- `lambda` → "Lambda"
- `ecs` → "ECS (Fargate)"
- `eks` → "EKS"

Deployment model display names:

- `harness` → "AgentCore Harness (no-code)"
- `framework_on_runtime` → "Framework on Runtime (bring your own code)"
- `framework` → "Framework on Runtime (bring your own code)"

Service display names and descriptions:

- `identity` → "Identity" / "Session authentication & caller verification — always on, free."
- `observability` → "Observability" / "Automatic OpenTelemetry traces — every LLM call, latency, and error without code changes — always on, free."
- `evaluations` → "Evaluations" / "Response quality tracking and regression gates — always on, free."
- `optimization` → "Optimization" / "Model routing hints and cost optimization — always on, free."
- `memory` → "Memory" / "Persistent cross-session memory — replaces in-process conversation buffers with a durable store."
- `gateway` → "Gateway" / "Connects external APIs and MCP tools to the agent."
- `code_interpreter` → "Code Interpreter" / "Sandboxed code execution inside the agent."
- `managed_kb` → "Managed KB" / "Built-in RAG over your internal documents."
- `policy` → "Policy" / "Cedar-based authorization for high-risk agent actions."

Always-on (free) services: `identity`, `observability`, `evaluations`, `optimization`.
User-selected (add-on) services: everything else in SERVICES.

## Step R2 — Write the HTML file

Write `$RUN_DIR/recommendation-report.html` with the following structure. Every `{{ }}` is
a substitution from Step R0/R1. Do not output placeholder text — if a value is absent, hide
that element entirely (use `display:none` or omit the HTML block).

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AWS Agent Architecture Recommendation</title>
<!-- SRI-pinned mermaid@10.9.3 script tag — inline it VERBATIM from the shared shell
     (references/report-shell.md), same tag/integrity hash used by every report with a diagram. -->
{{ SHARED_SHELL_MERMAID_TAG from references/report-shell.md }}
<style>
  /* ── Shared chrome ── load references/report-shell.md and inline its CSS block
     HERE (chart tokens, reset & base, .page layout, .site-header, .hero-panel,
     .kpi-row, .chip-row/.chip, .card, .section-title, .feat-grid, .timeline,
     .banner*, base table/th/td, .two-col, .report-footer). Single-sourced there
     so this report and the temporal report share identical chrome — do not
     restate those rules here. ── */
  {{ SHARED_SHELL_CSS from references/report-shell.md }}

  /* ── Scores (content) ── */
  .score-row { display: grid; grid-template-columns: 180px 1fr 50px;
               align-items: center; gap: 14px; margin-bottom: 12px; }
  .score-row:last-child { margin-bottom: 0; }
  .score-name { font-size: 14px; font-weight: 500; }
  .score-name.winner { color: var(--chart-accent); font-weight: 700; }
  .bar-track { background: #f3f4f6; border-radius: 4px; height: 10px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; background: var(--chart-muted); }
  .bar-fill.winner { background: var(--chart-accent); }
  .score-val { font-size: 14px; font-weight: 600; text-align: right; color: #6b7280; }
  .score-val.winner { color: var(--chart-accent); }
  .elim-label { font-size: 11px; color: #ef4444; font-style: italic;
                grid-column: 2 / 4; margin-top: -8px; margin-bottom: 4px; }

  /* ── Diagram card ── */
  .diagram-card { background: #fff; border-radius: 12px; padding: 28px 32px;
                  box-shadow: 0 2px 8px rgba(0,0,0,.06); overflow: auto; }
  .mermaid { min-height: 200px; }
  .diagram-ascii { font-family: monospace; font-size: 12px; color: #374151;
                   white-space: pre; background: #f9fafb; padding: 16px;
                   border-radius: 8px; margin-top: 12px; display: none; }

  /* ── Why card ── */
  .why-card { background: #fff; border-radius: 12px; padding: 28px 32px;
              box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .why-card ol { padding-left: 20px; }
  .why-card li { margin-bottom: 10px; font-size: 14px; color: #374151; }
  .why-card li strong { color: #1a1a2e; }

  /* ── Comparison table ── */
  .table-card { background: #fff; border-radius: 12px; padding: 28px 32px;
                box-shadow: 0 2px 8px rgba(0,0,0,.06); overflow-x: auto; }
  /* base table/th/td/tr styles come from the shared shell CSS inlined above */
  .check  { color: #16a34a; font-weight: 700; }
  .cross  { color: #9ca3af; }
  .winner-col { background: #fffbeb; }

  /* ── Alternatives ── */
  .alt-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
              gap: 12px; }
  .alt { background: #fff; border: 1px solid #eef0f3;
         border-left: 3px solid var(--chart-muted); border-radius: 10px;
         padding: 12px 16px; }
  .alt-name { font-size: 14px; font-weight: 700; color: #1a1a2e; }
  .alt-reason { font-size: 13px; color: #6b7280; margin-top: 2px; }

  /* ── Services grid ── */
  .services-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                   gap: 16px; }
  .service-card { background: #fff; border-radius: 10px; padding: 20px;
                  box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .service-card.addon-card { border-top: 3px solid #FF9900; }
  .service-card .svc-name { font-size: 14px; font-weight: 700; color: #1a1a2e;
                             margin-bottom: 6px; }
  .service-card .svc-badge { font-size: 11px; font-weight: 600; border-radius: 4px;
                              padding: 2px 8px; display: inline-block; margin-bottom: 8px; }
  .badge-free  { background: #f0fdf4; color: #15803d; }
  .badge-addon { background: #fff7ed; color: #c2410c; }
  .service-card .svc-desc { font-size: 13px; color: #6b7280; line-height: 1.5; }

  /* ── Cost card ── */
  .cost-card { background: #fff; border-radius: 12px; padding: 28px 32px;
               box-shadow: 0 2px 8px rgba(0,0,0,.06); }
  .cost-band { font-size: 32px; font-weight: 700; color: #1a1a2e; }
  .cost-label { font-size: 13px; color: #6b7280; }
  .cost-note  { font-size: 13px; color: #6b7280; margin-top: 10px;
                padding-top: 10px; border-top: 1px solid #f0f0f0; }
  .assumption-list { list-style: disc; padding-left: 18px; font-size: 13px;
                     color: #6b7280; margin-top: 8px; }

  /* ── Artifact links ── */
  .dl-link { font-size: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
             color: #b45309; text-decoration: none; border-bottom: 1px solid transparent;
             transition: border-color .15s; }
  .dl-link:hover { border-bottom-color: #b45309; }
  .dl-link::after { content: " ↓"; color: #9ca3af; font-size: 11px; }
  .artifact-row { display: flex; gap: 10px; align-items: baseline; font-size: 13px;
                  color: #6b7280; margin-bottom: 10px; }
  .artifact-row:last-child { margin-bottom: 0; }

  /* ── Print ── */
  @media print {
    body { background: #fff; }
    .site-header { background: #1a1a2e !important; -webkit-print-color-adjust: exact; }
    .hero-panel { -webkit-print-color-adjust: exact; }
    .bar-fill.winner { background: var(--chart-accent) !important; -webkit-print-color-adjust: exact; }
  }
</style>
</head>
<body>

<!-- HEADER -->
<header class="site-header">
  <div class="inner">
    <h1>AWS Agent Architecture Recommendation</h1>
    <div class="meta">
      Generated {{ RUN_DATE }}<br>
      Run ID: {{ RUN_ID }}
    </div>
  </div>
</header>

<div class="page">

<!-- HELP BANNER — shared CTA at the TOP of the report.
     Load references/report-help-banner.md and emit its HTML block (with {{ HELP_URL }}
     substituted). Also copy its CSS rules into the <style> block above. -->
{{ HELP_BANNER_HTML from references/report-help-banner.md }}

<!-- HERO PANEL — the report's single headline block -->
<div class="hero-panel">
  <div class="hero-eyebrow">Recommendation</div>
  <div class="hero-verdict">{{ RUNTIME_DISPLAY }}<small>{{ DEPLOYMENT_MODEL_DISPLAY }}</small></div>
  {{ IF EXEC_LEAD }}<p class="hero-lead">{{ EXEC_LEAD }}</p>{{ END IF }}
  <div class="hero-badges">
    <span class="badge">Score {{ WINNER_SCORE }} — next best {{ RUNNER_UP_SCORE }}</span>
    <span class="badge neutral">Entry point: {{ ENTRY_POINT }}</span>
    {{ IF ANSWERS.region AND ANSWERS.region != "unknown" }}
    <span class="badge neutral">Region: {{ ANSWERS.region }}</span>
    {{ END IF }}
  </div>
</div>

<!-- KPI ROW — 4 stat tiles right under the hero. Values are plain proportional
     figures (the shell does NOT set tabular-nums — keep it that way). -->
<div class="kpi-row">
  <div class="kpi">
    <div class="kpi-label">Runtime</div>
    <div class="kpi-value">{{ RUNTIME_SHORT_NAME e.g. "AgentCore", "Lambda", "ECS Fargate", "EKS", "Lambda MicroVMs" }}</div>
    <div class="kpi-note">{{ DEPLOYMENT_MODEL_DISPLAY }}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Bedrock model</div>
    <div class="kpi-value">{{ MODEL_DISPLAY }}</div>
    <div class="kpi-note">{{ model family, e.g. "Claude family", or "default" }}</div>
  </div>
  <div class="kpi">
    {{ IF COST_BAND }}
    <div class="kpi-label">Monthly cost</div>
    <div class="kpi-value">${{ COST_BAND }}</div>
    <div class="kpi-note">order-of-magnitude</div>
    {{ ELSE }}
    <!-- Migrate path (no estimate.json): NEVER invent a number -->
    <div class="kpi-label">Monthly cost</div>
    <div class="kpi-value">See migration plan</div>
    <div class="kpi-note">costed by the migration plugins</div>
    {{ END IF }}
  </div>
  <div class="kpi">
    <div class="kpi-label">AgentCore services</div>
    <div class="kpi-value">{{ COUNT(SERVICES) }}</div>
    <div class="kpi-note">{{ COUNT(always-on services IN SERVICES) }} free tier</div>
  </div>
</div>

<!-- WARNINGS (only if WARNINGS non-empty) -->
{{ FOR EACH warning IN WARNINGS }}
<div class="banner warning">
  <span class="banner-icon">⚠️</span>
  <span>{{ warning }}</span>
</div>
{{ END FOR }}

<!-- FedRAMP note (only if FEDRAMP_NOTE true) -->
{{ IF FEDRAMP_NOTE }}
<div class="banner fedramp">
  <span class="banner-icon">🔒</span>
  <span><strong>FedRAMP note:</strong> AgentCore FedRAMP authorization is in progress.
  For FedRAMP-required workloads, validate current status and consider GovCloud as
  a fallback before committing to AgentCore.</span>
</div>
{{ END IF }}

<!-- Region availability note (only if REGION_NOTE non-null) -->
{{ IF REGION_NOTE }}
<div class="banner info">
  <span class="banner-icon">📍</span>
  <span><strong>Region:</strong> {{ REGION_NOTE }}</span>
</div>
{{ END IF }}

<!-- I/O-wait TCO note (only if IO_WAIT_NOTE true) -->
{{ IF IO_WAIT_NOTE }}
<div class="banner tco">
  <span class="banner-icon">💡</span>
  <span><strong>TCO advantage:</strong> AgentCore charges $0 during model I/O wait
  (streaming, model latency, human typing pauses). For bursty or HITL workloads, a
  significant fraction of wall-clock time is idle — you only pay for active CPU.</span>
</div>
{{ END IF }}

<!-- YOUR PROFILE (recommendation.md §2) -->
{{ IF PROFILE non-empty }}
<p class="section-title">Your profile</p>
<div class="card">
  <div class="chip-row">
    {{ FOR EACH (label, value) IN PROFILE }}
    <span class="chip"><strong>{{ label }}</strong> {{ value }}</span>
    {{ END FOR }}
  </div>
</div>
{{ END IF }}

<!-- SCORES -->
<p class="section-title">Runtime Scores</p>
<div class="card">
{{ FOR EACH (runtime, score, pct) IN SORTED_SCORES }}
  <div class="score-row">
    <div class="score-name {{ 'winner' IF runtime == VERDICT }}">
      {{ RUNTIME_DISPLAY_NAME(runtime) }}
      {{ IF runtime IN ELIMINATED }} &nbsp;<span style="font-size:11px;color:#ef4444;font-weight:400;">(eliminated)</span>{{ END IF }}
    </div>
    <div class="bar-track">
      <div class="bar-fill {{ 'winner' IF runtime == VERDICT }}"
           style="width:{{ pct }}%"></div>
    </div>
    <div class="score-val {{ 'winner' IF runtime == VERDICT }}">{{ score }}</div>
  </div>
  {{ IF runtime IN ELIMINATED }}
  <div class="elim-label">{{ ELIMINATED[runtime] }}</div>
  {{ END IF }}
{{ END FOR }}
</div>

<!-- DIAGRAM + WHY -->
<p class="section-title">Architecture &amp; Rationale</p>
<div class="two-col">
  <div class="diagram-card">
    {{ IF DIAGRAM_MERMAID }}
    <div class="mermaid">{{ DIAGRAM_MERMAID }}</div>
    <pre class="diagram-ascii" id="ascii-fallback">{{ DIAGRAM_ASCII }}</pre>
    {{ ELSE }}
    <pre class="diagram-ascii" style="display:block">{{ DIAGRAM_ASCII }}</pre>
    {{ END IF }}
  </div>
  <div class="why-card">
    <p style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;
              letter-spacing:.8px;margin-bottom:14px;">Why {{ RUNTIME_DISPLAY }}</p>
    <!-- Extract top 3 bullet points from recommendation.md Section 3 "wins because:" -->
    <ol>
      {{ TOP_3_WHY_BULLETS from recommendation.md Section 3 }}
    </ol>
    {{ IF IO_WAIT_NOTE }}
    <div style="margin-top:16px;padding:12px;background:#f0fdf4;border-radius:8px;
                font-size:13px;color:#166534;">
      💡 <strong>I/O-wait billing edge:</strong> you pay $0 while the model generates
      or users type — real cost advantage for interactive chat.
    </div>
    {{ END IF }}
  </div>
</div>

<!-- SIX DIMENSIONS (recommendation.md §7 — only if SIX_DIMS present) -->
{{ IF SIX_DIMS }}
<p class="section-title">Six Dimensions</p>
<div class="feat-grid">
  <div class="feat">
    <div class="feat-icon">🔐</div>
    <div><div class="feat-name">Identity</div>
         <div class="feat-desc">{{ SIX_DIMS.identity }}</div></div>
  </div>
  <div class="feat">
    <div class="feat-icon">📊</div>
    <div><div class="feat-name">Observability</div>
         <div class="feat-desc">{{ SIX_DIMS.observability }}</div></div>
  </div>
  <div class="feat">
    <div class="feat-icon">🛡️</div>
    <div><div class="feat-name">Guardrails</div>
         <div class="feat-desc">{{ SIX_DIMS.guardrails }}</div></div>
  </div>
  <div class="feat">
    <div class="feat-icon">⚖️</div>
    <div><div class="feat-name">Scaling</div>
         <div class="feat-desc">{{ SIX_DIMS.scaling }}</div></div>
  </div>
  <div class="feat">
    <div class="feat-icon">🔌</div>
    <div><div class="feat-name">Tools &amp; Gateway</div>
         <div class="feat-desc">{{ SIX_DIMS.tools_gateway }}</div></div>
  </div>
  <div class="feat">
    <div class="feat-icon">🔁</div>
    <div><div class="feat-name">Protocols</div>
         <div class="feat-desc">{{ SIX_DIMS.protocols }}</div></div>
  </div>
</div>
{{ END IF }}

<!-- COMPARISON TABLE -->
<p class="section-title">Runtime Comparison</p>
<div class="table-card">
<!-- Extract the comparison table from recommendation.md Section 6 and render it here.
     Mark the VERDICT column with class="winner-col", ✅ with class="check", ❌ with class="cross" -->
  <table>
    <thead>
      <tr>
        {{ FOR EACH col IN TABLE_COLUMNS }}
        <th {{ 'class="winner-col"' IF col == VERDICT_DISPLAY }}>{{ col }}</th>
        {{ END FOR }}
      </tr>
    </thead>
    <tbody>
      {{ FOR EACH row IN TABLE_ROWS }}
      <tr>
        {{ FOR EACH cell IN row }}
        <td {{ 'class="winner-col"' IF col == VERDICT_DISPLAY }}>
          {{ IF cell == "Yes" OR cell == "✅" }}<span class="check">✓</span>
          {{ ELSE IF cell == "No" OR cell == "❌" }}<span class="cross">—</span>
          {{ ELSE }}{{ cell }}{{ END IF }}
        </td>
        {{ END FOR }}
      </tr>
      {{ END FOR }}
    </tbody>
  </table>
</div>

<!-- ALTERNATIVES (recommendation.md §5 — only if ALTERNATIVES non-empty) -->
{{ IF ALTERNATIVES non-empty }}
<p class="section-title">Alternatives considered</p>
<div class="alt-grid">
  {{ FOR EACH (runtime, reason) IN ALTERNATIVES }}
  <div class="alt">
    <div class="alt-name">{{ RUNTIME_DISPLAY_NAME(runtime) }}</div>
    <div class="alt-reason">{{ reason }}</div>
  </div>
  {{ END FOR }}
  {{ IF MANAGED_ALTERNATIVE == "bedrock_managed" }}
  <div class="alt">
    <div class="alt-name">Bedrock Managed Agents</div>
    <div class="alt-reason">No-code, fully-managed alternative in us-east-1. Less model
    flexibility and no code export — AgentCore recommended for portability and control.</div>
  </div>
  {{ END IF }}
</div>
{{ END IF }}

<!-- SERVICES DETAIL -->
<p class="section-title">AgentCore Services</p>
<div class="services-grid">
{{ FOR EACH svc IN SERVICES }}
<div class="service-card {{ 'addon-card' IF svc IS NOT always-on }}">
  <div class="svc-name">{{ SERVICE_DISPLAY_NAME(svc) }}</div>
  <span class="svc-badge {{ 'badge-free' IF svc IS always-on ELSE 'badge-addon' }}">
    {{ 'Always-on · Free' IF svc IS always-on ELSE 'Enabled' }}
  </span>
  <div class="svc-desc">{{ SERVICE_DESCRIPTION(svc) }}</div>
</div>
{{ END FOR }}
</div>

<!-- MODEL (recommendation.md §9) -->
<p class="section-title">Bedrock model</p>
<div class="card">
  <div style="font-size:16px;font-weight:700;color:#1a1a2e;">{{ MODEL_DISPLAY }}</div>
  {{ IF MODEL_REASONING }}
  <p style="font-size:13px;color:#6b7280;margin-top:4px;">{{ MODEL_REASONING }}</p>
  {{ END IF }}
  {{ IF MODEL_ALTERNATES non-empty }}
  <div class="chip-row" style="margin-top:12px;">
    {{ FOR EACH alt IN MODEL_ALTERNATES }}
    <span class="chip"><strong>Alternate</strong> {{ alt }}</span>
    {{ END FOR }}
  </div>
  {{ END IF }}
</div>

<!-- COST (only if estimate.json exists) -->
{{ IF COST_BAND }}
<p class="section-title">Cost Estimate</p>
<div class="cost-card">
  <div class="cost-band">${{ COST_BAND }}<span style="font-size:16px;font-weight:400;color:#6b7280;">/month</span></div>
  <div class="cost-label">Order-of-magnitude estimate — not a quote</div>
  {{ IF COST_ASSUMPTIONS }}
  <ul class="assumption-list">
  {{ FOR EACH a IN COST_ASSUMPTIONS }}
    <li>{{ a }}</li>
  {{ END FOR }}
  </ul>
  {{ END IF }}
  <div class="cost-note">~90% of cost is model tokens. AgentCore compute charges only for
  active CPU time — $0 during model I/O wait. Detailed TCO analysis is available in the
  migration plan.</div>
</div>
{{ END IF }}

<!-- NEXT STEPS (recommendation.md §11 — only if NEXT_STEPS non-empty) -->
{{ IF NEXT_STEPS non-empty }}
<p class="section-title">Next steps</p>
<div class="card">
  <div class="timeline">
    {{ FOR EACH (index, step) IN NEXT_STEPS }}
    <div class="tstep">
      <div class="tnum">{{ index }}</div>
      <div>
        <div class="tstep-title">{{ step.title }}</div>
        <div class="tstep-body">{{ step.body }}
          {{ IF step.command }} <code>{{ step.command }}</code>{{ END IF }}</div>
      </div>
    </div>
    {{ END FOR }}
  </div>
</div>
{{ END IF }}

<!-- ARTIFACTS -->
<!-- The report HTML sits inside $RUN_DIR, so artifact links are RELATIVE to it
     (drop the $RUN_DIR/ prefix). The download attribute makes the browser save the
     file instead of navigating to it. Scaffold is a directory → link the folder (no
     download attr; browsers can't download a dir, the link just opens it). -->
<p class="section-title">Artifacts</p>
<div class="card">
  <div class="artifact-row">
    <span>📄</span>
    <a class="dl-link" href="recommendation.md" download>recommendation.md</a>
    <span>Full recommendation document — the authoritative source of this report.</span>
  </div>
  <div class="artifact-row">
    <span>📐</span>
    <a class="dl-link" href="diagram.md" download>diagram.md</a>
    <span>Architecture diagram (Mermaid + ASCII fallback).</span>
  </div>
  {{ IF SCAFFOLD_EXISTS }}
  <!-- List each file in $RUN_DIR/scaffold/ as its own row (browsers cannot download a
       whole directory, so link each file individually):
       <div class="artifact-row"><span>🗂</span>
         <a class="dl-link" href="scaffold/FILENAME" download>scaffold/FILENAME</a>
         <span>one-line purpose of the file</span></div> -->
  {{ FOR EACH file IN scaffold/ }}
  <div class="artifact-row">
    <span>🗂</span>
    <a class="dl-link" href="scaffold/{{ file }}" download>scaffold/{{ file }}</a>
    <span>{{ one-line purpose of the file }}</span>
  </div>
  {{ END FOR }}
  {{ END IF }}
</div>

<!-- FOOTER -->
<div class="report-footer">
  {{ VOLATILE_FACTS_TEXT from recommendation.md Section 12 freshness footer }}
  &nbsp;·&nbsp; This report is a draft for review.
</div>

</div><!-- .page -->

<script>
mermaid.initialize({ startOnLoad: true, theme: 'neutral',
  themeVariables: { primaryColor: '#FF9900', primaryTextColor: '#1a1a2e',
                    primaryBorderColor: '#FF9900', lineColor: '#6b7280' } });
// Fallback: if Mermaid fails to render, show ASCII
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(function() {
    var diagrams = document.querySelectorAll('.mermaid');
    diagrams.forEach(function(el) {
      if (!el.querySelector('svg')) {
        var ascii = document.getElementById('ascii-fallback');
        if (ascii) ascii.style.display = 'block';
      }
    });
  }, 2000);
});
</script>
</body>
</html>
```

**CSS/HTML cross-check (do this before writing the file):** every class used in the
template HTML must be defined — either by the shell block or by the content CSS above —
and every content-CSS rule must have HTML that uses it. No orphans in either direction.
In particular, the old `.hero`/`.hero-main`/`.hero-services`, `.service-tag*`,
`.scores-list`, `.steps-card`/`.step-item`/`.step-num`/`.step-text`, and the local
`.report-footer` rules are GONE — the shell's `.hero-panel`, `.kpi-row`, `.card`,
`.timeline`, and `.report-footer` replace them. Do not re-add them.

## Step R3 — Open in browser

After writing the file, open it immediately:

```bash
open "$RUN_DIR/recommendation-report.html"
```

On Linux: `xdg-open "$RUN_DIR/recommendation-report.html"`

If the command fails (no GUI environment), output the path:

```
Recommendation report ready — open in your browser:
file://{{ RUN_DIR }}/recommendation-report.html
```

## Step R4 — Report completion

Output to the parent `generate.md`:

```
Recommendation report written to {{ RUN_DIR }}/recommendation-report.html
```

Do NOT update `.phase-status.json` — the parent `generate.md` handles phase completion.
