---
_fragment: outcome-b
_of_phase: scaffold
_contributes:
  - { file: "terraform/", _when: "always when this fragment fires" }
---

# Scaffold Phase: Outcome B (ECS Fargate) or Outcome C's B-Shaped Backend

> Self-contained fragment. Fires when `recommendation.outcome == "B"` (full
> app-surface mode) OR `recommendation.outcome == "C"` with `backend_shape ==
> "B-shaped"` (backend-only mode). **Terraform only in EITHER mode — this
> fragment never emits SST or OpenNext artifacts, unconditionally** (Requirement
> 8.3).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Determine Mode

Read `recommendation.json.outcome`:

- **If `outcome == "B"`:** run in **FULL APP-SURFACE MODE** (Steps 1-4). The
  entire Next.js app (via `next start` in a container) migrates to Fargate.
- **If `outcome == "C"` and `backend_shape == "B-shaped"`:** run in
  **BACKEND-ONLY MODE** (Step 5). The Next.js app stays on Vercel; only the
  separable backend runs on Fargate.

Both modes are Terraform-only — this distinction affects WHAT gets
containerized (the whole app vs. just the backend), not WHICH dialect is used.

---

## Full App-Surface Mode (Outcome B only)

### Step 1: Emit Terraform for the Fargate Stack

Per Requirement 8.3: ECS service running the `next start` container, ALB,
CloudFront in front of it, ECR (container registry), task definitions,
autoscaling configuration. All in Terraform — no SST, no OpenNext, ever, in
this fragment.

**Default the task definition to Graviton (ARM64).** Load
`references/shared/graviton.md` and apply its Terraform mechanics section:
set `runtime_platform { cpu_architecture = "ARM64", operating_system_family =
"LINUX" }` on the `aws_ecs_task_definition`, and note the
`docker buildx build --platform linux/arm64` (or ARM64-native runner)
requirement in `terraform/README.md` per that file's guidance — this is a
build-command note, not a Dockerfile change, for the common Next.js
base-image case.

### Step 2: Wire I1's Outcome-B Remediation (If I1 Was HIGH Severity)

Per `knowledge/preflight-checks.json`'s I1 `severity_rule_by_outcome.B`: if
autoscaling is configured for MORE than 1 task and ISR is present, wire in a
shared cache handler for multi-instance deployments (or, per the alternative
remediation, cache-control headers + CloudFront invalidation instead of
in-process ISR). Do not leave this as a comment-only TODO — provision the
actual Terraform resource (e.g. an ElastiCache-backed shared cache) or wire
the cache-control-header alternative into the container's Next.js config.

If ISR is present but the default single-task deployment doesn't need this
yet (I1 reads LOW at current scale), still make the threshold impossible to
miss later: put the "raising the task count above 1 flips this to HIGH
severity without a shared cache" warning as a comment directly ON the
autoscaling resource/variable that controls task count — not only in
`terraform/README.md` — so a future reader changing that value sees the
warning at the point of change, not only in separate documentation they may
not open.

### Step 3: Wire M1's Remediation (If M1 Was HIGH Severity)

M1 applies to every outcome (Requirement 6.5). Since Outcome B runs
`next start` directly (no edge middleware bundling layer the way OpenNext
has), the remediation here is typically "CloudFront Functions for simple
header/redirect logic" per `knowledge/preflight-checks.json`'s M1
remediations list — wire this in as an actual CloudFront Function resource,
not a placeholder.

### Step 4: Advisory Notes for A-Specific Checks

B1 (lockfile conflicts), B3 (sharp duplication), S1 (streaming empty-body) are
all suppressed/inapplicable on Outcome B per `knowledge/preflight-checks.json`
— do not surface remediations for these in the scaffold; container builds are
tolerant of them (per each check's own `suppressed_on: ["B"]` where
applicable). O1's advisory generalizes to "generic container-build hygiene" —
optionally note this as a comment, not a required resource.

---

## Backend-Only Mode (Outcome C, `backend_shape: "B-shaped"` only)

### Step 5: Emit Terraform-Only Fargate Backend

Emit the same Fargate stack shape as Step 1, but scoped to ONLY the separable
backend surface (`discovery.json.api_routes[]` / `backend_service_detected`) —
not the full Next.js app, which remains on Vercel under Outcome C. The same
Graviton default from Step 1 applies here too.

Document inline: "This backend-only scaffold serves Outcome C (Hybrid) — your
Next.js app and its PR previews remain on Vercel. Only the separable backend
surface below migrates to AWS, as an ECS Fargate service in Terraform."

Wire M1's remediation here too, same as the full app-surface mode's Step 3 —
M1 applies regardless of mode.

---

## Output Contribution for Parent Orchestrator

Terraform files only, in either mode. This fragment NEVER contributes an
`sst.config.ts` key — its absence from this fragment's output is structural,
not situational.

---

## Error Handling

| Error Category                                                                                        | Behavior                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `recommendation.json` is ambiguous about which mode applies                                           | STOP, surface a diagnostic — should have been caught upstream, do not guess                                                                                                  |
| I1's remediation choice (shared cache vs. cache-control headers) is unclear from the founder's inputs | Default to cache-control headers + CloudFront invalidation (the simpler, more broadly compatible option) and note the shared-cache alternative in accompanying documentation |

---

## Scope Boundary

**This fragment covers Outcome B's full-app Fargate scaffold AND Outcome C's
B-shaped backend scaffold ONLY — never emits SST/OpenNext in either mode.**

FORBIDDEN — Do NOT include ANY of:

- Emitting `sst.config.ts` or any OpenNext artifact, ever, in this fragment
- Production-hardening beyond a thin working skeleton (Requirement 8.5)
- Surfacing A-only Pre-Flight remediations (B1/B3/S1) as if they applied here

**Your ONLY job: emit the correct Terraform-only Fargate scaffold for
whichever mode Step 0 determined. Nothing else.**
