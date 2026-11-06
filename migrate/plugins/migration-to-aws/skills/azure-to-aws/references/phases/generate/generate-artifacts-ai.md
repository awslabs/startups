---
_fragment: artifacts-ai
_of_phase: generate
_contributes:
  - ai-migration/ (provider adapter, scripts, monitoring tf)
  - generation-ai.json
---

# Generate — AI Migration Artifacts

> **Loaded when `aws-design-ai.json` exists AND `run_mode` is `decide_and_execute`.** Runs under
> the `rw` worker (file-only: no skill calls, no `terraform`/`python` execution — validation stays
> main-window). Execute ALL steps in order.

The Azure port of gcp's `generate-artifacts-ai.md` + the essential migration-plan output of gcp's
`generate-ai.md`, folded into one fragment (azure keeps Generate lean — `generate-artifacts-*`
fragments, no separate plan file). Reads `aws-design-ai.json`, `estimation-ai.json` (for the
budget seed), `ai-workload-profile.json`, `preferences.json`. Missing a REQUIRED input → STOP
("Missing required artifact: `<file>`. Complete the prior phase that produces it.").

## Step 0: Determine the artifact path

Read `aws-design-ai.json → ai_architecture.bedrock_models[]` and build one artifact route per
row from `workload_id`, `call_sites[]`, `aws_model_id`, and `migration_path`. Preserve row order
and emit every matching lane; mixed Responses, Chat, and Messages repositories can use several
setups. Use `ai_architecture.code_migration.migration_path` only for a legacy single-surface
artifact. Missing per-row paths in a mixed artifact, or call sites matching zero/multiple rows,
STOP with `Unsupported or ambiguous call-site route`. Read `preferences.json` →
`ai_constraints.ai_framework`. Language for the adapter comes from
`ai-workload-profile.json → integration.languages[0]` (`python`→`.py`, `javascript`/`typescript`→
`.js`, `go`→`.go`, else `.py`).

| `migration_path` / framework                                         | Emits (in addition to the always-on set)                            |
| -------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `runtime_openai_responses`                                           | Runtime OpenAI setup/code preserving `responses.create`             |
| `runtime_openai_chat`                                                | Runtime OpenAI setup/code preserving `chat.completions.create`      |
| `runtime_messages`                                                   | Runtime Anthropic setup/code preserving `messages.create`           |
| `mantle_openai_responses` / `mantle_openai_chat` / `mantle_messages` | endpoint-specific Mantle setup/code preserving the source API       |
| `runtime_converse` / `runtime_invoke`                                | `ai-migration/provider_adapter.{py,js,go}` for the exact native API |
| gateway (`llm_router`/`api_gateway`/`voice_platform`/`framework`)    | `ai-migration/gateway_config.{yaml,py,json}` — skip the adapter     |
| agentic `migration_approach == harness`                              | `ai-migration/harness.json`, `ai-migration/deploy_harness.sh`       |
| agentic `migration_approach == strands`                              | `ai-migration/strands_agents.py`, `ai-migration/deploy_strands.sh`  |
| eval opted in                                                        | `ai-migration/eval-prompts.jsonl`, `ai-migration/run-evaluation.sh` |

Normalize legacy absent/`direct`, `converse`, `gpt-oss`, and `mantle` once at this boundary;
reject every other unknown non-empty value. Runtime is the default. A Mantle lane requires a
verified endpoint requirement from the design.

**Always emit (every path):** `ai-migration/setup_bedrock.sh`, `ai-migration/test_comparison.py`
(always Python), `ai-migration/bedrock_monitoring.tf`.

> **Runtime is the default path for Azure OpenAI and Anthropic SDK migrations.** Preserve the
> detected Responses, Chat Completions, or Messages API when the current model/API/Region
> supports it. Mantle is selected only for a verified endpoint requirement.

## Step 1R: Runtime-compatible source SDK paths

- `runtime_openai_responses` and `runtime_openai_chat`: use
  `https://bedrock-runtime.{region}.amazonaws.com/openai/v1`, an auto-refreshing short-lived
  Bedrock token, the selected prefixed Runtime/CRIS ID, and `bedrock:InvokeModel*` IAM.
- `runtime_messages`: use
  `https://bedrock-runtime.{region}.amazonaws.com/anthropic` with the same credential and IAM
  posture. The Anthropic SDK appends `/v1/messages`, so the final request path is
  `/anthropic/v1/messages`.
- Preserve the exact source method and payload. Do not reshape Chat to Responses or Messages to
  Converse merely because the endpoint changed.

## Step 1M: Mantle-compatible source SDK paths

Shell/code setup, **dry-run by default** with an `--execute` flag. OpenAI lanes use
`OPENAI_BASE_URL=https://bedrock-mantle.{region}.api.aws/openai/v1`; Messages uses the current
public Mantle Anthropic base path. Use a short-lived Bedrock token provider, the documented bare
model ID, and only `bedrock-mantle:CreateInference`, `bedrock-mantle:GetProject`,
`bedrock-mantle:ListProjects`, and `bedrock-mantle:CallWithBearerToken` as generated by
`iam_policy.py`; scope the first three to the project ARN and use `Resource: "*"` only for
`CallWithBearerToken`. Preserve the exact Responses, Chat Completions, or Messages
method selected by `migration_path`. Per-workload `MAX_TOKENS` comes from a lookup table,
default `1024`.

## Step 1: `provider_adapter.{py,js,go}` (direct / gpt-oss path)

