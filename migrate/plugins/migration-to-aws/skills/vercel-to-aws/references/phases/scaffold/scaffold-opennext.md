---
_fragment: outcome-a
_of_phase: scaffold
_contributes:
  - { file: "sst.config.ts", _when: "recommendation.outcome is 'A' (full app-surface mode, not the C-recursion)" }
  - { file: "terraform/", _when: "always when this fragment fires" }
---

# Scaffold Phase: Outcome A (OpenNext/SST) or Outcome C's A-Shaped Backend

> Self-contained fragment. Fires when `recommendation.outcome == "A"` (full
> app-surface mode) OR `recommendation.outcome == "C"` with `backend_shape ==
> "A-shaped"` (backend-only serverless-compute mode). **These two modes emit
> DIFFERENT artifacts — read Step 0 carefully before proceeding.**

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Determine Mode (Critical — Do Not Skip)

Read `recommendation.json.outcome`:

- **If `outcome == "A"`:** run in **FULL APP-SURFACE MODE** (Steps 1-4 below).
  The Next.js app itself is migrating; emit SST/OpenNext for the app surface
  plus Terraform for peripherals.
- **If `outcome == "C"` and `backend_shape == "A-shaped"`:** run in
  **BACKEND-ONLY MODE** (Step 5 below, skip Steps 1-4 entirely). The Next.js
  app stays on Vercel under Outcome C (Requirement 7.2) — this mode NEVER
  emits `sst.config.ts` or any OpenNext artifact. It emits ONLY a Terraform
  serverless backend (API Gateway + Lambda) for whatever was determined
  separable. Emitting SST here would be a direct violation of Requirement 7.2
  and the design.md engine's explicit "never emit a partial OpenNext/SST
  scaffold" rule — if you find yourself about to write `sst.config.ts` while
  in this mode, STOP, that is a bug.

---

## Full App-Surface Mode (Outcome A only)

### Step 1: Emit `sst.config.ts` (SST/OpenNext)

