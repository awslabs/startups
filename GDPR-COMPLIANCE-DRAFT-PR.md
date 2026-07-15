# Draft PR: Enforce declared GDPR data-residency constraints in gcp-to-aws (Clarify, Design, Generate, Report)

**Status:** Draft for review — not yet implemented. Sharing scope and approach before writing code.

**Plugin:** `migrate/plugins/migration-to-aws/skills/gcp-to-aws/`

**Framing:** This PR enforces the **data-residency / replication policy already advertised in Q2** when the user selects GDPR. It does **not** claim to make a migration "GDPR compliant." The plugin remains an architecture-and-IaC assistant: residency gates + honest disclosure, not a privacy-program product.

---

## Problem

`clarify-global.md` Q2 lets a user select GDPR as a compliance requirement, and states the intended policy directly in its own impact table:

> "GDPR: EU regions required (eu-west-1, eu-central-1), data residency constraints, no cross-region replication outside EU without explicit consent"

Almost nothing downstream reads `compliance` for `"gdpr"` as an architecture constraint:

- **Design** never validates `target_region` (from Q1) against the EU-only constraint Q2 promised. A user can select GDPR in Q2, have Q1 resolve to `us-east-1` (default, or via discovery auto-extract from a non-EU GCP region), and Design will proceed without any flag.
- **No design-ref gates cross-region replication** (S3 CRR, Aurora Global Database, multi-region compute from Q1="Global") against the "no replication outside EU without consent" rule — despite that rule being stated as policy in Q2's own table.
- **`generate-artifacts-infra.md`'s compliance-conditional block** (Config, Security Hub, KMS CMK, Secrets Manager rotation, S3 access logging) triggers only on `soc2|pci|hipaa|fedramp` — GDPR is excluded. That exclusion is already partially intentional today (`gdpr` maps to 365-day CloudTrail retention; GDPR-only stacks are explicitly kept out of Config/Security Hub in the self-check), but the "no account-control expansion" rationale is not documented in the baseline header or report the way other frameworks are.
- **`org-recommendation-engine.md`** explicitly folds GDPR into "no compliance" for the single-account default (`"None or GDPR-only"` as one bucket). Also fine as a policy, but stated nowhere as intentional.
- **Migration report Appendix G** ("what the baseline does NOT cover") lists caveats for SOC2, HIPAA, PCI, and FedRAMP — GDPR has no equivalent line.

Net effect: selecting GDPR in Clarify is mostly decorative for architecture. It's recorded in `preferences.json` and does not drive region/replication decisions that Q2 promised.

**Related, out of scope for this PR:** FedRAMP has the identical gap — its "GovCloud regions required" policy in the same Q2 table is likewise never enforced anywhere downstream. Flagging this so it isn't mistaken for something this PR fixes; it should be its own PR (GovCloud has additional considerations: endpoint availability, limited service catalog) beyond a region allowlist check. The gate mechanism can be generalized later (e.g. `compliance_region_policy`) if useful.

---

## Scope

**In scope:**

1. Shared EU region allowlist + closest-EU mapping (single source of truth)
2. Align Q2 impact/interpret text with that allowlist (so policy text matches enforcement)
3. Clarify-phase GDPR region cross-check (hard stop + A/B/C resolution — not a soft warning)
4. Design-phase fail-closed gate if Clarify left an inconsistent state
5. Cross-region replication gates for GDPR (S3 CRR, Aurora Global Database, multi-region compute) keyed off an explicit acknowledgment flag
6. Explicit, documented decision on GDPR's relationship to `baseline.tf` (no Config/Security Hub for GDPR-only) — documentation note, not new Terraform resources
7. GDPR line in Appendix G + mandatory Section 4 callout (especially loud when the user acknowledged a non-EU / cross-border exception)
8. Document the org-recommendation-engine's `"None or GDPR-only"` grouping (no behavior change)

**Out of scope (permanently for this plugin, not just this PR):**

- Claiming or generating "GDPR compliance" (DPA, RoPA, DPIA, DSAR workflows, EU representative, lawful basis analysis)
- Per-service "is this personal data?" classification
- SCC / transfer-mechanism validation beyond user self-acknowledgment
- New Terraform resources for GDPR

**Out of scope (follow-ups):**

- FedRAMP's equivalent GovCloud enforcement gap (separate PR)
- CCPA (Q2 option G) — no stated region/replication policy exists for it today
- Heroku-to-aws skill parity (confirm separately; keep this diff reviewable)
- Inventing unavailable services in a chosen EU region — reuse existing regional availability checks so mappings don't target services missing in e.g. `eu-south-2`

---

## Design decisions (resolved in review)

