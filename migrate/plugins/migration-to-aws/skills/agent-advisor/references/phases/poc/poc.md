---
_phase: poc
_title: "POC — Deployment plan + deployable proof-of-concept"
_requires_phase: migration-plan
_input:
  - design.json
  - confirm.json
_fragments:
  - _id: poc-report
    _trigger: { _always: true }
    _file: phases/poc/poc-report.md
_assemble:
  _file: phases/poc/poc-assemble.md
_produces:
  - plan.md
_advances_to: complete
_preconditions:
  - _check_file_exists: [design.json, confirm.json]
    _on_failure: _unrecoverable
  - _validate_json: [design.json, confirm.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: plan.md
    _on_failure: _halt_and_inform
  - _assert: "a deployment plan (plan.md) and a runtime-appropriate POC under poc/ were written (Step 3 dispatch on the verdict), with the resolved Bedrock model id (or a TODO: verify placeholder — never a fabricated id) and deploy.sh guardrails; Mode B additionally left a created-resources ledger + cleanup.sh"
    _on_failure: _halt_and_inform
---

# Phase: POC — Deployment plan + deployable proof-of-concept

Reached after the user confirms **Gate 2** — on Build paths (`build_scratch` /
`build_deploy`), or on `migrate` with a completed migration plan. Runs for ANY winning
runtime: agentcore / ecs / eks / lambda / lambda_microvms — the artifacts differ by
runtime (Step 3 dispatch), the flow does not. Completes the **idea → plan → deploy**
journey: it first writes a **deployment plan** (`plan.md` — the staged "how to stand this
up" steps), then a complete, deployable POC the user runs themselves.
In **Mode A (deliverables — the default)** this phase generates files only — it NEVER runs
deploy commands, never touches the user's AWS credentials, and never creates real
resources; the user reviews the plan + artifacts, then runs `./deploy.sh` themselves.
**Mode B (assisted build)** is an explicit opt-in chosen at Gate 2b (Step 0) that executes
the generated deploy steps in the user's account under the Step 4 safety contract.

## When this phase runs

- entry_point ∈ {`build_scratch`, `build_deploy`}, any verdict (or co_recommend
  `chosen_runtime`) in {agentcore, ecs, eks, lambda, lambda_microvms}.
- For `migrate`: POC runs ONLY if `phases.migration_plan == "completed"` (the POC implements
  the produced plan). Without a plan, migrate has nothing to implement — the flow completes
  after Generate/handoff.
- This phase is only loaded after the user confirmed **Gate 2** (asked in generate.md Step 7
  or migration-plan.md Step 6).

## Step 0 — Gate 2b: choose the POC mode

Ask via AskUserQuestion:

> "How do you want the POC delivered?"
>
> - **Mode A — Generated deliverables (recommended):** I generate the deployment plan, agent
>   code, and deploy script; you review and run `./deploy.sh` yourself. Nothing touches your
>   AWS account until you run it.
> - **Mode B — Assisted build:** after generating the same deliverables, I execute the deploy
>   steps in your AWS account with you — confirming your AWS identity first and asking before
>   every resource-creating or billable step. Creates real, billable resources.

Record the choice. Steps 1–3 run for BOTH modes (Mode B builds on Mode A's artifacts);
Step 4 runs ONLY for Mode B; Steps 5–6 run for both.

## Step 1 — Read inputs

Read `$RUN_DIR/design.json` (verdict, deployment_model, agentcore_services,
model_recommendation) and `$RUN_DIR/confirm.json` (confirmed deployment model + services). The
recommendation doc + diagram already exist from Generate; POC builds on those decisions.

**Plan-backed POC (Stage 2 ran):** if `.phase-status.json` has `migration_plan_ctx` and
`phases.migration_plan == "completed"`, ALSO read
`<migration_plan_ctx.migration_dir>/aws-design-ai.json` — via the recorded path ONLY, never
by re-globbing `.migration/` (a glob can pick up a stale run). When present, it wins over
`design.json` where they overlap (Steps 2, 2.5 and 3 each state where). If Stage 2 did not
run (skipped / not applicable / failed), proceed from `design.json` alone — the pre-existing
behavior — and label the POC "not plan-backed" in plan.md.

**Framework-migration POC (the 3-F trigger):** when plan-backed AND
`aws-design-ai.json.ai_architecture.code_migration.primary_pattern == "framework"` AND
`migration_path` is NOT `"mantle"` or `"gpt-oss"`, the POC is the **user's own app,
migrated** (Step 3-F) — not a hello-agent. In that case also read from
`migration_plan_ctx.repo` every original source file listed in
`code_migration.files_to_modify[]`. If a listed file does not exist in the repo, warn and
skip it; if NONE of the listed files exist, fall back to the hello-agent template and label
the POC "plan could not be applied — see aws-design-ai.json" in plan.md and the README.
Key the trigger on `primary_pattern` (a schema'd, checklist-enforced field) — NOT on the
`migration_path` string, whose value is free-form outside mantle/converse/gpt-oss.

## Step 2 — Resolve the Bedrock model id (verify, don't guess)

**Plan-backed:** when `aws-design-ai.json` is loaded, take the model id from
`design_blocks[0].target_bedrock_model` (or, if `design_blocks` is absent, the FIRST entry
of `ai_architecture.bedrock_models[].aws_model_id`) — the plan already region-validated it.
`bedrock_models[]` may carry alternative/backup entries; the primary is always the first
design block. The MCP check below then only confirms the id is still current.
**Not plan-backed:** resolve as follows.

`design.json.model_recommendation` carries an internal model key (e.g. `claude_sonnet_4_6`). The
POC needs the **real Bedrock model/inference-profile id**. Verify it via the awsknowledge MCP per
`references/decision-refs/freshness.md` (same anti-fabrication rule). If the MCP is not called,
write the id as a clearly-marked `TODO: verify model id` placeholder in the generated files and
say so in the README — never fabricate an id as if verified.

**Strip environment annotations from the model id.** The running assistant's model name may
carry a context-window annotation like `[1m]` (e.g. `us.anthropic.claude-sonnet-4-6[1m]`).
That suffix is a harness label, NOT a valid Bedrock model/inference-profile id — a Bedrock
call with it 404s. Before writing the id into any generated file, strip any trailing
`[...]` bracket annotation. The id you emit must be exactly what Bedrock accepts (e.g.
`us.anthropic.claude-sonnet-4-6`). If unsure of the exact id, use the `TODO: verify model id`
placeholder rather than a bracket-tagged string.

## Step 2.5 — Write the deployment plan (`$RUN_DIR/plan.md`)

Before generating any code, write the **deployment plan** — the "how to stand this up" bridge
between the recommendation (what to build) and the POC files (the built artifacts). This is the
**plan** in idea → plan → deploy. Write it to `$RUN_DIR/plan.md`. Keep it concrete and staged;
derive every item from `design.json` / `confirm.json` — plus, when plan-backed, from
`aws-design-ai.json`: stage the steps to implement the migration plan's design blocks
(one stage per design_block where sensible), and add a final "full migration" pointer to
the complete guide in `migration_plan_ctx.migration_dir`. Never from assumptions. Include:

1. **Goal** — one line: stand up an AgentCore POC of <the user's agent> to validate the loop.
2. **Prerequisites** — AWS account + credentials, target region, Bedrock model access enabled
   for the resolved model id, `uv` + `agentcore` CLI installed. Mark any `TODO: verify` items.
3. **What gets created** — the AWS resources the POC provisions (AgentCore Runtime + the
   confirmed services from `confirm.json`, e.g. Gateway/Memory), so the user knows the blast radius
   and that it is billable.
4. **Staged steps** — numbered, each with a **verification** and, where relevant, a **rollback**.
   Match the stages to the POC variant:
   - **Harness (3-H):** Stage 1 review generated `harness.json` + system prompt → values match
     intent. Stage 2 (Gateway) point at your existing API/MCP endpoint → endpoint reachable.
     Stage 3 `./deploy.sh` → `agentcore status` shows deployed/READY. Stage 4 smoke test via
     `agentcore invoke` (pass the target flag when the aws-target is not named `default`).
     Stage 5 (Memory) validate cross-session recall — recall needs a stable actor identity
     across invocations and long-term extraction is asynchronous; allow a few minutes.
   - **Framework migration (3-F):** Stage 1 review the migrated files (diff vs your original
     code — the changes come from the migration plan) → changes match aws-design-ai.json.
     Stage 2 run the compile check locally (`python -m py_compile` on each .py) → all pass.
     Stage 3 (optional, needs deps + AWS creds) run the entrypoint server locally and POST
     `/invocations` → model responds. Stage 4 `./deploy.sh` → `/ping` returns healthy.
     Stage 5 smoke test: POST `/invocations` with a real prompt → model responds.
   - **Hello-agent (3a–3e):** Stage 1 review `agent.py` + config → values match intent.
     Stage 2 `./deploy.sh` → `/ping` returns healthy. Stage 3 smoke test: POST
     `/invocations` → model responds. Stage 4 (Memory, if enabled) validate recall.
   - Rollback (all variants): how to tear down if a stage fails. Code/3-F path:
     `agentcore destroy` — `TODO: verify`. Harness path: the `@aws/agentcore` CLI has no
     destroy command; it provisions via CDK, so teardown is deleting the deployment's
     CloudFormation stack (`aws cloudformation delete-stack`).
5. **Cost note** — POC-scale is small but non-zero; point to recommendation §10, no dollar figures.
6. **Open placeholders** — the `TODO: verify` items (model id / CLI flags / teardown) to confirm
   against AWS docs before deploying.

The `deploy.sh` and `README.md` generated in Step 3 must stay consistent with this plan (same
stages, same placeholders). If they diverge, the plan is the source of truth for the sequence.

## Step 3 — Write the POC under `$RUN_DIR/poc/`

**RUNTIME DISPATCH FIRST** — check `design.json.verdict` (or co_recommend
`chosen_runtime`):

- **agentcore** → the AgentCore branches below (3-H / 3-F / 3a–3e), unchanged.
- **ecs / eks / lambda / lambda_microvms** → load
  `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/poc-shapes.md`
  and generate EXACTLY the shape specified for the verdict (artifacts,
  Terraform create-whitelist, auth modes, smoke path, teardown). The
  deploy.sh guardrails template from 3d applies to every runtime (typed
  `deploy` confirmation, cost warning, env-var parameterization, no
  credentials). Steps 2 (model id) and 2.5 (plan.md) already ran and their
  outputs feed the shape. A plan-backed 3-F migration on a container runtime
  ships the user's migrated app in the Dockerfile instead of the hello agent
  — 3-F's file-selection logic applies before containerization.

**For agentcore, BRANCH NEXT** — the POC must implement what the user confirmed and
what the migration plan prescribes, never silently fall back to the generic code path:

1. `deployment_model == "harness"` → **3-H (Harness path)**. The deliverable is the
   declarative Harness project; do NOT make `agent.py` + a container the deploy artifact —
   that is the code path the user did not choose.
2. `deployment_model == "framework_on_runtime"` AND the **3-F trigger** from Step 1 fired
   (plan-backed, `primary_pattern == "framework"`, not mantle/gpt-oss, at least one
   `files_to_modify[]` file exists) → **3-F (Framework migration path)**. The deliverable is
   the USER'S OWN APP with the migration plan's changes applied — generating a fresh
   hello-agent here contradicts the plan the user just approved.
3. Otherwise (`framework_on_runtime` without a usable plan, or absent) → **3a–3e
   (hello-agent code path)**.

### 3-H. Harness path (deployment_model == "harness")

The Harness model is **declarative**: the agent is a configuration (model + system prompt +
tools/Gateway + Memory), not custom serving code. Generate:

1. **`poc/harness.json`** — the deployable agent declaration itself (NOT a side artifact):
   model id from Step 2, a one-line system prompt, the confirmed `agentcore_services` from
   `confirm.json`, session limits from the AgentCore card. Mark external wiring (Gateway
   targets, KB sources) as `TODO`.
2. **`poc/deploy.sh`** — same guardrails as 3d (cost warning + typed `deploy` confirmation),
   but the commands are the **Harness CLI flow**, which is DIFFERENT from the code path:
   Harness deploys via the Node-based `@aws/agentcore` CLI (`agentcore create` / `agentcore
   deploy` with an `agentcore.json` project config) — NOT via the Python starter-toolkit's
   `configure --entrypoint agent.py` + `launch` (that toolkit only supports the
   code/container path). The exact Harness CLI commands are **volatile**: verify via the
   awsknowledge MCP (freshness rule); if not verified this run, write the command block with
   `# TODO: verify Harness CLI commands against AWS docs` and say so in the README.
3. **`poc/README.md`** — per 3e, plus one line stating this is a declarative Harness
   deployment: "no agent serving code to maintain; the agent is defined by harness.json."
4. **No `agent.py`, no Dockerfile** — if a smoke-test client is useful, a short
   `poc/invoke_test.sh` (curl/CLI invoke) is enough. For the Harness CLI that is
   `agentcore invoke "<prompt>"` run from the project directory `agentcore create`
   actually generated (don't hardcode a guessed directory name), passing the target flag
   when the aws-target is not named `default`.

Then skip 3a–3d and continue at Step 4 (Mode B) or Step 5.

### 3-F. Framework migration path (plan-backed, primary_pattern == "framework")

The POC is the **migrated version of the user's own app** — the migration plan's code
changes applied to their real source, packaged to deploy on AgentCore Runtime. It is a
**disposable deployment-proof**, not the authoritative migration: the user's repo is never
modified; the POC lives entirely under `$RUN_DIR/poc/`.

**3-F.1 — Copy the app.** Copy the repo (`migration_plan_ctx.repo`) into `$RUN_DIR/poc/app/`,
EXCLUDING: `.git/`, `.migration/`, `.agent-advisor/`, `__pycache__/`, `.venv/`/`venv/`,
`node_modules/`, caches, and binary/media files (images, gifs, archives). Unlisted source
files (e.g. `prompts.py`) are copied as-is — imports between files keep working.

**3-F.2 — Apply the plan's changes, minimally.** For each
`code_migration.files_to_modify[]` entry, apply its `changes[]` to the copied file with
these rules:

- **Minimal interpretation** — make the smallest edit that satisfies the change description.
- **Skip optional/phase-2 items** — any change marked "optional", "later", "phase 2", or
  that `services_to_migrate` defers (e.g. "swap in-process memory for the AgentCore Memory
  API later") stays UNAPPLIED; note it in the README under "deferred by design".
- **Drift guard** — if a change references code that is not present in the current file
  (the repo moved since Discover), do NOT guess: leave that change unapplied and add a
  `TODO: plan drift` note at the top of the file and in the README.
- **Adapt mechanically-implied edits** — e.g. if the original splats a settings dict into
  the old client constructor and the new client takes different kwargs, fix the settings
  construction too; removed env vars (per `env_changes.remove`) must not be read anywhere.

**3-F.3 — Entrypoint server (do NOT implement the plan's contract text literally).** The
plan's `agentcore_entrypoint` field (when present) describes intent, not a working design —
UI-framework session handlers (Chainlit/Streamlit/Gradio) are bound to their own server's
session lifecycle and CANNOT be invoked from a plain POST. Build the honest structure
instead:

1. Extract the core LLM-call logic (build messages, invoke the migrated client, windowed
   memory keyed by a session id) from the UI handler into a shared module
   (e.g. `poc/app/core.py`), and have the UI handler call it.
2. Add a separate entrypoint server (e.g. `poc/app/agentcore_app.py`) serving
   `POST /invocations` (`{"prompt": ..., "session_id": ...}` → shared core → response) and
   `GET /ping` (200) — same contract as the 3a template, but calling the user's migrated
   logic instead of raw boto3.
3. The container CMD runs the entrypoint server. The original UI (e.g. `chainlit run
   app.py`) remains **local-dev only** — AgentCore Runtime invokes `/invocations`; it does
   not host a browser UI. Say this explicitly in the README.
   If `agentcore_entrypoint` is absent from the plan, use the standard contract above anyway.

**3-F.4 — Dependencies: follow the repo's own tooling, and keep versions compatible.** Apply
`code_migration.dependency_changes` to the repo's existing manifest (`pyproject.toml` /
`package.json` / `requirements.txt` — whichever the repo uses). Do NOT introduce a second,
parallel manifest. If a lockfile exists (`poetry.lock`, `package-lock.json`, `uv.lock`),
DELETE it from the copy and note in the README that the user must re-lock
(`poetry lock` etc.) — a stale lockfile contradicting the edited manifest is worse than none.

**Version-compatibility guard:** when a change adds a package that constrains a package the
repo pins, update BOTH so they are compatible — do not leave a manifest that cannot resolve.
The common case: `langchain-aws` (the Bedrock LangChain integration) requires
`langchain-core` / `langchain` from the 0.3+ line; a repo pinning `langchain = "^0.1.x"`
(from its OpenAI era) will NOT resolve against `langchain-aws >= 0.2`. Bump the base
`langchain` pin to the range `langchain-aws` needs (verify the exact floor via the
`dependency-conflict-resolution` helper if available, or mark it `TODO: verify langchain /
langchain-aws version compatibility` in the README). The rule generalizes: an added
integration package and the framework it plugs into must share a resolvable version range.

**3-F.5 — Verify what was generated.** Run `python -m py_compile` (or the language's
equivalent syntax check) on every generated/modified source file. Fix syntax errors before
finishing. If dependencies aren't installable locally, note in the README that the compile
check passed but an import-level check needs `poetry install` first. A POC that doesn't
compile is a defect — this step is not optional. **Clean up compile byproducts:**
`py_compile` writes `__pycache__/` next to the sources — delete any `__pycache__/` and
`.pyc` files it created so they are not shipped in the POC.

**3-F.6 — Dockerfile + deploy.sh + README.**

- `Dockerfile`: build from the repo's manifest (e.g. Poetry install), CMD = the entrypoint
  server from 3-F.3.
- `deploy.sh`: the 3d template, with `--entrypoint` pointing at the 3-F.3 server file (NOT
  `agent.py`) and any build step the manifest requires.
- `README.md`: per 3e, PLUS, prominently: (a) "This is the migrated version of YOUR app
  (from `<repo>`), generated as a disposable deployment-proof — your original repo was not
  modified"; (b) the list of applied changes and any deferred/drifted ones; (c) "For the
  authoritative in-repo migration (git branch, generated tests, behavior-delta review,
  quality eval), run `/migration-to-aws:llm-to-bedrock`" — the POC does not replace it;
  (d) the local-dev note for the original UI.

Then skip 3a–3d and continue at Step 4 (Mode B) or Step 5.

### Code path (deployment_model == "framework_on_runtime", no usable plan) — 3a–3e

Create these files. Keep the agent **minimal but genuinely runnable** — a hello-agent that really
calls the recommended Bedrock model and answers the AgentCore entrypoint contract
(`/invocations` POST + `/ping` GET). Do NOT build scenario-specific business logic in v1.

### 3a. `agent.py` — minimal runnable agent

- Implements the AgentCore entrypoint contract: `POST /invocations` (read prompt from the
  request body, call Bedrock `Converse` with the resolved model id, return the text) and
  `GET /ping` (return 200 for health).
- Uses `boto3` bedrock-runtime. Region from an env var (`AWS_REGION`), no hardcoded creds.
- Include a one-line system prompt and echo the model's reply — enough to prove the loop works.

**Code-path branch (plan-backed only):** if `aws-design-ai.json` has
`ai_architecture.code_migration.migration_path == "mantle"`, do NOT use the boto3 template —
generate the agent with an OpenAI-compatible client pointed at the Bedrock Mantle endpoint
instead (same `/invocations` + `/ping` contract; base URL and model id from the plan; mark
the endpoint URL `TODO: verify` if not MCP-checked this run). For `"converse"`, absent, or
not plan-backed: use the boto3 template below.

Use this template verbatim, substituting `<MODEL_ID>` with the Step 2 value (or the
`TODO: verify model id` placeholder if the MCP was not called):

```python
"""Minimal AgentCore POC agent — proves the Bedrock loop works end to end.
Entry contract: POST /invocations (run a prompt), GET /ping (health)."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "<MODEL_ID>")
REGION = os.environ.get("AWS_REGION", "us-east-1")
SYSTEM_PROMPT = "You are a helpful assistant running as an AgentCore POC. Be concise."

_bedrock = boto3.client("bedrock-runtime", region_name=REGION)


def run_prompt(prompt: str) -> str:
    resp = _bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    return resp["output"]["message"]["content"][0]["text"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/invocations":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        prompt = body.get("prompt", "Say hello from AgentCore.")
        try:
            answer = run_prompt(prompt)
            payload = json.dumps({"response": answer}).encode()
            self.send_response(200)
        except Exception as exc:  # POC: surface the error to the caller
            payload = json.dumps({"error": str(exc)}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
```

### 3b. `requirements.txt`

- `boto3` (bedrock-runtime), plus the minimal web server deps for the entrypoint contract.
- Pin nothing exotic; keep it a starter.

### 3c. Deployment config

- Keep `agent.py` as the entrypoint; add a short note that AgentCore runs the container and
  expects the `/invocations` + `/ping` contract. (Harness deployments never reach this
  section — they follow 3-H, where `harness.json` IS the deploy artifact.)

### 3d. `deploy.sh` — one-command deploy (generated, NOT executed)

- A bash script that runs `agentcore configure` then
  `agentcore launch --auto-update-on-conflict` (the project's standard launch invocation).
- **Guardrails baked into the script**: at the top, echo a clear warning that running it creates
  real AWS resources in the user's account and may incur cost; require an explicit
  `read -p "Type 'deploy' to continue: "` confirmation before any `agentcore` call.
- Parameterize region + model id via env vars; do NOT embed credentials.
- **The exact `agentcore` CLI flags are volatile** — verify current `configure`/`launch` usage
  via the awsknowledge MCP (freshness rule). If not verified this run, keep the
  `# TODO: verify current agentcore CLI flags against AWS docs` comment above the commands.

Use this template:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ⚠️  This creates REAL resources in your AWS account and may incur charges.
echo "This will deploy an AgentCore POC to AWS account: $(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo '<not logged in>')"
echo "Region: ${AWS_REGION:-us-east-1}   Model: ${BEDROCK_MODEL_ID:-<MODEL_ID>}"
read -r -p "Type 'deploy' to continue: " CONFIRM
[ "$CONFIRM" = "deploy" ] || { echo "Aborted."; exit 1; }

export AWS_REGION="${AWS_REGION:-us-east-1}"
export BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-<MODEL_ID>}"

# TODO: verify current agentcore CLI flags against AWS docs (awsknowledge MCP)
agentcore configure --entrypoint agent.py --name "${AGENT_NAME:-poc-agent}"
agentcore launch --auto-update-on-conflict --env AWS_REGION="$AWS_REGION" --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID"

echo "Deployed. Test with the curl in README.md. Tear down with: agentcore destroy  # TODO: verify"
```

### 3e. `README.md` — the POC runbook

Top of file, a prominent notice: **"Running deploy.sh creates real resources in your AWS account
and may incur charges."** Then:

- **Follow the plan:** point to `../plan.md` as the staged deployment plan — the README is the
  runbook for the artifacts; `plan.md` is the sequence to follow.
- **Prerequisites:** AWS credentials configured, target region, `uv`, the `agentcore` CLI
  installed, model access enabled for the resolved Bedrock model.
- **Deploy:** `./deploy.sh` (one command).
- **Test after deploy:** a sample `curl`/CLI call to `/invocations` with a prompt, and the
  expected shape of the response.
- **Tear down:** how to remove the POC (the `agentcore` destroy/delete path) so the user doesn't
  leave resources running — mark the exact command `TODO: verify` if not MCP-checked.
- **Cost note:** POC-scale resources are small but non-zero; point to the recommendation doc's
  cost-magnitude section, no dollar figures here.

## Step 4 — Mode B: assisted build (ONLY if chosen at Gate 2b)

Execute the generated deployment in the user's account. **Safety contract — every point is
mandatory; no step may be skipped or reordered:**

0. **Deployment-model fidelity gate.** Before touching any tooling, restate what is about to
   be deployed and confirm it matches `confirm.json.deployment_model` and the Step 3 branch
   taken: a Harness POC deploys the declarative `harness.json` via the Harness CLI (3-H);
   a framework-migration POC (3-F) deploys the user's migrated app container with the 3-F.3
   entrypoint server as the entrypoint — NOT `agent.py`; a hello-agent POC deploys
   `agent.py` as a container. **If the locally available tooling cannot deploy the confirmed
   model** (e.g. only the Python starter toolkit — code path — is installed, but the user
   chose Harness), STOP and tell the user explicitly: "Your confirmed deployment model is
   `<X>`, but the installed CLI only supports `<Y>` — deploying `<Y>` would contradict the
   recommendation." Offer: (a) install/use the correct CLI, or (b) knowingly deploy the
   other model as a loop-proof POC, clearly labeled as NOT the recommended deployment model
   in plan.md, the README, and the final brief. Never silently substitute one deployment
   model for the other.

1. **Identity gate.** Run `aws sts get-caller-identity`. On failure: instruct
   `aws configure` / `aws sso login` (suggest `! aws sso login` to run it in-session) and
   re-check — never proceed unconfirmed. On success show Account / Arn / UserId via
   AskUserQuestion: "This identity will be used to create real, billable resources. Is this
   the intended (non-production) account?" Record the confirmed region and profile once;
   pass them explicitly (`--region`, `--profile`) on every subsequent AWS command.
2. **Command boundary.** Execute ONLY the commands present in the generated `deploy.sh`
   (e.g. `agentcore configure`, `agentcore launch`) plus read-only verification calls
   (`/ping`, `aws sts get-caller-identity`, describe/list). Anything else — ad-hoc resource
   creation, VPC/network changes, modifying or deleting resources this run did not create —
   is out of bounds.
3. **Per-step confirmation.** Before each resource-creating or billable command: show the
   exact command and its cost implication, and get an explicit yes via AskUserQuestion.
4. **Ledger before create.** Append the intended resource to
   `$RUN_DIR/poc/created-resources.json` BEFORE running its create command
   (`{"type": ..., "name": ..., "region": ..., "status": "pending"}`), then update
   `"status": "created"` after — a crash between create and record must not orphan an
   untracked resource. On the code path, all resource names carry the run id suffix (e.g.
   `poc-agent-<run_id>`) for idempotency and safe teardown matching. On the Harness path,
   the CLI names resources itself (project/agent name + generated suffix) — do not promise
   run-id suffixes; instead record the actual names/ARNs (and the CloudFormation stack name)
   in the ledger after deploy, and make those the teardown match keys.
5. **Teardown script.** Regenerate `$RUN_DIR/poc/cleanup.sh` from the ledger after every
   step. It deletes only ledger-listed resources, verifies each deletion, and reports
   leftovers instead of exiting silently.
6. **Stop on failure.** Any failed step halts the flow: report what exists (from the
   ledger), point at `cleanup.sh`, and ask the user how to proceed. No automatic retry, no
   automatic rollback without confirmation.
7. **Never disable safety protections** (deletion protection, versioning, backup retention).
8. **Back-propagate verified facts.** After the deploy succeeds, revisit every `TODO: verify`
   in `plan.md`, `README.md`, `deploy.sh`, and `invoke_test.sh` that this run resolved
   empirically (actual CLI commands and flags, invoke payload/target format, teardown
   mechanism) and rewrite those files to state the verified fact instead of the placeholder.
   Scripts must contain the commands that actually succeeded this run — a generated script
   that contradicts the executed deployment is a defect, not a leftover. (`cleanup.sh` is
   already covered by point 5; this point extends the same discipline to the other
   artifacts.)

After the deploy succeeds: run the smoke test from plan.md Stage 4 — POST `/invocations` on
the code path, or `agentcore invoke` on the Harness path (pass the target flag when the
aws-target is not named `default`) — show the result, then show the teardown instructions
(`cleanup.sh`) as the LAST message — the user decides whether the POC stays up.

## Step 4.5 — Generate the HTML POC report (both modes)

Load `references/phases/poc/poc-report.md` and follow it to produce
`$RUN_DIR/poc/poc-report.html` and open it in the browser. Runs for BOTH Mode A and Mode B
(Mode B additionally shows the deployed-resources ledger). Non-blocking — if it fails, log a
warning and continue to Step 5.

## Step 5 — In-chat brief

Point the user first to the **deployment plan** at `$RUN_DIR/plan.md` (idea → **plan** → deploy),
then to the POC files at `$RUN_DIR/poc/`. List the files and state plainly:

- The flow is **idea → plan → deploy**: `plan.md` is the staged how-to; `poc/` is the generated
  artifacts; deployment is the user's own action.
- **Mode A:** In Mode A, this advisor generated the files but will **not** deploy them — deployment is the user's
  explicit action via `./deploy.sh`.
- **Mode B:** list created resources from the ledger (`created-resources.json`) and point at `cleanup.sh`.
- What `./deploy.sh` will do and that it creates real, billable resources.
- Any `TODO: verify` placeholders that remain (model id / CLI flags / teardown command) and that
  they should be confirmed against AWS docs before deploying.

## Step 6 — Write state

Set `phases.poc` = completed. The advisor flow is complete.
