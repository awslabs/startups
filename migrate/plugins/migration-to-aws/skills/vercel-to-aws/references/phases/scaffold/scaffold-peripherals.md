---
_fragment: peripherals
_of_phase: scaffold
_contributes:
  - { file: "terraform/", _when: "always - this fragment always runs" }
  - { file: "terraform/README.md", _when: "always - this fragment always runs" }
---

# Scaffold Phase: Peripherals (Always Runs)

> Self-contained fragment. ALWAYS runs regardless of which outcome was
> recommended or which compute fragment (if any) fired — even a `"stay"`
> recommendation may still want a thin peripheral-only carve-out. Applies
> `knowledge/peripheral-mappings.json` to whatever peripherals Discover found,
> and wires M2's CloudFront-header remediation as a thin skeleton.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Load `knowledge/peripheral-mappings.json`

Load the Vercel-peripheral-to-AWS-target table (Blob->S3, Cron->EventBridge
Scheduler, KV->ElastiCache with Upstash noted as a keep-alternative,
Postgres->RDS/Aurora with Neon noted as a keep-alternative, Edge
Config->Parameter Store/AppConfig, env vars->Secrets Manager/SSM).

---

## Step 2: Map Discovered Peripherals

Read `discovery.json.storage_integrations[]` and `peripherals[]`. For each
detected peripheral, look up its mapping and emit the corresponding Terraform
resource as a thin working skeleton — not a fully production-hardened stack
(Requirement 8.5).

**A detected Cron peripheral's EventBridge-Scheduler-triggered Lambda
invoker defaults to Graviton (ARM64).** Load `references/shared/graviton.md`
and apply its Terraform mechanics section: set `architectures = ["arm64"]`
on the `aws_lambda_function`. No other peripheral mapping in this table
(S3, ElastiCache, RDS/Aurora, Parameter Store/AppConfig, Secrets Manager/SSM)
provisions compute this fragment controls the architecture of — this note
applies to the Cron mapping only.

**Under Outcome C specifically, check separability before migrating a
peripheral whose logic lives outside the separable surface.** This fragment
always runs regardless of outcome (per its own frontmatter), but under
Outcome C the Next.js app itself stays on Vercel — only the specific surface
Recommend determined separable (`discovery.json.api_routes[]` /
`backend_service_detected`) migrates. A peripheral can be TECHNICALLY
detected (e.g. a Vercel Cron hitting a route) without that route being part
of the separable surface — migrating the schedule alone would be wrong if
the cron's actual logic depends on app code or data staying on Vercel. When
`recommendation.json.outcome == "C"`, cross-check each detected peripheral's
associated route (if it has one, e.g. a cron hitting a specific API path)
against `discovery.json.api_routes[]`: if the peripheral's route is NOT in
that list, still emit the resource (do not silently withhold it — the
founder may still want it), but flag this explicitly in
`terraform/README.md`'s peripheral table as "not confirmed separable — this
peripheral's associated route was not part of the surface Recommend
determined separable; verify its logic doesn't depend on app code remaining
on Vercel before relying on this resource."

**Respect the "often correct to keep" note:** for KV and Postgres
specifically, the mapping table notes Upstash/Neon are often the right call to
KEEP rather than migrate. Before emitting an ElastiCache/RDS resource for
these, note this alternative explicitly in the accompanying documentation so
the founder can make an informed choice rather than defaulting to "migrate
everything."

---

## Step 3: Wire M2's Remediation (CloudFront Header Mapping)

Per Requirement 8.5's explicit example: if `preflight-findings.json`'s M2
check (geo/IP header dependence) was detected, emit the CloudFront-headers
mapping configuration — mapping Vercel's `x-vercel-ip-*` header conventions to
their CloudFront equivalents — as an actual working configuration snippet
(e.g. a CloudFront Function or Lambda@Edge function performing the header
rewrite), not a comment-only TODO.

**This is harder than a plain header-name substitution — do not undersell
it.** Unlike Vercel, CloudFront does not forward viewer-geolocation data to
the origin/function by default; enabling it (so a CloudFront Function or
Lambda@Edge function can read a `cloudfront-viewer-country`-equivalent value)
requires a distribution-level configuration that is not exposed as a plain
resource argument on `aws_cloudfront_distribution` in the current AWS
provider — it typically needs a response-headers policy or a real-time log
configuration, and the exact mechanism can change between provider versions.
Write the CloudFront Function/Lambda@Edge code assuming the header IS
available, but explicitly call out in `terraform/README.md` that enabling the
underlying distribution setting is a required manual step this scaffold does
not (and, given the AWS provider's current shape, cannot cleanly) automate —
never emit code that silently looks complete but doesn't actually receive the
data it reads.

---

## Step 4: Emit `terraform/README.md`

Regardless of what else fired, ALWAYS emit `terraform/README.md` documenting:

- Which peripherals were mapped and why.
- Which "often correct to keep" alternatives were noted.
- Which Pre-Flight remediations were wired in (M1 if applicable via the
  compute fragment, M2 here, I1 if applicable via the compute fragment).
- The Graviton (ARM64) default applied to compute resources (per
  `references/shared/graviton.md`), including its one advisory note about
  native/compiled Node dependencies beyond `sharp`.
- The interface-behind-which OpenNext v3 sits (Requirement 8.7) — a brief note
  that this scaffold's backend-compute and peripheral logic is structured so a
  future verified Adapter-API-based AWS adapter can replace OpenNext v3
  output without touching assessment/discovery/recommendation logic. This
  does not require an actual abstraction layer to exist in v1's THIN scaffold
  — it means the scaffold's module boundaries (compute vs. peripherals vs.
  the interface points between them) are documented clearly enough that a
  future swap is a scoped, described change, not an archaeological
  discovery.

This file's presence is what `scaffold.md`'s own `_postconditions` checks for
(warn-and-skip if absent, since Scaffold is optional overall — but this
fragment should always produce it when it runs at all).

---

## Output Contribution for Parent Orchestrator

Terraform peripheral resources (keyed by peripheral type) plus
`terraform/README.md`. This fragment's output is always present in
`scaffold-assemble.md`'s merge, regardless of what the compute fragments
contributed (or didn't).

---

## Error Handling

| Error Category                                          | Behavior                                                                                               |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| A detected peripheral has no entry in the mapping table | Note it explicitly as unmapped in `terraform/README.md`, do not fabricate a mapping                    |
| M2 was not detected                                     | Skip Step 3 entirely — do not speculatively emit header-mapping config for a check that wasn't flagged |

---

## Scope Boundary

**This fragment covers peripheral mapping and M2's remediation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Next.js app hosting scaffold (that is the compute fragments' job, or
  explicitly NOT emitted at all under Outcome C / stay)
- Production-hardening beyond a thin working skeleton
- Silently migrating a peripheral the mapping table flags as "often correct
  to keep" without noting the alternative

**Your ONLY job: map peripherals, wire M2's remediation, always emit
`terraform/README.md`. Nothing else.**
