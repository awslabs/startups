# Phase 4: Estimate AWS Costs (Orchestrator)

**Execute ALL steps in order. Do not skip or optimize.**

## Step 0: Pricing Mode Selection

Before running any sub-estimate file, determine the pricing source.

### Step 0a: Load Pricing Cache

Read `shared/pricing-cache.md`. Check the `Last updated` date in the header:

- If <= 90 days old: **Cached prices are the primary source.** No MCP calls needed for services listed in the cache. Proceed to Step 1.
- If > 90 days old: Cache is stale. Attempt MCP (Step 0b) for fresh prices; use stale cache as fallback.

### Step 0b: MCP Availability Check (only if cache stale or service not listed)

Attempt to reach awspricing with **up to 2 retries** (3 total attempts):

1. **Attempt 1**: Call `get_pricing_service_codes()`
2. **If timeout/error**: Wait 1 second, retry (Attempt 2)
3. **If still fails**: Wait 2 seconds, retry (Attempt 3)
4. **If all 3 attempts fail**: Use cached prices with staleness warning

### Step 0c: MCP Preflight — Surface Status to User (ALWAYS run)

**Before any sub-estimate file runs**, display the pricing mode to the user so they know what to expect:

- **If cache ≤ 90 days and MCP not needed**: "Pricing source: cached (updated [date], ±5-25% accuracy). Live pricing API not required."
- **If cache > 90 days and MCP available**: "Pricing source: live API (awspricing MCP). Cache is stale ([date]) — using real-time pricing."
- **If cache > 90 days and MCP unavailable**: "⚠️ Pricing source: stale cache only (updated [date]). The awspricing MCP server is unreachable — ensure `uvx` is installed (`pip install uv` or `brew install uv`) and AWS credentials are configured. Proceeding with cached pricing; accuracy may be ±15-25% for AI models."
- **If cache ≤ 90 days but a required service is NOT in cache and MCP unavailable**: "⚠️ Some services not in pricing cache and MCP unreachable. Those services will show `pricing_source: unavailable` in the estimate."

This prevents silent failures — the user sees the pricing constraint upfront, not after 5 minutes of estimation work.

### Pricing Hierarchy

Each sub-estimate file uses this lookup order per service:

1. **`shared/pricing-cache.md`** (primary) — Cached prices (±5-25% accuracy). Set `pricing_source: "cached"`. Used first because it requires zero API calls and covers most common services.
2. **MCP API** (secondary) — Real-time pricing for services NOT in pricing-cache.md (±5-10% accuracy, more precise). Set `pricing_source: "live"`. Only called when the cache lacks the needed service or model. **Region note:** The `.mcp.json` sets `AWS_REGION=us-east-1` as the MCP server default, but each `get_pricing()` call accepts a `region` parameter that overrides it. Always pass the user's target region (from `preferences.json`) in MCP queries.
3. **Cache after MCP failure** — If MCP was attempted but failed (timeout, error), and the service IS in the cache, use the cached price. Set `pricing_source: "cached_fallback"`. This distinguishes intentional cache use from MCP failure recovery.
4. **Unavailable** — If a service is NOT in the cache AND MCP is unavailable, set `pricing_source: "unavailable"` for that service. Add the service to `services_with_missing_fallback` and display a warning to the user: "Pricing unavailable for [service] — not in cache and MCP unreachable. Exclude from totals or provide a manual estimate."

**`pricing_source` values summary:**

| Value               | Meaning                                                   |
| ------------------- | --------------------------------------------------------- |
| `"cached"`          | Found in pricing-cache.md (normal path)                   |
| `"live"`            | Retrieved from MCP API in real-time                       |
| `"cached_fallback"` | MCP was attempted but failed; fell back to cache          |
| `"unavailable"`     | Not in cache AND MCP failed; service excluded from totals |

If cache is > 90 days old and MCP is unavailable:

- Add warning: "Cached pricing data is >90 days old; accuracy may be significantly degraded"
- **Display to user**: Add visible warning with staleness notice

## Step 1: Prerequisites

