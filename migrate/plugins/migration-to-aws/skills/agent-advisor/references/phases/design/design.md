---
_phase: design
_title: "Design"
_requires_phase: confirm
_input:
  - scoring-result.json
  - confirm.json
_assemble:
  _file: phases/design/design-assemble.md
_produces:
  - design.json
_advances_to: estimate
_preconditions:
  - _check_phase_completed: confirm
    _on_failure: _halt_and_inform
  - _check_file_exists: [scoring-result.json, confirm.json]
    _on_failure: _unrecoverable
  - _validate_json: [scoring-result.json, confirm.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: design.json
    _on_failure: _halt_and_inform
  - _validate_json: design.json
    _on_failure: _halt_and_inform
  - _assert: "design.json has verdict, chosen_runtime, deployment_model, agentcore_services, model_recommendation, and carries scores + eliminated (and blocking_constraints when present) copied verbatim from scoring-result.json; handoff_required is true iff the winning runtime is ecs or eks"
    _on_failure: _halt_and_inform
---

# Phase: Design

Assembles the recommendation from the scoring result + Confirm choices + service cards.

## Step 1 — Read inputs

Read `$RUN_DIR/scoring-result.json` and `$RUN_DIR/confirm.json`. The winning runtime is
`confirm.chosen_runtime` if present (co_recommend pick), else `scoring-result.verdict`. Prefer
`confirm.deployment_model` and `confirm.agentcore_services` over the scoring-result defaults (Confirm
is the user-confirmed set).

## Step 2 — Load the winning runtime's service card

Load ALL THREE files (each is required; do not skip any — Step 4's lock-in check depends on
`managed-alternatives.md` even when no lock-in ends up applying):

1. `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/<verdict>.md` (use
   `lambda-microvms.md` for lambda_microvms; for co_recommend, load both cards)
2. `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/model-selection.md`
3. `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/managed-alternatives.md`

## Step 3 — Refresh volatile facts

Load `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/freshness.md` and follow its procedure:
read the winning profile's `volatile_facts`, try awsknowledge MCP for each, fall back to cached
values on failure. Record which succeeded vs fell back (for the freshness footer).

## Step 4 — Provider lock-in check

Determine the managed alternative from the source/current model provider: Claude-committed →
`claude_managed`; OpenAI-committed → `bedrock_managed`; multi-provider or undecided → `none`.
If a managed alternative applies, surface it **as awareness only** (per `managed-alternatives.md`)
with its tradeoffs — do NOT present it as the recommendation. Otherwise note AgentCore supports
all models.

## Step 4b — I/O-wait TCO differentiator (surface proactively)

Most customers don't know AgentCore Runtime (and Harness) bill **$0 during I/O wait** (active
CPU only). Surface this as a TCO advantage — WITHOUT adding a question — when it actually
matters: if `traffic_pattern` is `bursty` or `idle`, OR `session_state` is `hitl`, AND AgentCore
is viable (winning runtime is `agentcore`, or it is in a `co_recommend` set, or it was not
eliminated). Set `io_wait_tco_note = true` in design.json and include a short note for the doc,
e.g.: "Your traffic is spiky / has human-in-the-loop waits — on AgentCore you pay nothing while
the agent waits on the model or a human (active-CPU billing only), which is a real TCO edge vs
always-on compute. Exact numbers come from the migration/pricing plugins." No dollar figures
here. If AgentCore is not viable, omit the note.

## Step 4c — FedRAMP status (WIP, not a hard block)

If the user's `compliance` includes `fedramp`: AgentCore's FedRAMP authorization is **in progress
(WIP)** — do NOT hard-eliminate AgentCore for it. Verify the current status per `freshness.md`
(the `fedramp` volatile fact, via awsknowledge MCP). Then surface an honest note: "AgentCore's
FedRAMP authorization is in progress — verify the current status before committing. If you need
FedRAMP-authorized compute **today**, GovCloud on ECS/EKS is the safe fallback." Record
`fedramp_note = true` in design.json when this fires. (HIPAA/SOC/PCI/etc. are unaffected —
AgentCore is eligible for those.)

## Step 4d — Region gating (availability + CRIS/GDPR)

Read `region` from answers. Region does NOT change the verdict — it gates two things:

1. **Availability:** if the winning runtime is `agentcore` (or the chosen deployment model is
   Harness), verify it's available in the user's region via the awsknowledge MCP (per
   `freshness.md`; the profile's `regions` volatile fact). If unavailable, surface a note with the
   nearest supported region and — if the gap is blocking — the container fallback. Do NOT silently
   recommend a runtime the user's region can't run. Record `region_availability_note` when it fires.
2. **CRIS / data residency:** if `region` is `multi`/`global` OR the user is in the EU OR
   `compliance` includes `gdpr`, surface the CRIS choice: **geo-CRIS keeps inference within the
   region (data-residency-safe)** vs **global-CRIS may route cross-region (a GDPR risk)**. Present
   it as a compliance decision, not a silent default. Record `cris_note = true`. Exact CRIS/region
   configuration is validated downstream in the migration flow — keep this directional.

## Step 5 — Assemble design.json

Carry the scoring facts forward so Generate has a deterministic source for "Alternatives
considered" and the "Eliminated" line (Generate reads design.json, not scoring-result.json):

```json
{
  "verdict": "...", "chosen_runtime": "...", "deployment_model": "...",
  "agentcore_services": [...], "model_recommendation": {...}, "warnings": [...],
  "scores": {...}, "eliminated": {...}, "blocking_constraints": [...],
  "volatile_facts": {"session_cap": {"value": "8h", "source": "mcp|cached"}},
  "managed_alternative": "claude_managed | bedrock_managed | none",
  "io_wait_tco_note": true|false,
  "fedramp_note": true|false,
  "region_availability_note": "... | null",
  "cris_note": true|false,
  "handoff_required": true|false
}
```

Copy `scores`, `eliminated`, and (if present) `blocking_constraints` verbatim from
scoring-result.json. Set `handoff_required` = true when the winning runtime is **ecs or eks**
(heavy-infra compute handed off downstream). Standard Lambda, Lambda MicroVMs, and AgentCore are
self-contained — `handoff_required` = false for them. (For migrate, Generate ends with the migration-plan gate — the user chooses between an
in-skill migration plan and the classic downstream handoff; that's an entry-point behavior
in Step 6, independent of `handoff_required`.)

## Step 6 — Branch on entry point

- entry_point == migrate → set `phases.design` = completed, set `phases.estimate` = "skipped",
  and continue to **Generate**. The user gets the same recommendation doc + architecture diagram
  as Build paths; Generate then offers the migration-plan gate (Gate 1) at the end — in-skill plan or classic
  handoff. Do NOT run Estimate (precise
  cost belongs downstream).
- otherwise → set `phases.design` = completed and continue to Estimate.
