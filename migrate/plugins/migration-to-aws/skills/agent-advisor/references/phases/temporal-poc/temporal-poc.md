---
_phase: temporal-poc
_title: "Temporal Worker POC — connectivity-and-pickup proof"
_kind: checkpoint
_requires_phase: temporal-worker
_trigger: { _when: "phases.temporal_poc == in_progress (Gate T 'yes' in temporal-worker.md Step 5.7)" }
_input:
  - temporal-design.json
_assemble:
  _file: phases/temporal-poc/temporal-poc-assemble.md
_produces:
  - temporal-poc/poc-report.html
_preconditions:
  - _check_file_exists: temporal-design.json
    _on_failure: _unrecoverable
  - _validate_json: temporal-design.json
    _on_failure: _unrecoverable
_postconditions:
  - _assert: "temporal-poc/ holds the smoke-worker POC per poc-shapes.md — smoke_worker.py (worker + start on task queue poc-smoke-<run_id>), Dockerfile, ecs-poc.tf (whitelist; never creates VPC/subnets/NAT/IGW/ALB; secrets via SSM, never inline), run_local.sh, deploy.sh (typed confirmation + cost warning), README — plus poc-report.html; the full 8-var TEMPORAL_* TLS contract is honored and TEMPORAL_TLS is never inferred"
    _on_failure: _halt_and_inform
---

# Phase: Temporal Worker POC — connectivity-and-pickup proof

