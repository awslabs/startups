---
_phase: clarify
_title: "Clarify — Adaptive Questions"
_requires_phase: discover
_input: context-signals.json
_fragments:
  - _id: clarify-technical
    _trigger: { _when: "audience is technical" }
    _file: phases/clarify/clarify-technical.md
  - _id: clarify-business
    _trigger: { _when: "audience is business" }
    _file: phases/clarify/clarify-business.md
_assemble:
  _file: phases/clarify/clarify-assemble.md
_produces:
  - answers.json
  - scoring-result.json
_advances_to: confirm
_postconditions:
  - _check_file_exists: answers.json
    _on_failure: _halt_and_inform
  - _validate_json: answers.json
    _on_failure: _halt_and_inform
  - _check_file_exists: scoring-result.json
    _on_failure: _halt_and_inform
  - _validate_json: scoring-result.json
    _on_failure: _halt_and_inform
  - _assert: "answers.json has the nested shape {entry_point, answers:{...}} and every collected key uses a legal value from clarify.md Step 3; scoring-result.json was written by scoring.py (not hand-scored) and carries a verdict"
    _on_failure: _halt_and_inform
---

# Phase: Clarify — Adaptive Questions

Asks the core scoring questions, writes `answers.json`, runs the scoring engine.

## Step 1 — Pick the wording file by audience

- audience == technical → Load `references/phases/clarify/clarify-technical.md`
- audience == business → Load `references/phases/clarify/clarify-business.md`
  Both map onto the SAME scoring keys/values below. Only wording differs.

## Step 2 — Pre-fill from Discover and the opening description

If `$RUN_DIR/context-signals.json` exists, treat its keys as already answered. Show them as
"detected: `<value>` (say so if wrong)" and skip asking those, unless the user corrects them.
Also scan the Turn-1 open-context notes for two tone-setting signals and pre-fill them:

- "keep it cheap / minimize cost / tight budget" → `model_priority = cost`
- "don't want to manage / touch code / no-code / just run it" → `deployment_preference = harness`

## Step 3 — Ask the core questions (AskUserQuestion, batched)

**First batch (ask these up front — they set the tone for the whole recommendation):**
`model_priority` (esp. cost) and `deployment_preference` (managed no-code vs bring-your-own),
unless already pre-filled in Step 2. These two decisions steer everything downstream, so surface
them early rather than mid-flow. Then collect the remaining keys in subsequent batches.

Collect answers for these keys. Legal values are fixed (Plan 1 Data Model):

- `session_duration`: under_15min | 15min_to_8hr | over_8hr | unknown
- `traffic_pattern`: bursty | steady | idle | unknown
- `session_state`: stateless | stateful | hitl | unknown
- `isolation`: required | nice_to_have | not_needed | unknown
- `memory_needs`: cross_session | session_only | none | unknown
- `ops_preference`: minimal | moderate | full_control | unknown
- `compute_tier`: light | heavy_non_gpu | gpu | unknown
- `idle_resume`: process_level | filesystem | none | unknown
- `launch_concurrency`: high | moderate | low | unknown
- `multi_agent`: yes | no | unknown
- `deployment_preference`: harness | framework | either | unknown — do you want a no-code
  **managed** agent runtime (AgentCore Harness — declare the agent as config, AWS runs the loop),
  bring your own **framework** code (Strands/LangGraph/CrewAI/custom on the runtime), or **either**
  (let the advisor pick)? Ask this early — it captures managed-vs-framework intent up front.
  Only affects the AgentCore deployment model, not the runtime score. Default: `either`.
- `framework`: strands | langgraph | crewai | custom | none | unknown
- `existing_cluster`: eks | ecs | none | unknown
- `multi_cloud`: yes | no | unknown
- `platform_fit`: ecs | eks | lambda | none | unknown
- `compliance` (multi-select list): none | soc2 | hipaa | pci | fedramp | gdpr | ccpa.
  Note: FedRAMP does NOT auto-eliminate AgentCore — AgentCore's FedRAMP authorization is in
  progress (WIP). If the user needs FedRAMP, Design surfaces a "verify current status" note and
  the GovCloud ECS/EKS fallback, rather than hard-eliminating AgentCore.
- model keys: `model_priority` (quality|speed|cost|balanced|unknown),
  `model_features` — the ONE most critical specialized feature; drives a hard model override
  (see `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/model-selection.md`). Legal values:
  `tool_use | long_context | extended_thinking | rag | multimodal | image_generation | speech |
  embedding | none | unknown`. Ask only when priority is "specialized" or the user hints at a
  specific need (single-select — the most critical one).
  `current_model` (gpt4|gpt4o|gemini_flash|gemini_pro|claude|other|none|unknown) — migrate only.
- `region`: single | multi | global | unknown, plus (optionally) the specific region(s).
  Does NOT affect scoring — it gates two things in Design: (a) **availability** — AgentCore and
  especially Harness aren't in every region, so if the user's region doesn't support the
  recommended runtime, Design verifies via MCP and flags it; (b) **CRIS / data residency** — for
  EU users or when `compliance` includes `gdpr`, Design surfaces the geo-CRIS vs global-CRIS
  choice. Ask it; it's a compliance/feasibility gate, not a scoring input.

**Critical-question rule:** if `session_duration` is blank/unknown, **OR was only inferred by
Discover and not confirmed by the user**, ask it directly in chat before scoring — it gates hard
constraints, so an unconfirmed guess can silently eliminate runtimes. (Applies to every entry
point that reaches Clarify.)

## Step 4 — Write answers.json

```json
{"entry_point": "<from state>", "answers": { ...collected keys... }}
```

Write to `$RUN_DIR/answers.json`.

## Step 5 — Run the scoring engine

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts python ${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/scripts/scoring.py $RUN_DIR/answers.json
```

This writes `$RUN_DIR/scoring-result.json` and prints `RESULT=ok VERDICT=<verdict>`.
If the command errors, show the error and stop — do not hand-score.

## Step 6 — Write state and continue to Confirm

Set `phases.clarify` = completed (leave `phases.confirm` = pending). Do NOT jump to Design.
The state machine now routes to **Confirm** (`references/phases/confirm/confirm.md`), which
confirms the deployment model / services / co_recommend pick and writes `confirm.json` — Design and
the diagram require it.