| Topic                       | Decision                                                                                                                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Product framing             | Residency/replication enforcement + disclosure. Not "GDPR compliance."                                                                                                                             |
| Region mismatch UX          | **Hard stop + reprompt** (options A/B/C). Soft warning would recreate the decorative checkbox.                                                                                                     |
| Exception path (option B)   | Allowed, but **loud**: record acknowledgment, Design `warnings[]`, and mandatory migration-report Section 4 callout.                                                                               |
| Allowlist location          | Single shared file; Q2 table/interpret updated to match. No duplicated lists.                                                                                                                      |
| Closest-EU suggestion       | Deterministic mapping table from common GCP / non-EU AWS regions → suggested EU region (used in option A prompt).                                                                                  |
| Acknowledgment field        | Boolean self-attest is enough for v1. Rename away from "consent" legal language: `cross_border_transfer_acknowledged`. Record _what_ was acknowledged. Do **not** imply the plugin validated SCCs. |
| FedRAMP in this PR          | **No** — separate PR. Same pattern, different product surface.                                                                                                                                     |
| `baseline.tf` for GDPR-only | No Config/Security Hub. Document that as intentional (header note + Appendix G).                                                                                                                   |

---

## Proposed changes by file

### 0. NEW: `references/shared/gdpr-region-allowlist.md`

Single source of truth. All Clarify / Design / design-ref rules **reference this file**; do not inline the list elsewhere.

Contents:

1. **EU region allowlist** (AWS `eu-*` commercial regions):
   - `eu-west-1`, `eu-west-2`, `eu-west-3`
   - `eu-central-1`, `eu-central-2`
   - `eu-north-1`
   - `eu-south-1`, `eu-south-2`

2. **Closest-EU mapping** (deterministic; used when presenting option A). At minimum cover:
   - Common GCP regions → suggested AWS EU region (e.g. `europe-west1` → `eu-west-1`, `europe-west3` → `eu-central-1`, `us-central1` / `us-east1` → `eu-west-1` as default suggestion)
   - Non-EU AWS regions → suggested EU region (e.g. `us-east-1` → `eu-west-1`, `ap-southeast-1` → `eu-central-1`)
   - Fallback when unmapped: `eu-west-1`

3. **Usage note:** This allowlist is a **plugin policy for declared GDPR migrations**, not legal advice. UK (`eu-west-2` is London / EU commercial partition naming — keep as listed) and Switzerland are not separately modeled in v1; do not invent extra partitions without an explicit follow-up.

Also update Q2's impact table and interpret block in `clarify-global.md` so they cite this allowlist (or "all AWS `eu-*` regions per `gdpr-region-allowlist.md`") instead of only `eu-west-1` / `eu-central-1`. **Policy text and enforcement must match in the same PR.**

### 1. `references/phases/clarify/clarify-global.md` (Q1 / Q2 interaction)

Currently Q1 and Q2 are independent questions with no cross-check. Add an explicit ordering note: if Q2 resolves to include `"gdpr"` and Q1's extracted/selected region is outside the EU allowlist, do not silently accept — hard-stop for re-confirmation before Clarify completes.

**Also update** the GDPR row in the Q2 impact table and the `F ->` interpret line so they no longer hardcode only `eu-west-1, eu-central-1`; point at the shared allowlist.

Add a new interaction rule near Q1/Q2:

> **GDPR region cross-check:** If `compliance` (Q2) includes `"gdpr"` and the resolved `target_region` (Q1, whether extracted or user-selected) is not in the EU region allowlist (`references/shared/gdpr-region-allowlist.md`), do not proceed to write `preferences.json` as final. Present:
>
> _"You selected GDPR (data residency). Your target region is `{region}`, which is outside the EU allowlist this skill enforces for GDPR-declared migrations. This tool does not determine whether your processing is lawful — it only enforces the residency policy stated in Q2. Would you like to:_
>
> - _[A] Switch target region to `{closest EU region}` (from allowlist mapping)_
> - _[B] Acknowledge that you are proceeding with a non-EU primary region and that any cross-border transfer mechanism (e.g. SCCs) is documented **outside this tool** — this skill will not validate that mechanism_
> - _[C] Revisit Q2 compliance selection"_
>
> Record the resolution in `preferences.json` (see Schema below).

This mirrors existing hard-gate patterns in Clarify (e.g. mandatory-Clarify-before-Design), so it should read as consistent rather than a new mechanism.

### 2. `references/phases/clarify/clarify.md` (Validation Checklist / Step 2 extraction)

Add the GDPR region cross-check as an explicit item in whatever validation runs before Clarify writes `phases.clarify: "completed"` — so this can't be skipped by choosing "use defaults for the rest" partway through the wizard. If the user skips remaining questions after Q2 answered GDPR but before Q1 is confirmed, the default region logic must still route through the EU allowlist, not the generic "closest AWS region to GCP source region" default.

### 3. `references/phases/design/design-infra.md` (or wherever the Design orchestrator's precondition checks live — confirm exact file during implementation)