Reached when `phases.temporal_poc == "in_progress"` (Gate T "yes" in
temporal-worker.md Step 5.7). Generates a minimal Temporal worker deployable to
ECS Fargate that connects to the USER'S Temporal server and executes one smoke
workflow — proving "an AWS worker polls my server and picks up tasks" before
the real migration. It is NOT a migration of the user's workflows; their code
stays untouched (the branch's core promise applies to the POC too).

The deploy shape (Terraform whitelist, guardrails, secrets handling, teardown
wording) comes from
`${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/references/decision-refs/poc-shapes.md`,
section "Temporal worker POC" — load it now and follow it exactly.

## Step 0 — Gate 2b: choose the POC mode

Same mode question as the main flow's poc.md Step 0 (AskUserQuestion):

> "How do you want the POC delivered?"
>
> - **Mode A — Generated deliverables (recommended):** I generate the smoke
>   worker, Terraform, and scripts; you review and run them yourself. Nothing
>   touches your AWS account until you run deploy.sh.
> - **Mode B — Assisted build:** after generating the same deliverables, I
>   execute the deploy steps in your AWS account with you — confirming your
>   AWS identity first and asking before every resource-creating or billable
>   step. Creates real, billable resources.

Record the choice. Steps 1–2 run for BOTH modes; Step 3 only for Mode B;
Steps 4–5 for both.

## Step 1 — Read inputs

Read `$RUN_DIR/temporal-design.json`: the connection target follows the plan's
Way —

- **Way 1, new Cloud namespace** (was self-hosted): the POC connects to the
  NEW Temporal Cloud namespace; runbook 2's steps 1–2 become partially
  executable. Connection posture: `tls` + API key (or `mtls` if the namespace
  is cert-based).
- **Server unchanged** (already Cloud, or self-hosted staying): the POC
  connects to the EXISTING server — a live rehearsal of runbook 1's "new
  workers join, verify pickup". Posture from the inventory:
  `*.tmprl.cloud` → `tls`/`mtls` per their auth; self-hosted → ask which of
  off/tls/mtls their server speaks (do not assume).

Ask for the concrete values now if not already known: address, namespace, and
the TLS posture inputs the contract needs (see poc-shapes.md env table).
Never ask for secret VALUES in chat — ask where they live (SSM parameter
names, local file paths).

## Step 2 — Generate `$RUN_DIR/temporal-poc/` (Mode A deliverables)

Per poc-shapes.md "Temporal worker POC". Files:

1. **`smoke_worker.py`** — one file, temporalio SDK, two subcommands:
   - `worker`: runs a Worker on task queue `poc-smoke-<run_id>` registering
     `SmokeWorkflow` (one activity round-trip returning a greeting string).
   - `start`: starts one `SmokeWorkflow` execution, waits, prints
     `workflow result: <result>` and exits nonzero on failure.
     Connection via the full env contract — `TEMPORAL_ADDRESS`,
     `TEMPORAL_NAMESPACE`, `TEMPORAL_TLS`, `TEMPORAL_API_KEY`,
     `TEMPORAL_TLS_SERVER_NAME`, `TEMPORAL_TLS_CA_PATH`,
     `TEMPORAL_TLS_CERT_PATH`, `TEMPORAL_TLS_KEY_PATH` — mapped EXPLICITLY to
     `Client.connect(tls=TLSConfig(...))`; `TEMPORAL_TLS` is never inferred
     from other vars. `off` → no TLS (local/dev only, warn in
     README); `tls` → server-auth TLS (+ optional CA/server-name); `mtls` →
     client cert/key required.
2. **`Dockerfile`** — python slim + uv + smoke_worker.py; default CMD
   `worker`.
3. **`ecs-poc.tf`** — the ECS whitelist from poc-shapes.md (cluster
   reuse-or-create, ECR, log group `/agent-advisor/poc/<run_id>`, IAM,
   egress-only SG, task def, service desired_count 1, 0.25 vCPU). Secrets
   (API key, cert/key material) via task-def `secrets` from SSM SecureString /
   Secrets Manager — never inline. NEVER create VPC/subnets/NAT/IGW/ALB;
   `VPC_ID`/`SUBNET_IDS` env → default VPC fallback → clear failure.
4. **`run_local.sh`** — pre-AWS validation, two processes: start
   `smoke_worker.py worker` in the background, run `smoke_worker.py start`,
   assert the printed result, kill the worker. Points at the user's server
   (or `localhost:7233` for a dev server). This proves the full code path —
   connect → poll → execute → result — before any AWS resource exists.
5. **`deploy.sh`** — typed `deploy` confirmation + cost warning (poc.md 3d
   template); ECR create-if-missing, build/push, `terraform init/plan/apply`.
   Then print, verbatim: "apply alone proves nothing — run the smoke:" and
   the one-off starter invocation (`aws ecs run-task` overriding the command
   to `start`, or the local alternative `python smoke_worker.py start` with
   the same env).
6. **`README.md`** — prerequisites (namespace reachable from the VPC,
   secrets provisioned in SSM, ECR access, `terraform`); deploy; test
   (expect `workflow result: hello from ...` from the starter and the
   execution visible in Temporal UI); teardown (`terraform destroy` stops the
   worker; **task queues are not deletable resources** — `poc-smoke-<run_id>`
   metadata ages out on its own and never touched production queues); cost
   note (one 0.25-vCPU Fargate task ≈ small; no dollar figures).

Nothing is executed in Mode A — files only.

## Step 3 — Mode B: assisted build (ONLY if chosen at Gate 2b)

Follow poc.md Step 4's safety contract unchanged — every point mandatory:
verify AWS identity first (`aws sts get-caller-identity`, show the user, get
explicit confirmation it is the intended account), then execute deploy.sh's
steps one at a time, asking before EVERY resource-creating or billable step
(ECR create, terraform apply, run-task). terraform destroy on abort is
offered, never auto-run.

## Step 4 — HTML POC report + open

Write `$RUN_DIR/temporal-poc/poc-report.html` — same conventions as
poc-report.md (help banner at top from `references/report-help-banner.md`,
SRI-pinned mermaid@10.9.3, dark header + `#FF9900` accent): what was
generated, the smoke-path diagram (worker service + one-off starter → user's
server), how to run, teardown. In the "Generated files" table, every file
name is a download link — the report sits in the same directory as the
artifacts, so: `<a class="dl-link" href="smoke_worker.py" download>` etc.
(same convention as poc-report.md). Then open it in the browser
(non-blocking):

```bash
open "$RUN_DIR/temporal-poc/poc-report.html"      # macOS
xdg-open "$RUN_DIR/temporal-poc/poc-report.html"  # Linux
```

If it fails (no GUI), print:
`POC report ready — open: file://$RUN_DIR/temporal-poc/poc-report.html`

## Step 5 — Write state

Give a short in-chat summary (files, the two-step proof: run_local first, then
deploy + run-task; audience-matched wording). Set
`phases.temporal_poc = "completed"` (read-merge-write; state → `complete`).