Feature-flagged on `AI_PROVIDER` (values `azure_openai` | `bedrock` | `shadow`; **default
`azure_openai`**). Emits methods gated on `integration.capabilities_summary`: `text_generation`→
`generate`, `streaming`→`generate_stream`, `embeddings`→`embed`. Bedrock side is boto3 Converse
(`BEDROCK_INFERENCE_PROFILE_ARN` env, model-id fallback). **Azure source side:** the `azure_openai`
branch calls the `AzureOpenAI` client (`azure_endpoint`, `api_version`) for Python / `@azure/openai`
(or the `openai` SDK with `azure` config) for Node — NOT Vertex/`@google-cloud/vertexai`.

## Step 2: `test_comparison.py`

Always Python. Runs the same prompts through the source (Azure OpenAI) and the Bedrock target and
diffs outputs, so the user validates behavior before cutover.

## Step 3: `setup_bedrock.sh`

Enables the chosen model(s), creates endpoint-specific IAM, and emits only the credentials and
base path required by the exact migration path. Runtime uses `bedrock:InvokeModel*`; Mantle uses
the exact Mantle inference actions from `iam_policy.py`. Verification invokes the exact selected API and model ID in the target
account and Region.

## Step 3B: `gateway_config.{yaml,py,json}` (gateway users)

Format by framework: `llm_router` → `gateway_config.yaml` (LiteLLM); `framework` →
`gateway_config.py`; `voice_platform` → `gateway_config.json`; `api_gateway` → `gateway_config.yaml`.
OpenRouter branches on `code_migration.openrouter_path` (`same_model_mantle` → run Step 1M;
`direct` → adapter; `litellm` → yaml; `keep_openrouter` → json; absent → litellm).

## Step 3C / 3E: agentic artifacts

Harness (`migration_approach == harness`): `harness.json`, `deploy_harness.sh`,
`incremental_migration.sh` (only if `harness_config.incremental_migration`). Strands
(`== strands`): `strands_agents.py`, `deploy_strands.sh`, `bridge_retarget.py` (only if
`strands_config.bridge_phase`). Both port from gcp unchanged (AgentCore is the target, agnostic of
source cloud).

## Step 3D: eval artifacts (opt-in)

`eval-prompts.jsonl`, `run-evaluation.sh`.

## Step 3F: `bedrock_monitoring.tf` (all paths)

Budget `limit_amount = ceil(projected_bedrock_monthly * 1.5)`, min 10, emitted as a computed
integer (seed `projected_bedrock_monthly` from `estimation-ai.json → cost_comparison.projected_bedrock_monthly`,
default 50). Cost-anomaly monitor `monitor_type = "DIMENSIONAL"`, `monitor_dimension = "SERVICE"`.
`aws_bedrock_inference_profile` requires the AWS provider `>= 5.66`.

## Write `generation-ai.json`

```jsonc
{
  "phase": "generate",
  "generation_source": "ai",
  "timestamp": "<ISO 8601>",
  "migration_plan": { "approach": "...", "phases": [], "models_to_migrate": [] },
  "step_by_step_guide": {},
  "rollback_plan": {
    "mechanism": "feature_flag",
    "flag_name": "AI_PROVIDER",
    "default_value": "azure_openai",
    "rollback_time": "...",
    "triggers": []
  },
  "monitoring": {},
  "production_readiness_checklist": [],
  "success_criteria": {},
  "recommendation": {}
}
```

`rollback_plan.mechanism` MUST be `"feature_flag"`; `flag_name` `AI_PROVIDER`; `default_value`
`azure_openai` (the pre-cutover provider — flip to `bedrock` to cut over, back to `azure_openai`
to roll back).

## Write `STARTUP_PROGRAMS.md`

AWS Activate tiers, branching on `preferences.json → startup_program_status`
(`eligible_founders`/`eligible_portfolio`/`has_credits`/`unknown`). Include the Generative AI
Accelerator section ONLY when `ai_monthly_spend` is high AND `agentic_profile.is_agentic`. Content
is AWS-only and ports from gcp unchanged.

## Step: Self-Check

- [ ] `AI_PROVIDER` default is `azure_openai` everywhere (adapter flag + rollback default).
- [ ] Every exact path emitted its matching source-SDK or Bedrock-native artifact lane.
- [ ] `bedrock_monitoring.tf` present on every path; budget is a computed integer ≥ 10.
- [ ] No secret VALUE in any emitted file; credentials are env-var references.
- [ ] Endpoint host, base path, credential method, IAM family, and model-ID form match
      `migration_path`; GPT-5.4/GPT-5.5 Runtime CRIS combinations are allowed when current docs verify them.
- [ ] Plugin attribution strings say "Azure-to-AWS".
- [ ] `generation-ai.json` validates; `rollback_plan.mechanism == "feature_flag"`.

## Phase Completion

**Do NOT update `.phase-status.json`** — the parent `generate.md` handles phase completion after
the main-window validation step.

> **`_assert` has no teeth.** The self-check is prose the `rw` worker both produces and evaluates;
> CI binds it but never runs it. Judge correctness by the step-5 AI fixture oracle and a
> fresh-context run, never by "the artifacts were emitted."

## Status — build step 3 (AI route)

The AI Generate fragment. Wired into `generate.md` `_fragments`
(`_when aws-design-ai.json exists AND run_mode == decide_and_execute`). Its inputs come from
`design-ai.md` (step 2) and `estimate-ai.md` (step 3). Reachable end-to-end only once
`discover-app-code.md` (step 4) produces `ai-workload-profile.json` for a non-IaC estate.
