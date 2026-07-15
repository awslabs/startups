---
_phase: temporal-worker
_title: "Temporal Worker Migration (branch)"
_kind: checkpoint
_requires_phase: intake
_trigger: { _when: "entry_point == temporal_worker (Intake trigger confirmation, or Discover detected Temporal and the user confirmed) AND phases.temporal_worker != completed" }
_input: workspace
_assemble:
  _file: phases/temporal-worker/temporal-worker-assemble.md
_produces:
  - temporal-design.json
  - temporal-migration-plan.md
  - temporal-migration-report.html
_preconditions:
  - _check_phase_completed: intake
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: temporal-design.json
    _on_failure: _halt_and_inform
  - _validate_json: temporal-design.json
    _on_failure: _halt_and_inform
  - _check_file_exists: [temporal-migration-plan.md, temporal-migration-report.html]
    _on_failure: _halt_and_inform
  - _assert: "temporal-design.json records the Way (server), the per-task-queue Tier 1 choice + the rule that fired, and the per-Activity-class Tier 2 targets (with the scoring-result reference for agent-session classes); Workflow orchestration code is never rewritten (no Step Functions / primitives translation)"
    _on_failure: _halt_and_inform
  - _assert: "temporal-migration-plan.md has the 7 sections from Step 5 (architecture diagram, worker deployment plan, execution-tier plan, Cloud commercials selected by current server state, magnitude-only cost table, the selected cutover runbook WITH its preconditions, freshness footer); Serverless Workers is labeled PRE-RELEASE regardless of any docs 'Available' label"
    _on_failure: _halt_and_inform
  - _assert: "temporal-migration-report.html contains an Artifacts section (Step 5 section 8) linking temporal-migration-plan.md, temporal-design.json, and temporal-inventory.json via RELATIVE hrefs — the report is how users discover the run's files"
    _on_failure: _halt_and_inform
---

# Phase: Temporal Worker Migration (branch)

Reached when `entry_point == temporal_worker` (Intake trigger confirmation, or
Discover detected Temporal and the user confirmed). The user runs Temporal and
wants the Workers (and the work they execute) on AWS. **Workflow orchestration
code is never rewritten** — no Step Functions / AgentCore-primitives translation.
This is a self-contained branch: it does NOT pass through Clarify / Confirm /
Design / Estimate / Generate, so the phase gate never applies to it.

Decision content (Tier 1/Tier 2/Way tables, runbooks, commercials) lives in
`${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/temporal.md`
— load it now and treat it as the single source of truth. Do not restate its
rules from memory.

## Step 0 — Run directory

Reuse the Intake `$RUN_DIR` — it already exists on both entry paths. Only if the
branch is somehow entered without one, create it exactly as add-capabilities
Step 0 does (`<cwd>/.agent-advisor/<MMDD-HHMM>/` + `.gitignore` containing `*`).

## Step 1 — Input fork

