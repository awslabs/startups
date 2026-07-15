# POC Shapes — Per-Runtime Deploy Artifacts

Single source of truth for what a generated POC looks like per winning
runtime. Loaded by `poc.md` Step 3 (non-AgentCore verdicts) and by
`temporal-poc.md` (which reuses the ECS shape). Content locked by
`scripts/test_poc_shapes.py` — changing a whitelist, auth mode, or fallback
rule requires updating that test in the same commit.

## Common contract (every runtime)

- `plan.md` precedes artifacts (staged deployment plan).
- Agent code carries the SAME minimal Bedrock-calling logic everywhere; the
  **entrypoint file name and contract are runtime-specific**: `agent.py`
  (HTTP `/invocations` + `/ping`) for AgentCore/ECS/EKS, `handler.py` (Lambda
  handler) for Lambda; Harness has no code file; a plan-backed 3-F POC ships
  the user's migrated app instead.
- `deploy.sh` guardrails (all runtimes): cost warning at top; typed
  `read -p "Type 'deploy' to continue"` confirmation before any
  resource-creating call; region/model via env vars; NO credentials embedded;
  volatile CLI flags carry `TODO: verify` unless MCP-verified this run.
- `README.md`: prerequisites, deploy, test-after-deploy, teardown, cost note
  (no dollar figures — point to the recommendation doc).
- Mode A generates files only — nothing is executed. Mode B follows poc.md
  Step 4's safety contract unchanged.

## agentcore

Unchanged — poc.md sections 3-H (Harness) / 3-F (plan-backed framework) /
3a–3e (code path) remain the authority. This file adds nothing for AgentCore.

## ecs

Artifacts: `Dockerfile`, `ecs-poc.tf`, `agent.py`, `deploy.sh`, `README.md`.

- **No ALB.** The smoke path is: deploy.sh finishes by running a one-off
  `aws ecs run-task` (or `aws ecs execute-command`) that curls the
  container's localhost endpoint, then prints the
  `aws logs tail /agent-advisor/poc/<run_id> --follow` command. A service
  that deploys but cannot be invoked is not a POC.
- **Terraform may create ONLY**: ECS cluster (reuse-or-create by name), ECR
  repo, CloudWatch log group `/agent-advisor/poc/<run_id>`, IAM roles and
  policies, security group (egress-only), task definition, service
  (desired_count 1, Fargate, 0.25–0.5 vCPU).
- **Terraform must NEVER create**: VPC, subnets, NAT gateway, internet
  gateway, ALB/NLB.
- Networking: `VPC_ID`/`SUBNET_IDS` env vars → if unset, data-source the
  default VPC → if no default VPC exists, FAIL with a clear message; never
  create one. Public IP = ENABLED when in the default VPC (no NAT
  assumption).
- IAM: task execution role attaches the managed
  `AmazonECSTaskExecutionRolePolicy`; task role gets `bedrock:InvokeModel`
  scoped to the resolved model ARN only.
- Image tag: `poc-<run_id>`. deploy.sh creates the ECR repo if missing
  (inside the typed-confirm section), builds, pushes.
- Teardown: `terraform destroy`; note that the ECR repo (if Terraform-created)
  goes with it.

## eks

Artifacts: `Dockerfile`, `k8s/namespace.yaml`, `k8s/deployment.yaml`,
`k8s/service.yaml`, `deploy.sh`, `README.md`.

- **Never creates an EKS cluster.** Requires an existing cluster; without one,
  emit the manifests plus "point kubectl at your cluster".
- Namespace is **`agent-advisor-poc-<run_id>`** — unique per run, created by
  `namespace.yaml`. Never a fixed name like `poc` (teardown of a fixed name
  could delete a user's pre-existing namespace).
- Service type **`ClusterIP`**; the README test path is
  `kubectl port-forward` + local curl. No LoadBalancer (billable cloud
  resource).
- Bedrock auth: manifests include a commented IRSA `serviceAccountName`
  block; README states the prerequisite "your node role or an IRSA service
  account must allow bedrock:InvokeModel". **The EKS POC creates no IAM
  resources.**
- deploy.sh: build/push to ECR, then `kubectl apply -f k8s/`.
- Teardown: `kubectl delete -f k8s/` — deletes exactly what it created.

## lambda

Artifacts: `handler.py`, `lambda-poc.tf`, `deploy.sh`, `README.md`.

- Function URL auth mode **`AWS_IAM` — never `NONE`** (a public
  Bedrock-invoking endpoint is an open cost hole). README test uses
  `curl --aws-sigv4` or `aws lambda invoke`.
- Terraform locks: timeout 60s, memory 512 MB, `source_code_hash` on the
  package, CloudWatch log group, env vars `AWS_REGION` + `BEDROCK_MODEL_ID`,
  role with `bedrock:InvokeModel` scoped to the resolved model ARN.
- Packaging: zip via pip target-dir; if deps exceed zip limits, container
  image packaging (note it in README).
- Teardown: `terraform destroy`.

## lambda_microvms

Artifacts: the full **lambda** shape above, PLUS `microvms.tf.disabled`.

- **Fallback rule**: every MicroVMs-specific flag or config key MUST be
  MCP-verified this run. If verification fails, the file stays `.disabled`
  with this header: "MicroVMs config pending verification — POC deploys as
  standard Lambda; rename after verifying against AWS docs." No deployable
  claim is made for unverified MicroVMs config.
- If verified: rename guidance in README; config keys cite the verification
  in the freshness footer.

## Temporal worker POC (used by temporal-poc.md)

Reuses the **ecs** shape's Terraform whitelist/never-list and guardrails, with
these deltas:

- The container runs `smoke_worker.py worker` (long-poll worker); the smoke
  is a SEPARATE one-off `run-task` (or local run) of `smoke_worker.py start`.
  `terraform apply` succeeding proves nothing by itself — the starter's
  printed result is the proof.
- Task queue: `poc-smoke-<run_id>` — never the user's real queues.
- **Connection env contract (explicit — never inferred):**

| Env                                                | Meaning                              |
| -------------------------------------------------- | ------------------------------------ |
| `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`           | always required                      |
| `TEMPORAL_TLS`                                     | `off` / `tls` / `mtls`               |
| `TEMPORAL_API_KEY`                                 | Cloud API-key auth (with `tls`)      |
| `TEMPORAL_TLS_SERVER_NAME`                         | SNI override (self-hosted behind LB) |
| `TEMPORAL_TLS_CA_PATH`                             | custom root CA (self-hosted TLS)     |
| `TEMPORAL_TLS_CERT_PATH` / `TEMPORAL_TLS_KEY_PATH` | client cert/key (`mtls`)             |

- On ECS, the API key and cert/key material come from SSM Parameter Store
  (SecureString) or Secrets Manager via task-definition `secrets` — never
  inline in the task def. `run_local.sh` reads local file paths.
- Teardown wording: `terraform destroy` stops the worker; Temporal **task
  queues are not deletable resources** — the `poc-smoke-<run_id>` queue
  metadata ages out on its own and never touched production queues.