Add a **Design-phase precondition check**, run before any resource mapping begins:

> If `preferences.json → compliance` includes `"gdpr"`, and `preferences.json → target_region` (or equivalent resolved field) is not in the EU region allowlist, and `metadata.gdpr_region_resolution` is not `"cross_border_acknowledged"`: **STOP**. Emit `GATE_FAIL | phase=design | field=target_region | reason=gdpr_region_mismatch`. Output: "GDPR was declared but the target region ({region}) is outside the EU allowlist and no cross-border acknowledgment was recorded. Re-run Clarify to switch region, revise compliance, or acknowledge a documented transfer mechanism outside this tool."

This is a fail-closed gate, consistent with the existing `handoff-gates.md` pattern (`GATE_FAIL` / `HANDOFF_OK`).

When `gdpr_region_resolution` **is** `"cross_border_acknowledged"`, Design proceeds but **must** emit a high-visibility entry in `aws-design.json → warnings[]` summarizing the non-EU primary region and that transfer legality was user-acknowledged, not tool-validated.

### 4. `references/design-refs/storage.md` and `references/design-refs/database.md`

Add a GDPR-conditional rule to each, following the same pattern already used for PCI/HIPAA/FedRAMP conditional rules in `generate-artifacts-infra.md`'s domain table:

- **storage.md**: When `compliance` includes `"gdpr"`, do not select S3 Cross-Region Replication targeting a non-EU region unless `cross_border_transfer_acknowledged.value == true`. If the source GCP config has multi-region storage (`google_storage_bucket.location = "EU"` dual/multi-region, or explicit non-EU secondary) and acknowledgment is absent, map to single-EU-region S3 with a `warnings[]` entry: `"Source GCS bucket is multi-region; GDPR declared without cross-border acknowledgment — mapped to single EU region S3. Confirm data residency requirements."` If acknowledgment is present, allow CRR as without GDPR, and record in warnings what non-EU target was unlocked.
- **database.md**: When `compliance` includes `"gdpr"` and Q1/Q6 would otherwise select Aurora Global Database or any multi-region database topology, require the same acknowledgment flag. Absent acknowledgment, cap topology at `multi-az-ha` (single EU region) regardless of Q1="Global" + Q6="Catastrophic", and add a `warnings[]` entry explaining the cap. With acknowledgment, allow Global Database and warn loudly that the user acknowledged cross-border replication.

Reuse existing regional service-availability checks so EU-capped designs do not map to services unavailable in the chosen EU region.

### 5. `references/phases/generate/generate-artifacts-infra.md`

No new Terraform resources. Add one documentation-only change: extend the existing compliance-conditional header-variant logic (Step 1.5, item 3) so that when `compliance` contains `gdpr` (with or without soc2/pci/hipaa/fedramp also present), the `baseline.tf` file header includes a short note:

> "GDPR was declared for this migration. This baseline does not generate GDPR-specific controls (GDPR is a data-processing/residency framework, not an AWS account-control framework this baseline addresses). Data residency constraints were enforced at Clarify/Design — see `terraform/README.md` for the resolved region and any `cross_border_transfer_acknowledged` decisions in `preferences.json`. Existing behavior retained: GDPR contributes to CloudTrail retention (365 days) but does not alone emit Config/Security Hub."

This makes the "GDPR gets no Config/Security Hub" behavior an explicit, documented decision rather than a silent gap, without generating anything new.

### 6. `references/shared/org-recommendation-engine.md`

Add a one-line comment next to the existing `"None or GDPR-only"` signal-table entry explaining the reasoning, e.g.:

> Note: GDPR is a data-residency/processing framework, not an account-isolation driver — it does not independently push toward Profile 2 (prod/dev split) the way SOC2/PCI/HIPAA do. If a workload has both GDPR and another compliance framework, the other framework's row governs the profile recommendation.

No behavior change — just makes the existing grouping legible as an intentional decision for future maintainers.

### 7. `references/phases/generate/generate-artifacts-report.md` (Appendix G + Section 4)

Add a GDPR line to the existing "What the baseline does NOT cover (you still need)" list, matching the style of the existing SOC2/HIPAA/PCI/FedRAMP bullets:

> - GDPR: Data Processing Agreement (DPA) with AWS, Records of Processing Activities (RoPA), data subject rights workflows (access/erasure/portability), Data Protection Impact Assessment (DPIA) where applicable, lawful basis / transfer-mechanism documentation, and a designated EU representative if required. This migration assistant enforces declared region/replication preferences only — it does not assess GDPR compliance.

Also add a **mandatory** compliance callout in Section 4 (exec summary teaser) when GDPR is declared:

