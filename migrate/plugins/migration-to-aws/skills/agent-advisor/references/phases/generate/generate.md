---
_phase: generate
_title: "Generate — Recommendation Doc + Scaffolding"
_requires_phase: estimate
_input:
  - design.json
  - confirm.json
_fragments:
  - _id: generate-report
    _trigger: { _always: true }
    _file: phases/generate/generate-report.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - diagram.md
  - recommendation.md
  - mini-brief.md
  - recommendation-report.html
_advances_to: migration-plan
_preconditions:
  - _check_file_exists: design.json
    _on_failure: _unrecoverable
  - _validate_json: design.json
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [diagram.md, recommendation.md, mini-brief.md, recommendation-report.html]
    _on_failure: _halt_and_inform
  - _assert: "recommendation.md fills all 12 sections (business summary first, technical detail after) with the freshness footer; mini-brief.md carries the recommendation, top-3 signals, eliminated, model, and any io_wait/fedramp/region/cris notes set in design.json; recommendation-report.html was generated (Step 5 is not optional)"
    _on_failure: _halt_and_inform
---

# Phase: Generate — Recommendation Doc + Scaffolding

## Step 1 — Read inputs

Read `$RUN_DIR/design.json`. Read `$RUN_DIR/estimate.json` **if it exists** (Build paths only —
for `migrate`, Estimate is skipped and there is no estimate.json; that's expected). Load the
winning runtime's service card and
`${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/model-selection.md`.

## Step 2 — Build the architecture diagram

Load `references/diagram/build-diagram.md` and follow it to produce `$RUN_DIR/diagram.md`
(Mermaid + ASCII), then embed it into Section 4 of the recommendation doc.

## Step 3 — Fill the recommendation document

Load `references/output-templates/recommendation-doc.md`. Fill ALL 12 sections. Business
summary first, technical detail after (single layered doc — do not fork by audience). Write to
`$RUN_DIR/recommendation.md`. Append the freshness footer.

For `migrate`: also fill Section 9 (Bedrock model) with the **coarse family mapping**
(e.g. "GPT-4o → Claude Sonnet 4.6 family") and a note that detailed pricing/TCO come from the
migration plugins — no dollar figures. Section 10 (cost magnitude) states "Detailed cost and TCO
are produced by the migration plugins" instead of a band (Estimate was skipped).

## Step 4 — Lightweight scaffolding (Build paths only)

**Skip this step entirely for `migrate`** (execution artifacts belong to the downstream plugins).
For Build paths:

- AgentCore + Harness → write a minimal `harness.json` skeleton with the model id from
  model_recommendation and the selected services.
- AgentCore + Framework / other runtimes → write a minimal framework starter note (entrypoint
  contract: `/invocations` POST + `/ping` GET for AgentCore) + the model id.
  Write scaffolding under `$RUN_DIR/scaffold/`. Keep it minimal — heavy IaC hands off.

## Step 4.5 — Write the mini-brief to `$RUN_DIR/mini-brief.md` (delivered by the Step 5.5 checkpoint)

Compose the **mini-brief** — it is the deliverable of the whole advisor flow — and WRITE IT
TO `$RUN_DIR/mini-brief.md` (a file, not just chat text; Step 5.5 re-reads it):

- Recommendation (runtime + deployment model), Why (top 3 signals), Eliminated, Model, and a
  pointer to `$RUN_DIR/recommendation.md`.
- Any `warnings` from the scoring result (e.g. 5 TPS).
- If `design.json` has `io_wait_tco_note == true`: the I/O-wait TCO point (AgentCore bills $0
  during model/human waits — a cost edge for spiky/HITL traffic; no dollar figures).
- When set: `fedramp_note` (FedRAMP WIP — verify + GovCloud fallback),
  `region_availability_note` (runtime not in the user's region — nearest supported), and
  `cris_note` (geo-CRIS vs global-CRIS data-residency choice for EU/GDPR).

## Step 5 — Generate HTML recommendation report

**You MUST produce `$RUN_DIR/recommendation-report.html` — it is a required output of
this phase, not optional.** Load `references/phases/generate/generate-report.md` and follow it to
write the file, then open it in the user's browser.

Scope of "non-blocking": only the **browser-opening** and a genuine build _failure_ are
non-blocking — NOT the generation itself. So:

- If the `open`/`xdg-open` command fails (no GUI): print
  `Report ready — open: file://$RUN_DIR/recommendation-report.html` and continue.
- If writing the HTML genuinely errors: log the specific warning and continue.
- Never SKIP this step to reach Step 5.5 faster. Step 5.5 checks that the file exists
  (below) — if it is missing, you skipped Step 5 and must come back and do it.

## Step 5.5 — Recommendation review checkpoint (BLOCKING — the user must see and confirm the recommendation before any gate)

**Precondition check (do this FIRST, before composing the checkpoint):** confirm
`$RUN_DIR/recommendation-report.html` exists on disk. If it does NOT, Step 5 was skipped —
go back and run Step 5 now (generate the report + open it) before proceeding. Do not
present this checkpoint without the report having been generated.

This is its own turn, separate from every gate. Send ONE message whose body is the **full
mini-brief pasted from `$RUN_DIR/mini-brief.md`**, followed in the SAME message by an
AskUserQuestion:

> [contents of $RUN_DIR/mini-brief.md]
>
> "This is the recommendation. Take a moment to review it (full detail in
> `$RUN_DIR/recommendation.md`) — does it look right before we talk about next steps?"
>
> - **Looks good — continue** → record the confirmation (below) and proceed to Step 6.
> - **Explain more first** → answer the user's questions on the recommendation (from
>   recommendation.md / design.json — no new scoring), then re-ask this checkpoint.
> - **Something's off — revisit an answer** → identify which clarify answer changed, update
>   `answers.json`, re-run scoring, and redo Design → Generate. Do NOT proceed on a
>   recommendation the user disputes.