1. Read `$MIGRATION_DIR/.phase-status.json`. If missing, invalid, or `phases.clarify` is not exactly `"completed"`: **STOP**. Output: "Phase 2 (Clarify) not completed or phase state is missing/invalid. Complete Clarify before Estimate."
2. Read `$MIGRATION_DIR/preferences.json`. If missing: **STOP**. Output: "Phase 2 (Clarify) not completed. Run Phase 2 first."

Check which design artifacts exist in `$MIGRATION_DIR/`:

- `aws-design.json` (infrastructure design from IaC)
- `aws-design-ai.json` (AI workload design)
- `aws-design-billing.json` (billing-only design)

If **none** of these artifacts exist: **STOP**. Output: "No design artifacts found. Run Phase 3 (Design) first."

## Step 2: Routing Rules

### Infrastructure Estimate

IF `aws-design.json` exists:

> Load `estimate-infra.md`

Produces: `estimation-infra.json`

### Billing-Only Estimate

IF `aws-design-billing.json` exists AND `aws-design.json` does **NOT** exist:

> Load `estimate-billing.md`

Produces: `estimation-billing.json`

### AI Estimate

IF `aws-design-ai.json` exists:

> Load `estimate-ai.md`

Produces: `estimation-ai.json`

### Mutual Exclusion

- **estimate-infra** and **estimate-billing** never both run (billing-only is the fallback when no IaC exists).
- **estimate-ai** runs independently of either estimate-infra or estimate-billing (no shared state). Run it after the infra/billing estimate completes.

## Phase Completion

Before marking Estimate complete, enforce route output gates (fail closed):

1. Determine which estimate routes ran:
   - Infra route: `aws-design.json` exists
   - Billing-only route: `aws-design-billing.json` exists AND `aws-design.json` does NOT exist
   - AI route: `aws-design-ai.json` exists
2. Require at least one route to be active. If none active: STOP.
3. For each active route, require its expected artifact:
   - Infra route -> `estimation-infra.json`
   - Billing-only route -> `estimation-billing.json`
   - AI route -> `estimation-ai.json`
4. If any active route is missing its expected output: STOP and output: "Estimate route [name] did not produce required artifact(s). Re-run the failed sub-estimate before completing Phase 4."

## Completion Handoff Gate (Fail Closed)

Load `shared/handoff-gates.md`. **Re-read from disk** each active estimate artifact before checking.

**Re-entry guard:** If `generation-infra.json` (or sibling generation artifacts) exists and `phases.generate` is not `"pending"`: STOP unless the user explicitly confirms re-running Estimate. Emit `GATE_FAIL | phase=estimate | field=generation-infra.json | reason=stale_downstream`.

**Infra route additional checks** (when `estimation-infra.json` exists):

- `recommendation.path` ∈ `{migrate_optimized, migrate_phased, stay}`
- `recommendation.path_label` is non-empty
- `recommendation.migrate_if` and `recommendation.stay_if` are non-empty arrays

**On any FAIL:** Emit `GATE_FAIL | phase=estimate | field=<path> | reason=missing`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user to re-run `estimate-infra.md` Part 7 (recommendation block).

**On PASS:** Emit `HANDOFF_OK | phase=estimate | artifacts=<comma-separated active estimate files>`.

### Inner workshop reprice — skip state transition

When Estimate is invoked from `workshop-refresh.md` (inner reprice): write the
estimate artifact(s), present a brief summary, then **return to the workshop
loop**. Do **not** emit `HANDOFF_OK`, do **not** update `.phase-status.json`, do
**not** offer the what-if workshop below.

### Outer Estimate — Decision gate (replaces auto-advance to Generate)

After outer-run `HANDOFF_OK`, use the Phase Status Update Protocol
(read-merge-write) — **in the same turn** as the summary:

1. Set `phases.estimate` to `"completed"`
2. Ensure `phases.workshop` exists (seed `"pending"` if missing)
3. **Do not** set `current_phase` to `"generate"` — Generate is opt-in from
   here on. Leave `current_phase` at `"estimate"` and present the Decision
   gate below.

### Post-Estimate: Decision Gate

