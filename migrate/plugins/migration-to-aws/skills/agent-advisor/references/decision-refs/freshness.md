# Volatile Facts & Freshness

**Outbound-query rule (applies to every channel below — MCP, WebFetch, or CLI):**
freshness lookups carry ONLY public service, feature, model, or region names (e.g.
"AgentCore session cap", "Lambda MicroVMs launch TPS"). Never include user code,
file contents, prompts, architecture details, or anything else from the workspace
or the run directory in an outbound request — the answer never depends on it.

## Fields to verify at runtime via the awsknowledge MCP

- AgentCore microVMs session cap (currently 8h) and Instances session cap (currently 14d)
- AgentCore microVMs compute cap (2 vCPU / 8 GB; Instances lifts it via EC2 choice)
- AgentCore / AgentCore Instances / Lambda MicroVMs region availability (Instances
  launched 2026-08 in a limited region set)
- AWS Agent Registry region availability when Registry is selected, independently of runtime
  (`registry_regions` in `references/runtimes/agentcore.json`; see the procedure below)
- Lambda MicroVMs launch TPS (5, not adjustable)
- FedRAMP certification status for AgentCore and Lambda MicroVMs
- Any Bedrock model price (defer to migration-to-aws pricing cache; never hardcode here)

## Temporal (design.md — Freshness, temporal units only)

Volatile facts to re-verify when the Temporal branch generates a plan. The awsknowledge
MCP does not cover Temporal-side facts; each fact below names its actual verification
channel. Whatever cannot be verified this run stays cached and the footer must say so.

**WebFetch (primary and only channel for Temporal-side facts):**
Use WebFetch to retrieve the relevant `docs.temporal.io` page directly. This is the
primary (and only) channel for the **Feature statuses** fact below — no MCP server,
no auth step. Tradeoff accepted: the former `temporal-docs` kapa.ai MCP synthesized
answers across Temporal docs, forum, and Slack; WebFetch reads a single docs page —
a slightly narrower source, but the feature-status facts needed here live on
`docs.temporal.io`. The anti-fabrication rule applies: a fact counts as verified
only if the WebFetch actually returned it this run.

- Scope note: WebFetch covers Temporal **platform** knowledge only. The Marketplace
  listing / commercial-terms fact below is AWS buyer-side and stays WebFetch-only —
  fetch that page separately from `docs.temporal.io`.

**Verifiable this run (attempt these):**

- **Marketplace listing + commercial terms** — fetch
  `https://aws.amazon.com/marketplace/pp/prodview-xx2x66m6fp2lo` (public page, no auth).
  Confirm: listing resolves (not 404/redirect to search), product name still
  "Temporal Cloud (Pay-as-you-Go)", the $0.01/action pricing dimension, free trial.
  (The Marketplace Catalog API cannot do this — it is seller-scoped; the public page is
  the only buyer-side channel.)
