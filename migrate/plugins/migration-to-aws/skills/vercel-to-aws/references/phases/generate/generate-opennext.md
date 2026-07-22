---
_fragment: compute-opennext
_of_phase: generate
_contributes:
  - { file: "sst.config.ts", _when: "recommendation.outcome is 'A' (full app-surface mode)" }
  - terraform/cdn.tf
---

# Generate Phase: Outcome A (OpenNext/SST)

> Self-contained compute fragment. Fires ONLY when `recommendation.json.outcome
> == "A"`. Emits `sst.config.ts` for the Next.js app surface via SST/OpenNext,
> plus `terraform/cdn.tf` for the CloudFront distribution. This is the ONE
> exception to the Terraform-first convention — SST/OpenNext is OpenNext's happy
> path for Next.js on AWS, and wrapping it in Terraform would produce worse output.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Emit `sst.config.ts`

Emit `$MIGRATION_DIR/sst.config.ts` with a complete SST/OpenNext configuration:

- Server functions (the Next.js app surface)
- CloudFront distribution
- ISR tag cache AND revalidation queue provisioned TOGETHER (never just the
  cache alone — this directly remediates Pre-Flight Check I1)
- Image optimization

**Default server function to Graviton (ARM64).** Load
`references/shared/graviton.md` and apply its SST mechanics: set
`server: { architecture: "arm64" }` on the `sst.aws.Nextjs` component.

Document the SST exception inline:

```typescript
// This app surface uses SST/OpenNext rather than hand-written Terraform.
// This is an explicit, outcome-scoped exception to this plugin's Terraform-first
// convention — SST/OpenNext is OpenNext's happy path for Next.js; wrapping it
// in Terraform would produce a worse artifact. Terraform owns everything else
// (baseline, VPC, peripherals, security).
```

---

## Step 2: Wire M1 Remediation (If Applicable)

If `preflight-findings.json`'s M1 check (edge middleware) was HIGH severity:

Create `$MIGRATION_DIR/open-next.config.ts` (separate from `sst.config.ts`):

```typescript
import type { OpenNextConfig } from "@opennextjs/aws/types/open-next.js";

const config: OpenNextConfig = {
  middleware: { external: true },
};

export default config;
```

SST's `sst.aws.Nextjs` picks this up automatically when present.

---

## Step 3: Wire B1-B4/S1/O1 Remediations (As Applicable)

For each Pre-Flight Check flagged as detected in `preflight-findings.json`:

- **B1 (monorepo lockfile):** Add `outputFileTracingExcludes` note in docs
- **B3 (sharp dependency):** Confirm ARM64 prebuilt binaries ship with sharp
  (they do — note this as resolved by Graviton default)
- **B4 (bundle contamination):** Add `outputFileTracingExcludes` config
- **S1 (streaming empty-body):** Note SST/OpenNext handles streaming natively
- **O1 (build env consistency):** Add CI-only deploy note in docs

---

## Step 4: Emit `terraform/cdn.tf`

Emit a CloudFront distribution resource that references the SST deployment's
origin. This is a thin configuration — SST manages the full CDN setup, but
having the distribution declared in Terraform allows the peripheral fragments
to attach behaviors (e.g. M2's header mapping CloudFront Function).

---

## Output Contribution for Parent Orchestrator

`sst.config.ts` + `terraform/cdn.tf`. Optionally `open-next.config.ts` when
M1 is HIGH severity.

---

## Scope Boundary

**This fragment covers Outcome A's SST/OpenNext app-surface scaffold and
CloudFront distribution ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Terraform compute resources (ECS, Lambda) — this outcome uses SST
- Peripheral resources (those are `generate-peripherals.md`'s job)
- Firing alongside `compute-fargate` or `compute-lambda`
- Emitting under any outcome other than `"A"`

**Your ONLY job: emit SST/OpenNext for the app surface. Nothing else.**