- **Code path given** (from Intake's open-context prompt, or ask now: "Where's
  your Temporal worker code? A directory path lets me inventory workflows and
  activities.") → run the scan (Step 1a).
- **No code** → rebuild the profile via Q&A in Step 2 instead. ALL outputs must
  then carry the label "based on interview, not code-verified".

## Step 1a — Code scan (read-only)

Produce `$RUN_DIR/temporal-inventory.json` with:

**1. Workflow/Activity inventory.** SDK patterns differ by language — every item
carries a confidence label (`high` / `medium` / `low`):

| Language   | Pattern                                                                                                                     | Confidence |
| ---------- | --------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Python     | `@workflow.defn` / `@activity.defn` decorators                                                                              | high       |
| Java       | `@WorkflowMethod` / `@ActivityMethod` annotations                                                                           | high       |
| Go         | plain functions registered via `worker.RegisterWorkflow` / `RegisterActivity`; follow `workflow.ExecuteActivity` call sites | medium     |
| TypeScript | `proxyActivities<T>()` + `Worker.create({workflowsPath})` — workflows live in a separate bundle; scan both sides            | medium     |

Anything you cannot classify → confidence `low` + flag "needs manual
confirmation" (surfaces in Step 2).

**2. Task queues and namespaces.** There may be SEVERAL of each. Map every
workflow/activity to its task queue — Tier 1 and the runbooks are applied **per
task queue**, not once globally.

**3. Activity classification** (per decision-refs/temporal.md Tier 2:
light-io / agent-session / short-tool / heavy) → each entry: name, class,
confidence, task queue. Write `$RUN_DIR/activities-classified.json`.

**4. LLM call sites + provider** (openai / anthropic / google / bedrock).

**5. Orchestration complexity signals**: signal/timer/child-workflow counts
(context for the plan's scope note, and evidence if the user asks why the
orchestration layer stays on Temporal).

**6. Server connection type**: Cloud endpoint (`*.tmprl.cloud`) vs self-hosted
address.

**7. Temporal AI integrations** (`temporalio.contrib.openai_agents`, Google
ADK): mark "deeply coupled" — a Bedrock rewrite must respect the shim.

Tell the user what was detected, with confidence labels, before moving on
(same determinism-boundary stance as discover.md: detections are best-effort
LLM interpretation; the user corrects them in Step 2).

## Step 2 — Clarify (adaptive — skip anything already detected)

Ask only what the scan didn't answer. **Word every question for the `audience`
in `.phase-status.json`** — same convention as the main flow's
clarify-technical.md / clarify-business.md split. For `business`, translate to
plain terms and lean harder on the code scan (prefer detecting over asking);
never use "Worker", "task queue", "Activity", or "replay" in a question without
a one-line plain-language gloss. Business phrasings per topic below in
parentheses.

Full checklist:

- Server location (Temporal Cloud / self-hosted where) and worker location
  (business: "Is the Temporal service something your team runs on its own
  machines, or do you pay Temporal for their hosted cloud version?")
- In-flight long-running workflows? Max remaining duration? (drives runbook 2
  warnings) (business: "Is there work currently mid-flight that takes days or
  weeks to finish — e.g. an approval that waits on a person?")
- Traffic shape: steady / intermittent / spiky (business: "Is usage steady all
  day, or spiky with quiet gaps?")
- Longest Activity duration (drives Serverless Workers 15-min rule)
  (business: "What's the longest single task — seconds, minutes, or hours?")
- Team operates K8s today? (business: "Does your team already run
  Kubernetes? If you're not sure, the answer is no.")
- Hard compliance requirement that orchestration state stay self-hosted?
  (drives Way 2 — but surface External Payload Storage first, per
  decision-refs/temporal.md) (business: "Any rule — legal or contractual —
  that says this system's records must stay on servers you control?")
- (AI workloads) LLM provider + willingness to move to Bedrock (business:
  "Your system calls `<provider>` today. Open to switching the AI to Amazon's
  Bedrock service as part of this?")
- **Activity-classification confirmation** — present the classified inventory:
  technical: "Detected 12 activities: 8 light-IO, 3 agent-session, 1 heavy —
  correct?"; business: describe by what the steps DO ("we found 12 kinds of
  tasks: 8 quick lookups, 3 longer AI investigations, 1 nightly batch job —
  sound right?"). Low-confidence items MUST be individually confirmed here.

## Step 3 — Decide (two tiers) → `$RUN_DIR/temporal-design.json`

Apply decision-refs/temporal.md in order:

1. **Way 1 vs Way 2** (server) — decision table.
2. **Tier 1** (polling tier) — eliminations, then ordered rules, per task queue.
   Rules 1 (K8s tension) and 4 (mixed-duration split) are user-choice gates:
   AskUserQuestion, don't auto-pick. When the user declines rule 4's split,
   record the outcome as "rule 4 offered, user chose single ECS service" —
   not as rule 5.
3. **Tier 2** (execution tier) — per Activity class. For **agent-session**
   Activities, run the main flow's scoring engine:

   Build `$RUN_DIR/temporal/answers.json` via this adapter (unlisted
   dimensions stay `"unknown"` — the engine's DEFAULTS apply):

   | scoring.py dimension                                    | Fill from Temporal context                                                                                                                                                                                                                                                                                                                  |
   | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `session_duration`                                      | max expected runtime of this Activity (`under_15min` / `15min_to_8hr` / `over_8hr`)                                                                                                                                                                                                                                                         |
   | `traffic_pattern`                                       | Activity start pattern from workflow schedule/volume (`bursty` / `steady` / `idle`)                                                                                                                                                                                                                                                         |
   | `launch_concurrency`                                    | expected concurrent Activity starts (`high` / `moderate` / `low`)                                                                                                                                                                                                                                                                           |
   | `session_state`                                         | agent loop holds conversation/tool state → `stateful`; waits for human signal → `hitl`                                                                                                                                                                                                                                                      |
   | `memory_needs`                                          | memory scoped to one Activity run → `session_only`; persists across runs → `cross_session`. A retried/re-dispatched agent Activity (e.g. re-draft after a rejection signal) counts as a NEW run — stay `session_only` unless the business logic needs memory to carry across executions (shared investigation context, cross-ticket recall) |
   | `isolation`                                             | per-session sandbox needed (untrusted code/tools) → `required`                                                                                                                                                                                                                                                                              |
   | `framework`                                             | detected agent framework in the Activity body (`strands` / `langgraph` / `crewai` / `custom` / `none`)                                                                                                                                                                                                                                      |
   | `platform_fit`                                          | caller is an in-VPC Worker, not a user-facing endpoint → team's existing AWS fit if stated (`ecs` / `eks`), else `none`                                                                                                                                                                                                                     |
   | `existing_cluster`                                      | from Tier 1 answer (team's K8s/ECS reality)                                                                                                                                                                                                                                                                                                 |
   | `ops_preference`, `multi_agent`, `compute_tier`, others | ask in Step 2 only if load-bearing; otherwise `unknown`                                                                                                                                                                                                                                                                                     |

   Then run scoring exactly as the main flow does (clarify.md Step 5), pointed
   at the branch's own subdirectory so nothing in `$RUN_DIR` is clobbered:

   ```bash
   mkdir -p $RUN_DIR/temporal
   uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts python ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts/scoring.py $RUN_DIR/temporal/answers.json
   ```

   This writes `$RUN_DIR/temporal/scoring-result.json` (the engine writes
   `scoring-result.json` next to its input) and prints `RESULT=ok
   VERDICT=<verdict>`. If it errors, show the error and stop — do not
   hand-score. The winner is the execution-tier recommendation for that
   Activity class (typical: AgentCore Runtime for ≤8h sessions — DAF pattern).
   On `co_recommend` (tie), use the main flow's framing: present both with
   "choose A if X / B if Y" contrasts drawn from each runtime's service card
   (AskUserQuestion), and carry the chosen runtime AND the contrast into the
   plan's execution-tier section — a reader of the plan must see why the
   near-tie broke the way it did.

Write `temporal-design.json`: way, per-task-queue Tier 1 choice + rule that
fired, per-Activity-class Tier 2 targets, scoring result reference (if run),
runbook selection.

## Step 4 — Freshness check

Load `references/decision-refs/freshness.md` and run its Temporal section.

**Verification channel for Temporal feature statuses (auth-gated MCP → WebFetch
fallback):** freshness.md's Temporal section names the Temporal Knowledge Base
MCP (`temporal-docs`, which ships in this plugin's `.mcp.json`) as the preferred
source, and defines the auth-gate procedure — follow it exactly. In short:
check whether `temporal-docs` is authenticated this session; if authenticated,
query it first; if registered-but-not-authenticated, **STOP and ask via
AskUserQuestion** whether to authenticate (per freshness.md), and if the user
says yes, direct them to `/mcp` and **wait** for them to finish before
continuing. Only if the user declines → WebFetch the docs.temporal.io page. Ask
at most once per run. Pausing here is safe: Step 4 is a read-only freshness
check that resumes cleanly. (The Marketplace listing fact stays WebFetch-only;
the KB MCP does not cover it.)

Non-negotiable regardless of channel: **Serverless Workers is PRE-RELEASE** —
docs (or an MCP answer echoing the docs label) may say "Available"; do not
trust the label, re-verify this run and label the output pre-release
regardless. Workflow Streams and External Payload Storage are Preview. The
anti-fabrication rule applies: only claim verified (whether via MCP or WebFetch)
for calls actually made and results observed this run.

## Step 5 — Output

Write `$RUN_DIR/temporal-migration-plan.md`, then render
`$RUN_DIR/temporal-migration-report.html`. For the visual chrome, do NOT
re-improvise CSS — reuse the shared single-source shell so this report matches
the recommendation report exactly:

- Load `references/report-shell.md` and inline its CSS block into the report's
  `<style>` (dark `.site-header`, `.section-title`, `.banner*`, base
  `table`/`th`/`td`, `.page` layout, `.two-col`) plus its SRI-pinned
  mermaid@10.9.3 script tag in `<head>`.
- Load `references/report-help-banner.md` for the top "Need help?" banner (its
  CSS into `<style>`, its HTML at the top of `.page` with `{{ HELP_URL }}`
  substituted).
- The shell also provides `.hero-panel`, `.kpi-row`, and `.timeline`: this
  report's headline uses the hero panel (verdict = the selected Way, with a
  "Workers to AWS" scope line) followed by a KPI row (task queues count,
  Activity classes count, Temporal Cloud actions magnitude), and the cutover
  runbook renders with the shared `.timeline`.
- Then add this report's OWN content CSS after the shell block for any
  temporal-specific sections (e.g. a callout box for the hygiene reminders or a
  card wrapper) — the tier tables render with the shared `table` styles and the
  current→target diagram renders in a `.mermaid` block. Keep temporal-specific
  rules here; never copy the shared chrome rules in — they live only in the
  shell.

Sections (content unchanged — only the chrome now comes from the shared shell):

1. **Current → target architecture diagram** — three layers: Temporal Server /
   polling tier / execution tier (mermaid; current on the left, target on the
   right).
2. **Worker deployment plan** — per task queue: Tier 1 choice + which rule
   fired + rationale.
3. **Execution-tier plan** — per Activity class (Tier 2), incl. the Temporal
   hygiene reminders for in-process Light-IO (idempotency, timeouts/retries,
   cancellation, heartbeats) and the scoring rationale for agent-session.
4. **Temporal Cloud commercials** — from decision-refs/temporal.md, selected by
   CURRENT server state: new-to-Cloud (self-hosted → Way 1) gets the full
   Marketplace subscribe flow; already-on-Cloud gets "billing unchanged +
   PrivateLink for the new workers" (never re-pitch the subscribe flow); Way 2
   gets the self-host stack (EKS + Aurora/RDS) and its ops cost framing.
5. **Cost comparison** — magnitude-level only; no human-labor dollar figures.
   Format as a TABLE, one row per cost line, NOT a prose paragraph:

   | Cost line                                                      | Magnitude                                    | Note                                                                      |
   | -------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------- |
   | Polling tier (ECS/EKS service)                                 | tens of $/mo                                 | small — sized in §2                                                       |
   | Execution tier (LLM tokens, AgentCore sessions, batch compute) | dominates                                    | same tokens as today — the migration moves them, it doesn't multiply them |
   | Temporal Cloud actions                                         | derive from the user's volume × $0.01/action | new line vs self-hosted; or unchanged if already on Cloud                 |
   | What it replaces                                               | qualitative only                             | self-hosted cluster ops burden — no dollar figure                         |

   One takeaway sentence below the table ("execution tier dominates; the
   polling tier is noise"), nothing more.
6. **Cutover runbook** — the one selected in Step 3, copied WITH its
   preconditions block (runbook 1's graceful-drain/Activity-retry preconditions
   are not optional).
7. **Freshness footer** — per freshness.md template (generation date,
   MCP-verified vs cached).
8. **Artifacts** — REPORT-ONLY section (not in the plan; the plan's 7-section
   contract above is unchanged). The report is the deliverable the user actually
   sees in the browser — without this section they never discover the other
   files. Render right before the freshness footer as a small table (shared
   `table` styles, no new CSS): one row per file this run produced, each name a
   RELATIVE link (the report sits in `$RUN_DIR`, so `href="temporal-migration-plan.md"`;
   add the `download` attribute on `.json`/`.md` links — mirror
   generate-report.md's Artifacts pattern):
   - `temporal-migration-plan.md` — the full migration plan (this report is its
     visual summary)
   - `temporal-design.json` — recorded Way/Tier 1/Tier 2 decisions and which
     rules fired
   - `temporal-inventory.json` — discovered task queues, workers, and Activity
     classes
   - any other files created under `$RUN_DIR` this run (`ls $RUN_DIR` — list
     what exists, e.g. `context-notes.md`)
   - one note line (no link): if the POC gate (Step 5.7) is accepted later, POC
     artifacts land under `temporal-poc/` with their own report.

No Step Functions comparison section — the scope note at the top already
states the orchestration layer stays on Temporal. If the user asks why, answer
in chat per decision-refs/temporal.md ("If the user asks") — do not add it to
the plan.

If the no-code fork was taken, every section carries "based on interview, not
code-verified".

After writing both files, open the report in the browser (non-blocking — a
failure must not stop the branch):

```bash
open "$RUN_DIR/temporal-migration-report.html"      # macOS
xdg-open "$RUN_DIR/temporal-migration-report.html"  # Linux
```

If it fails (no GUI), print:
`Report ready — open: file://$RUN_DIR/temporal-migration-report.html`

## Step 5.5 — Bedrock gate (only if non-Bedrock LLM calls were detected)

AskUserQuestion: "Move Activity LLM calls to Bedrock as part of this migration?"

- **Yes** → the branch does NOT execute the rewrite. Append a **"Bedrock
  migration"** section to temporal-migration-plan.md that (a) instructs running
  the `/migration-to-aws:llm-to-bedrock` skill as a follow-up, and (b) REQUIRES
  replay safety per decision-refs/temporal.md runbook 3: keep Workflow
  determinism against recorded history (Activity type/name and args at recorded
  command points — not just signatures), or isolate via Worker Versioning (GA) /
  a new task queue. If Step 1a flagged "deeply coupled" AI integrations
  (OpenAI Agents SDK / ADK shims), say the rewrite must respect the shim.
- **No** → the plan keeps a short "Later, optional: Bedrock" section with the
  same replay-safety pointer.

## Step 5.7 — Gate T: worker POC offer

Placed after Step 5.5 if it ran, otherwise directly after Step 5's output.
AskUserQuestion:

> "Want a deployable worker POC — a minimal worker on AWS (ECS Fargate) that
> connects to your Temporal server and runs one smoke workflow, so you can see
> task pickup working before the real migration?"

- **Yes** → ONE read-merge-write sets BOTH `phases.temporal_worker =
  "completed"` AND `phases.temporal_poc = "in_progress"` (atomic — this is
  what makes the confirmation resumable: if the session breaks here, the
  state machine re-enters `temporal_poc` without re-asking). Then load
  `references/phases/temporal-poc/temporal-poc.md` (it asks the POC mode first).
- **No** → set `phases.temporal_poc = "skipped"` and end the branch below.

## End of branch

Give a short in-chat summary (way, polling tier per queue, execution tiers,
selected runbook) and point the user to `$RUN_DIR/temporal-migration-plan.md`.
Match the summary to the audience: for `business`, lead with what changes for
the team (cost model, what stays the same, cutover risk in plain terms), not
service names. The plan document itself always keeps its layered structure —
business framing first, technical specifics after (same convention as the main
flow's recommendation doc).
Set `phases.temporal_worker = "completed"` in `.phase-status.json`
(read-merge-write; state → `complete` when temporal_poc is skipped/completed).
No runtime scoring of the main flow, no Estimate.