- **Feature statuses** (Serverless Workers, Workflow Streams, External Payload Storage,
  Worker Versioning) — WebFetch the relevant `docs.temporal.io` page. CAUTION for
  Serverless Workers: the docs label has moved before without a GA announcement (it read
  "Available" in 2026-07 while the feature was still pre-release; it reads "Public
  Preview" as of 2026-08) — a docs label alone does NOT upgrade it to GA — keep the
  Public Preview label until the user shows GA evidence (e.g. a GA announcement post).

**Not verifiable (always cached):**

- $1,000 credits / SCMP / Vendor Insights details beyond what the listing page shows.
- "No official cross-cluster history migration tool" — absence is unprovable by lookup;
  restate as of the last-verified date.

The anti-fabrication rule below applies unchanged: only facts actually fetched and
observed this run may be listed as verified.

## Procedure

1. Identify the volatile facts to check: for the main skill, the `volatile_facts` entries
   (`verify_via_mcp: true`) from the winning runtime's profile JSON; for **add-capabilities**
   (which has no winning runtime profile), the "Hard limits" facts in the relevant service card
   (agentcore.md) instead.
   Check Registry facts only when `registry` is selected. In the main skill, include
   `registry_regions` from `references/runtimes/agentcore.json` even if the winning runtime is
   ECS, EKS, Lambda, or another runtime. In add-capabilities, use the Registry Hard limits entry.
2. Attempt an awsknowledge MCP lookup for each.
3. On success (the MCP call returned a value THIS run), use the fresh value and list the field as
   verified.
4. On failure OR if you did not call the MCP at all (unavailable, skipped), use the cached
   `value` and list the field as fallen-back.

**Anti-fabrication rule (do not skip):** a field may appear in the "verified via MCP" list ONLY
if you actually made an MCP call this run and observed its result. If you did not call the MCP
for a field — for any reason — it goes in the cached/fell-back list. Never claim verification you
did not perform. If the MCP was not called at all, the verified list is empty and every field is
cached.

## AWS Agent Registry availability

Apply this check whenever Registry is selected, regardless of the agent's runtime:

1. Identify the intended Registry deployment Region. Use the user's stated Region; ask if it
   is missing, unknown, `multi`, or `global`. Do not silently choose a Region.
2. Refresh Registry availability via awsknowledge MCP using the procedure above. A Runtime
   availability result cannot verify Registry. Keep the observed source and verification date
   with the result; on failure retain the cached snapshot date and mark availability unconfirmed.
3. If this run confirms availability in the intended Region, proceed. If unavailable, ask the
   user to omit Registry or explicitly choose a supported Region after considering data
   residency. Do not silently move Registry or change the compute runtime.
4. If availability cannot be verified, keep Registry conditional and include an availability
   warning; do not present it as available or ready to deploy. Ask whether to omit Registry or
   leave the recommendation as a draft pending verification. Do not complete Design or
   add-capabilities while a selected Registry's intended Region remains unavailable or unverified.

The main flow records the result in `design.json.volatile_facts.registry_regions` and appends
any warning, with the affected unit and Region, to `warnings` and `region_availability_note`.
The add-capabilities branch records the Region, verification result, and any unresolved warning
in `capabilities-recommendation.md`. Only a lookup observed this run counts as verified.

## Freshness footer template (append to every recommendation doc)

Choose the wording that matches what actually happened:

- If some fields were MCP-verified this run:
  > _Generated `<DATE>`. Facts verified via AWS Knowledge MCP: `<list verified>`. Cached values used
  > for: `<list cached>`. Limits and pricing change — verify against AWS docs before committing._
- If the MCP was not called / unavailable:
  > _Generated `<DATE>`. AWS Knowledge MCP not called this run; all facts are cached values —
  > verify against AWS docs before committing._

The footer is a summary, not the only place a date belongs. A cached number quoted in the body —
a service limit, a scaling ceiling, a price anchor — carries its own snapshot date at the point of
use, so a reader who reads one section is not relying on a footer they may never reach.

## Pre-scoring verification contract

Before scoring, inspect every matching runtime hard constraint marked `verification_required`. Do not place verification records in `seed.json` or `answers.json`: those files are reusable workload input and cannot prove that a lookup happened in this run.

After this run observes a verification result, write `$RUN_DIR/current-run-verifications.json` using `scripts/schemas/current-run-verifications.json`:

```json
{
  "artifact_type": "agent-advisor.current-run-verifications",
  "schema_version": 1,
  "run_id": "<the $RUN_DIR directory name>",
  "verifications": {
    "<verification_key>": {
      "status": "verified",
      "source": "https://docs.aws.amazon.com/...",
      "value": "<canonical observed value>"
    }
  }
}
```

The artifact is run-materialized evidence: write it only after this run actually observes the source, and validate it before scoring. `score_units.py` verifies that its `run_id` matches the directory containing `answers.json`; absent or invalid evidence is ignored only by leaving the result provisional, while a mismatched artifact is a hard error. A verified record must use a public AWS documentation URL that exactly matches a constraint's `verification_sources`, and its `value` must exactly match that constraint's `verification_expected_value`. Otherwise omit the verified record or record `not_verified`/`failed`.

One verification key represents exactly one service claim. Do not use CPU/memory evidence to certify GPU support, or a general service page to certify an unobserved limit. A changed observed value is evidence that the static profile needs review, not permission to apply the old elimination.

Cached profile values, a prior run, and unobserved documentation are useful context but are not current-run verification. They cannot hard-eliminate a runtime and cannot support final pricing, availability, quota, or I/O-wait billing claims. The scorer therefore emits deferred verification requirements (including the exact expected value) and a `provisional` recommendation until valid run-materialized evidence is supplied. This procedure is mandatory before any final recommendation or release decision.
