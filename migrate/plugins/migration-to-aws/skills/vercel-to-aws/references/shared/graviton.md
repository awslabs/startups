---
_shared: graviton
---

# Shared: Graviton (ARM64) Default for Scaffold Compute

> Loaded by `scaffold-opennext.md`, `scaffold-fargate.md`, and
> `scaffold-peripherals.md` — single canonical source for this skill's
> ARM64-by-default decision, per this plugin's "shared warnings exist in one
> canonical file" convention (`SKILL.md` § Context Loading Rules). Ported from
> `gcp-to-aws`'s Graviton feature, scoped down: this skill's compute is
> homogeneous Node.js/Next.js (no polyglot compatibility-tier table needed),
> so there is no Clarify question — the default applies unconditionally.

---

## The Default

Every compute resource this skill's Scaffold checkpoint emits (the SST/OpenNext
server function, the Terraform-only backend Lambda under Outcome C's A-shaped
mode, the ECS Fargate task under Outcome B or C's B-shaped mode, and the
EventBridge-Scheduler-triggered Lambda invoker for a detected Cron peripheral)
SHOULD default to **ARM64 (Graviton)** rather than x86_64. Node.js is a
Graviton-"ready" runtime with no code changes required — this is not a
Clarify-gated decision the way gcp-to-aws's Q11b is for its polyglot workload
mix; it applies unconditionally here because every compute fragment in this
skill runs the same runtime (Node.js, via `next start` or a Lambda handler).

**Do not ask the founder about this.** Adding a Clarify question for this
would be a 6th fixed question purely to confirm a default that has no real
counter-signal in this skill's fixed workload shape — this skill's 5-question
minimalism (Requirement 3.1) is deliberate; do not erode it for a decision
that's safe to default silently, the same way `db.t4g`-class defaults are
applied without a question elsewhere in this plugin.

## The One Relevant Compatibility Signal This Skill Already Detects

`tier1-signals.json.has_sharp_dependency` (Pre-Flight Check B3's detection
input) is the only native/compiled Node dependency this skill's PreScan
already looks for. `sharp` ships prebuilt ARM64 Linux binaries
(`@img/sharp-linux-arm64`) — it is NOT a Graviton blocker. Do not treat
`has_sharp_dependency: true` as a reason to fall back to x86_64.

**Residual risk, advisory only, never a gate:** this skill has no detection
signal for OTHER native/compiled Node dependencies (e.g. a hand-rolled
native addon, a niche package with no prebuilt ARM64 binary) — PreScan's
fixed scan does not check for this generally, and adding such a check is out
of scope for this pass. Note this as a one-line advisory in
`terraform/README.md` wherever this file's guidance is applied: "This
scaffold defaults compute to ARM64 (Graviton) for lower per-hour pricing. If
your dependencies include a native/compiled Node addon beyond `sharp`
(already verified ARM64-compatible), confirm it ships an ARM64 build before
deploying." Never block scaffold generation on this — it is a note, not a
precondition.

## What This Default Does NOT Do

- **Does not model performance uplift.** If a founder-facing cost figure
  exists anywhere in this skill's output, it must model ONLY the ARM64 hourly
  price differential, never a throughput/performance claim — this skill has
  no Estimate phase (full cost estimation is Out of Scope for v1 per
  `requirements.md`), so in practice this default has no dollar-figure
  consequence to word carefully today; this constraint exists so a future v2
  Estimate phase inherits the same discipline gcp-to-aws's Graviton feature
  applies, not because v1 currently renders such a figure.
- **Does not touch the report.** This is a Scaffold-checkpoint-only decision.
  `report-render.md` never mentions architecture/Graviton — Scaffold is
  optional and off-backbone; a founder who declines the checkpoint never sees
  this default at all.

## Terraform / SST Mechanics (Verified — Do Not Guess a Different Shape)

- **`aws_ecs_task_definition`** (Outcome B full app-surface, and Outcome C's
  B-shaped backend-only mode): set
  `runtime_platform { cpu_architecture = "ARM64", operating_system_family = "LINUX" }`.
  The container image itself must be built for ARM64 — a plain
  `docker build` on an x86_64 CI runner produces an x86_64 image regardless of
  this Terraform setting; note in `terraform/README.md` that the build step
  needs `docker buildx build --platform linux/arm64` (or an ARM64-native
  runner) alongside this setting, or the task will fail with an exec-format
  error at container start, not at `terraform apply`. Common Next.js base
  images (e.g. `node:22-alpine`) already publish multi-arch manifests, so this
  is a build-command change, not a Dockerfile rewrite, in the common case.
- **`aws_lambda_function`** (Outcome C's A-shaped backend-only mode via
  Terraform, and the Cron peripheral's EventBridge-triggered invoker in
  `scaffold-peripherals.md`): set `architectures = ["arm64"]`.
- **`sst.config.ts`'s `sst.aws.Nextjs` component** (Outcome A full app-surface
  mode): set `server: { architecture: "arm64" }`. This prop exists on
  `server` (the app's own server function) only — SST's `Nextjs` component
  does NOT expose an `architecture` override on `imageOptimization` or the
  ISR revalidation function; leave those on SST's own default rather than
  inventing a config key that doesn't exist (verified against
  `sst.dev/docs/component/aws/nextjs/` — do not assume parity across every
  sub-function just because `server` exposes it).

## Error Handling

| Error Category                                                                                              | Behavior                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Founder's own Dockerfile/base image is explicitly x86_64-only (rare, unverifiable from this skill's inputs) | Note the ARM64 default in `terraform/README.md` as usual, but flag it as worth confirming rather than silently overriding — this skill has no signal to detect this case itself |
| A future compute fragment is added that this file doesn't yet cover                                         | Extend this file's Terraform/SST Mechanics section rather than duplicating the default's rationale inline in the new fragment                                                   |