**The decision is the product; execution artifacts are opt-in.** The verdict
(`recommendation.outcome` / `path`) already exists in the estimate artifacts —
present it and let the user choose what happens next. Never advance to
Generate without an explicit choice of option C (or an explicit later request
for Terraform/scripts).

Present (values from the active estimate artifacts; one line each):

```
Estimate complete.

### Decision pack ready

- Verdict: [outcome_label when recommendation.outcome exists; else path_label]
- AWS estimate (Balanced): $[X]/mo · Your GCP baseline: [figure with its
  baseline-quality label from estimate-infra.md Part 1 — apply the
  not-comparable rule when the sources measure different things]
- Timeline if you execute: ~[N–M] weeks ([complexity tier], from
  shared/migration-complexity.md — omit this line when no tier signal exists)
- Deferred to specialists: [BigQuery / other deferred rows, or omit line]

[A] Done for now — I have what I need to decide
[B] Explore what-ifs — reprice scenarios side by side (~1 min each): region,
    single-AZ database, EKS vs Fargate, Graviton
[C] Generate Terraform and migration scripts
```

**Data-justified scenario hint (add one line when applicable):** if a material
assumption was defaulted rather than confirmed — most commonly `availability`
(Multi-AZ, ~2x database cost) — append: "Suggestion: we assumed [assumption];
comparing a [alternative] scenario would bound that assumption before you
commit." Suggest at most one.

**Choice handling:**

- **A** → Mark `phases.workshop` → `"completed"` (declined). Then:
  1. **Render the decision pack:** load `references/shared/report-decision-core.md`
     and render it in **decision** mode — write
     `$MIGRATION_DIR/decision-report.html` and `$MIGRATION_DIR/DECISION.md`
     per that file's decision-mode rules (no appendices, no Terraform, CTA
     footer). Validate with
     `python3 "$PLUGIN_ROOT/scripts/validate-migration-report.py" "$MIGRATION_DIR/decision-report.html" --mode decision`
     (absolute paths — cwd must not be load-bearing) and fix failures before
     presenting.
  2. Set `run_mode: "decide"` and `current_phase: "complete"` in
     `.phase-status.json` (`phases.generate` **stays** `"pending"` — this
     combination means "decision complete, execution available on request";
     see `schema-phase-status.md`).
  3. Run the post-gate feedback checkpoint per `SKILL.md`. Close with:
     "Your decision report is saved at `decision-report.html` (plus a
     Slack-friendly `DECISION.md`). If you decide to migrate, say 'generate
     the Terraform and migration scripts' — everything is saved and I'll pick
     up from here."
- **B** → Load `references/phases/workshop/workshop.md`. Keep
  `current_phase: estimate`; set `phases.workshop` → `"in_progress"`. On
  workshop exit, **return to this gate** (options A and C; the workshop's
  active scenario carries into either) — do not advance to Generate directly.
- **C** → Mark `phases.workshop` → `"completed"` (declined). Set
  `run_mode: "decide_and_execute"` and `current_phase` → `"generate"`. Then
  run the post-gate feedback checkpoint per `SKILL.md` and continue to
  Generate.

For AI-only / billing-only runs (no infra inventory), present the gate without
option B and set `phases.workshop` → `"completed"`.

## Reference Files

- `shared/pricing-cache.md` — Cached AWS + source provider pricing (±5-25%, primary source)

## Scope Boundary

**This phase covers financial analysis ONLY.**

**Cost labeling rule (applies to ALL sub-estimate files):** All dollar figures presented to the user in chat summaries, report tables, and metric boxes MUST be labeled as "estimated monthly costs" or prefixed with "Est." — never present raw dollar amounts as if they are exact. This includes the Present Summary output, migration report content, and any user-facing cost references.

FORBIDDEN — Do NOT include ANY of:

- Changes to architecture mappings from the Design phase
- Execution timelines or migration schedules — **exception:** the Decision gate's one-line timeline band (`~N–M weeks`, tier from `shared/migration-complexity.md`) is allowed; full schedules, week-by-week plans, and runbooks remain Generate-only
- Terraform or IaC code generation
- Detailed migration procedures or runbooks
- Team staffing or resource allocation

**Your ONLY job: Show the financial picture of moving to AWS. Nothing else.**