> **GDPR / data residency note:** Your declared GDPR requirement constrained this migration's residency policy ([resolved region]; allowlist: see skill `gdpr-region-allowlist`). [If `cross_border_transfer_acknowledged`: **"You acknowledged proceeding with a non-EU and/or cross-border topology. This tool did not validate SCCs or any transfer mechanism — that remains your responsibility."**] This baseline does not generate GDPR-specific account controls — residency and acknowledgment decisions were enforced at Clarify/Design. See Appendix G.

When `cross_border_transfer_acknowledged` is true, this callout must not be omitable or buried — same visibility bar as other compliance callouts in Section 4.

---

## Schema additions to `preferences.json`

```json
{
  "compliance": { "value": ["gdpr"], "chosen_by": "user" },
  "metadata": {
    "gdpr_region_resolution": "region_switched | cross_border_acknowledged | compliance_revised | not_applicable",
    "gdpr_acknowledgment_scope": "non_eu_primary_region | non_eu_replica | both | null"
  },
  "cross_border_transfer_acknowledged": {
    "value": true,
    "chosen_by": "user",
    "prompt": "Acknowledge non-EU / cross-border topology; transfer mechanism documented outside this tool"
  }
}
```

Notes:

- Prefer **`cross_border_transfer_acknowledged`** over `data_transfer_consent` — this is self-attestation that a mechanism exists outside the tool, not legal consent captured by the plugin.
- `gdpr_acknowledgment_scope` records _what_ was acknowledged (non-EU primary region vs non-EU replica/CRR vs both).
- `cross_border_transfer_acknowledged` is only written/read when `compliance` includes `"gdpr"` and either (a) Q1 resolved outside the EU allowlist (option B), or (b) a multi-region construct was under consideration (Q1="Global"/"Multi-region", or storage/DB topology that would leave the EU). Absent for GDPR-flagged single-EU-region migrations with no cross-region constructs — do not ask an acknowledgment question that doesn't apply.
- Resolution value `user_confirmed_transfer_mechanism` from earlier drafts is renamed to **`cross_border_acknowledged`** for consistency with the field name.

---

## Test plan (once implemented)

- [ ] Clarify: GDPR selected (Q2=F) + Q1 resolves to non-EU region → cross-check prompt fires; paths A/B/C write correct `metadata.gdpr_region_resolution` (and B sets `cross_border_transfer_acknowledged` + `gdpr_acknowledgment_scope`)
- [ ] Clarify: GDPR selected + Q1 already EU → no prompt, `gdpr_region_resolution: "not_applicable"`
- [ ] Clarify: "use defaults for the rest" after GDPR → default region still forced through EU allowlist / cross-check, not raw GCP-closest mapping
- [ ] Q2 impact/interpret text cites shared allowlist (not only eu-west-1 / eu-central-1)
- [ ] Design: `gdpr` + non-EU region + no acknowledgment → `GATE_FAIL`, Design does not proceed
- [ ] Design: `gdpr` + non-EU + `cross_border_acknowledged` → proceeds with loud `warnings[]` entry
- [ ] Design: GDPR + EU region → proceeds normally for single-region source configs
- [ ] storage.md: GCS multi-region + GDPR + no acknowledgment → single-EU S3 + warning; + acknowledgment → CRR allowed + warning of what was unlocked
- [ ] database.md: Q1=Global + Q6=Catastrophic + GDPR + no acknowledgment → capped at multi-az-ha + warning; + acknowledgment → Aurora Global allowed + loud warning
- [ ] generate-artifacts-infra.md: GDPR-only → baseline.tf header includes the new note; no Config/Security Hub; CloudTrail retention 365 still applies; existing self-checks unchanged
- [ ] Migration report: GDPR declared → Appendix G bullet present; Section 4 callout present with resolved region; if acknowledgment set, exception language is mandatory and prominent
- [ ] Regression: PCI/HIPAA/SOC2/FedRAMP-only runs (no GDPR) — zero behavior change to already-passing fixtures
- [ ] Shared allowlist file is the only place the EU region list is defined (no duplicates in Clarify/Design/design-refs)

---

## Explicit non-goals (do not expand this PR)

- DPIA / DPA / RoPA / DSAR automation
- Validating SCCs or adequacy decisions
- Per-resource personal-data classification
- Generating "GDPR controls" in Terraform beyond existing retention behavior
- FedRAMP GovCloud enforcement (separate PR)
- Heroku skill parity (separate follow-up)

---

## Open questions (remaining)

None blocking implementation after review alignment. Optional polish during impl:

1. Exact closest-EU rows for the GCP region set most common in discovery fixtures — fill from real inventory samples if easy; otherwise ship the fallback (`eu-west-1`) and extend later.
2. Whether `eu-west-2` (London) should stay on the GDPR allowlist as-is (AWS commercial `eu-*` naming) or get a one-line "confirm with counsel for UK GDPR / post-Brexit" note in the allowlist file — prefer a short note, not a code fork, in v1.
