---
_fragment: artifacts-report
_of_phase: generate
_contributes:
  - migration-report.html
---

# Generate — Stakeholder Report

> **Fragment unit.** See `generate.md` for how it is composed into the phase.

The customer-facing report. **It leads with the cluster-level architecture rationale** —
what workloads were found, what each becomes, and why — and moves the per-resource
mapping table to an appendix. This is the visible payoff of the holistic goal and the
part a customer actually reads; a 40-row table as the headline buries the argument.

**Execute the steps in order.**

## Inputs

Read from `$MIGRATION_DIR/`: `aws-design.json` (`clusters[]` with `pattern_status` /
`target_architecture` / `rationale`, `services[]`, `deferred[]`, `warnings[]`),
`estimation-infra.json` (cost comparison, tiers, reservations, `is_floor`),
`azure-resource-inventory.json` (drift + reservation signals), `preferences.json`,
and `scenarios/index.json` if it exists (workshop what-ifs).

Reuse the executive-summary renderer conventions from the shared report spec where
available; otherwise emit clean semantic HTML (headings, tables, a table of contents).

## Step 1: Lead with cluster-level rationale (REQUIRED — `_assert`)

The report OPENS with the workload story, one block per `clusters[]` entry:

- the workload (its primary + members, in plain language),
- its `target_architecture` and the cluster `rationale` — what it becomes and why,
- for an `unclassified` cluster or `pattern_status: catalog_absent`, say so plainly so
  the report does not overclaim architectural insight it does not have.

The per-resource mapping table (azure_type → aws_service, confidence) goes in an
**appendix**, not the body. The phase `_assert` fails if the table leads.

## Step 2: Cost section

Present the Premium / Balanced / Optimized comparison from `estimation-infra.json`, and
**surface, not hide**:

- `is_floor: true` and any unpriced lines — say the total is a floor and why.
- Reserved-instance baselines, and that a `$0` consumption line was substituted with an
  RI-equivalent rate (never presented as free).
- The baseline provenance (user-stated bracket vs invoice) and the accuracy band.

## Step 3: Surface the rest

- **Drift** between declared IaC and running state (when a live/RDfA source ran).
- **Deferred** specialist items, each named with its recommendation.
- **Availability downgrades** — where a zone-redundant source maps to single-AZ.
- The **what-if comparison** when `scenarios/index.json` has ≥ 2 scenarios (REQUIRED by
  the phase `_assert` in that case).

## Step 3.5: Resource count (REQUIRED)

Any **mapping / plan / service / headline** count the report states — the headline "N
services", a per-section subtotal, or the appendix mapping table's row count — MUST equal
`generation-warnings.json.accounted`: the accounted headline = generated services (each
plan-fold counted ONCE via its parent) + `deferred[]`. `skipped[]` entries (config sources,
observability, plan-folded children) are still recorded in `generation-warnings.json` for
completeness but are **EXCLUDED from the accounted headline** — a folded or config-only
resource is not a distinct billed service, and counting it double-counts against its parent.
Do **not** count only the emitted `.tf` resources, and do **not** count `services[]` alone —
a deferred resource is still a resource the customer must plan for. This mirrors the
PRIMARY-services headline rule in gcp-to-aws `report-decision-core.md` § 1 (secondaries
excluded). The report-body mapping count, the Terraform `migration_summary` count
(`generate-artifacts-infra.md` Step 4), and `generation-warnings.json.accounted` must all
agree.

**Surface the split in the report body (REQUIRED).** State the three figures side by side so
the reader sees raw estate vs. plan rather than a bare number that appears to disagree with
the discovery count: **"N discovered · M mapped services · A accounted (M + D deferred)"** —
where N = `total_resources` (raw discovered), M = generated primary services, D = `deferred[]`,
and A = `accounted` (= M + D).

**Exception — the discovery/"discovered" count is its own figure.** A statement about what
was *discovered* — "Discovery identified N resources", "N resources discovered", the raw
Azure estate size — references `azure-resource-inventory.json` `total_resources` (the RAW
discovered count), NOT `accounted`. `total_resources` legitimately exceeds `accounted`
(the accounted set excludes resources that were never mapped/planned — e.g. free/zero-cost
or non-migratable items), so forcing the discovery label to equal `accounted` understates
what was actually found. Keep the two distinct: the discovery figure = `total_resources`;
every mapping/plan/service/headline figure = `accounted` (with the three-way agreement
above). This mirrors gcp-to-aws `report-decision-core.md` where the discovered/current
count is a separate figure from the mapping count.

## Step 4: Draft-for-review footer (REQUIRED — `_assert`)

Every report carries a footer stating it is a draft for review, generated from the
migration plan, and that figures are estimates to validate before decisions.

> **Plan-share links are GATED OFF** (landing page not live). Do NOT emit a share link.

## Status — implemented (build step: Generate)

Implemented, mirroring gcp-to-aws's `generate-artifacts-report.md` but honoring azure's
holistic contract: cluster-level rationale leads, per-resource table is an appendix,
cost floor / reservations / drift / deferrals / availability-downgrades / what-if all
surfaced, draft-for-review footer present.