Per Requirement 8.2: emit the Next.js app surface via SST/OpenNext — server
functions, CloudFront, ISR tag cache AND revalidation queue **provisioned
together** (never just the incremental cache alone — this directly remediates
Pre-Flight Check I1's Outcome-A severity rule), image optimization.

Document this inline, in the scaffold's own README or a comment at the top of
`sst.config.ts`:

> "This app surface uses SST/OpenNext rather than hand-written Terraform. This
> is an explicit, outcome-scoped exception to this plugin's Terraform-first
> convention (see Requirement 8.2) — SST/OpenNext is OpenNext's happy path for
> the Next.js app; wrapping it in Terraform would produce a worse artifact.
> Terraform owns everything else (peripherals, below)."

**Default the server function to Graviton (ARM64).** Load
`references/shared/graviton.md` and apply its SST mechanics section: set
`server: { architecture: "arm64" }` on the `sst.aws.Nextjs` component. Do NOT
attempt to set an `architecture` override on `imageOptimization` or the ISR
revalidation function — SST's `Nextjs` component does not expose that prop
there; leave those on SST's own default.

### Step 2: Wire M1's Remediation (If M1 Was HIGH Severity)

If `preflight-findings.json`'s M1 check was HIGH severity, wire in the
OpenNext external-middleware option (one of M1's documented remediations,
specifically called out as "OpenNext external middleware option (A only)" in
`knowledge/preflight-checks.json`) as a thin, working configuration — not a
comment-only TODO.

**This setting lives in a SEPARATE `open-next.config.ts` file, not in
`sst.config.ts` itself.** Create (or update) `open-next.config.ts` at the
project root, sibling to `sst.config.ts`, exporting a default object
satisfying OpenNext's `OpenNextConfig` type (import from
`@opennextjs/aws/types/open-next.js` — this is the current package name;
older references to a bare `open-next` package name are stale) with
`middleware: { external: true }`. SST's `sst.aws.Nextjs` component picks up
this file automatically when present; do not attempt to express this setting
as an `sst.config.ts` transform or prop — no such option exists there. Since
OpenNext's own API surface can change between versions, verify the current
config shape against OpenNext's docs (`opennext.js.org/aws/inner_workings/
components/middleware` and `opennext.js.org/aws/config/reference`) before
emitting this file rather than relying on a memorized shape — a wrong import
path or property name here fails silently at build time, not at review time.

### Step 3: Wire B1-B4/S1/O1 Remediations (As Applicable)

For each of B1 (monorepo lockfile conflicts), B2 (Yarn packageManager pin), B3
(sharp direct dependency), B4 (bundle contamination), S1 (streaming empty-body
risk), O1 (build environment consistency) that was flagged as detected in
`preflight-findings.json`: wire the corresponding remediation from
`knowledge/preflight-checks.json` into the scaffold or its accompanying
documentation (e.g. an `outputFileTracingExcludes` suggestion for B4, a CI-only
deploy note for O1).

### Step 4: Emit Terraform Peripherals

Emit Terraform for anything NOT covered by SST/OpenNext: this is handled by
`scaffold-peripherals.md` (always runs, Step 3 of `scaffold.md`) — this
fragment does not duplicate that work, but DOES need to ensure `sst.config.ts`
and the Terraform peripherals reference each other correctly (e.g. the
Terraform-managed RDS instance's connection string surfaced as an SST secret).

---

## Backend-Only Mode (Outcome C, `backend_shape: "A-shaped"` only)

### Step 5: Emit Terraform-Only Serverless Backend

Per Requirement 7.2 and the recommendation engine's explicit rule: emit
serverless backend compute (API Gateway + Lambda) in Terraform ONLY, covering
whatever `discovery.json.api_routes[]` / `backend_service_detected` determined
separable. NO SST. NO OpenNext. NO `sst.config.ts` file, ever, in this mode.

**Default the Lambda function(s) to Graviton (ARM64).** Load
`references/shared/graviton.md` and apply its Terraform mechanics section:
set `architectures = ["arm64"]` on each `aws_lambda_function`.

Document inline: "This backend-only scaffold serves Outcome C (Hybrid) — your
Next.js app and its PR previews remain on Vercel. Only the separable backend
surface below migrates to AWS, as API Gateway + Lambda in Terraform."

Wire M1's remediation here too if flagged — M1 applies to ALL outcomes
(Requirement 6.5), including this backend-only mode, since the backend's own
routes may still intersect with any CDN-cacheable paths.

---

## Output Contribution for Parent Orchestrator

**Full app-surface mode:** contributes `sst.config.ts` plus whatever Terraform
peripheral wiring this fragment needs to hand off to
`scaffold-peripherals.md`.

**Backend-only mode:** contributes ONLY Terraform files (no `sst.config.ts`
key in the contribution at all — its absence is itself meaningful, and
`scaffold-assemble.md`'s completion gate checks for this).

---

## Error Handling

| Error Category                                                                                                   | Behavior                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `recommendation.json` is ambiguous about which mode applies (e.g. `backend_shape` missing when `outcome == "C"`) | STOP this fragment, surface a diagnostic — this should have been caught by `recommend`'s own postconditions; do not guess |
| A Pre-Flight Check remediation conflicts with another (rare)                                                     | Note the conflict explicitly in the scaffold's accompanying documentation, apply the higher-severity one                  |

---

## Scope Boundary

**This fragment covers Outcome A's app-surface scaffold AND Outcome C's
A-shaped backend scaffold ONLY — never both in the same run.**

FORBIDDEN — Do NOT include ANY of:

- Emitting `sst.config.ts` while in Backend-Only Mode (a hard rule, not a
  preference)
- Production-hardening beyond a thin working skeleton (Requirement 8.5)
- Re-running the Recommendation Engine

**Your ONLY job: emit the correct scaffold for whichever mode Step 0
determined. Nothing else.**