On "Looks good — continue": read-merge-write `.phase-status.json` and set top-level
`"recommendation_reviewed": true`.

**Mechanical gate rule:** Steps 6 and 7 MUST NOT ask Gate 1 or Gate 2 unless
`.phase-status.json` has `recommendation_reviewed == true`. If it is absent, you skipped
this checkpoint — go back and run it. This ordering is not optional and does not collapse
into the gate question: the user confirms they have SEEN the recommendation first, and only
then is asked what to do next. (Resume-safe: if the session breaks after confirmation, the
flag survives and the checkpoint is not re-asked.)

Because the checkpoint delivered the brief, the gates below only need a one-line recap
(runtime + deployment model + model), not the full brief.

## Step 6 — Migration-plan gate (Gate 1)

**Precondition:** `.phase-status.json.recommendation_reviewed == true` (set by Step 5.5).
Absent → run Step 5.5 first; never ask this gate without it.

**Applicability** (skip this step when none applies — mark `phases.migration_plan = "not_applicable"`):

- entry_point == `migrate` → always offer.
- entry_point == `build_deploy` → offer ONLY if Discover ran and
  `$RUN_DIR/context-signals.json.model_provider` ∈ {openai, anthropic, google-genai} —
  i.e. something real exists to migrate. Key absent, `none`, or `bedrock` → not applicable.
- entry_point == `build_scratch` → never (nothing existing to migrate).

For `migrate`, FIRST load `references/handoff/handoff-migration.md` and follow its Step 1 to
write `$RUN_DIR/handoff-summary.md` (it is both the human-readable handoff artifact and the
Stage 2 injection payload source). Then ask **Gate 1** — a one-line recap (runtime +
deployment model + model; the full brief was confirmed at Step 5.5), followed by the
AskUserQuestion in the same message:

> Recommended: `<runtime>` + `<deployment model>`, model `<model>` (details: recommendation.md).
>
> "Do you want a complete migration plan for this workload? I'll generate
> it here using this plugin's migration engine, reusing the decisions we already made
> (runtime, deployment model, memory). It will analyze your code and may ask a few extra
> questions."
>
> - **Yes — generate the migration plan** → set `phases.migration_plan = "pending"`;
>   after Step 7 the state machine loads `references/phases/migration-plan/migration-plan.md`.
> - **No** → set `phases.migration_plan = "skipped"`. For `migrate`, keep the classic
>   pointer: follow handoff-migration.md Steps 2–4 (direct the user to
>   `/migration-to-aws:llm-to-bedrock` or `gcp-to-aws` with `handoff-summary.md`).

## Step 7 — Write state and branch

Set `phases.generate` = completed (read-merge-write). Then branch:

1. **Gate 1 answered Yes** → next phase is `migration_plan`: load
   `references/phases/migration-plan/migration-plan.md`. Gate 2 is offered from that phase's Step 6.
2. **Otherwise, if** entry_point ∈ {`build_scratch`, `build_deploy`}: ask **Gate 2**
   for the winning runtime — any of agentcore / ecs / eks / lambda / lambda_microvms
   (verdict or co_recommend `chosen_runtime`; same precondition:
   `recommendation_reviewed == true`) — a one-line recap (runtime + deployment model +
   model), followed by the AskUserQuestion in the same message:

   > Recommended: `<runtime>` + `<deployment model>`, model `<model>` (details: recommendation.md).
   >
   > "Do you want a deployable proof-of-concept for this recommendation on `<runtime>`?
   > I'll generate the agent code, deployment plan, and scripts."
   >
   > - **Yes** → set `phases.poc = "in_progress"` (persist the confirmation), then load
   >   `references/phases/poc/poc.md` (it asks which POC mode first).
   > - **No** → set `phases.poc = "skipped"`; the advisor flow is complete.

3. **Otherwise** (migrate without a plan): the Step 5.5 checkpoint already delivered the
   brief; close with a short completion message pointing at `recommendation.md` — the
   advisor flow is complete.

Note: for `migrate` WITH a completed migration plan, Gate 2 is asked at the end of
migration-plan.md (its Step 6), using the same wording as point 2 above.
