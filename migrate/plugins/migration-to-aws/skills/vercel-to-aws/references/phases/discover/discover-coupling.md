---
_fragment: coupling-score
_of_phase: discover
_contributes:
  - coupling-score.json (items[] section)
---

# Discover Phase: Coupling Score (Unconditional)

> Self-contained fragment. ALWAYS runs, regardless of the signal-priority branch
> taken or which Tier 2/3 inputs are present. Computes the full per-feature
> Coupling Score inventory (Requirement 5.1-5.2) using the item definitions in
> `knowledge/coupling-weights.json`.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Recompute Short-Circuit (Warm Re-Entry Only)

Before computing ANY item this fragment owns, check whether
`assessment-state.json.findings.coupling.<item_id>.computed_from_inputs`
intersects the `newly_received` list passed in from `discover.md` Step 0 (itself
sourced from `prescan-assemble.md`/`prescan.md` Step 1). If a given item's
dependency set does NOT intersect `newly_received`, copy its prior
`value`/`confidence`/`computed_at` forward UNCHANGED and skip recomputation for
that item only. If it DOES intersect (or this is a cold/fresh run with no prior
`assessment-state.json` findings for this item), recompute normally per the steps
below.

This is a per-fragment prose contract, not a new DSL primitive — see
`design.md` § Resolved Design Decisions item 1 and `SKILL.md` § Assessment State
Management.

---

## Step 1: Load `knowledge/coupling-weights.json`

Load the item definitions table. For each of the 9 items (`isr`,
`edge_middleware`, `edge_runtime_routes`, `image_optimization`, `streaming_ssr`,
`server_actions_version_skew`, `preview_deployments`, `vercel_managed_stores`,
`vercel_injected_headers`), apply its `detection` method against the artifacts
already produced by other fragments this same Discover run
(`discovery.json`'s in-progress contributions from `discover-configs.md`,
`discover-api.md`, `discover-adapter.md`/`discover-manifests.md`).

---

## Step 2: Compute Each Item (Subject to the Short-Circuit Above)

For each item, record:

```json
{
  "id": "isr",
  "detected": true,
  "detection_method": "revalidateTag/revalidatePath calls found in 4 route files",
  "weight_rationale": "<copied/adapted from knowledge/coupling-weights.json>"
}
```

`preview_deployments` is special: it cannot be detected from code alone (per
`coupling-weights.json`'s own detection note — "Clarify Q4, not detectable from
code alone"). Record it as `detected: "pending_clarify"` here; `clarify-ask.md`
resolves it, and `recommend-rules.md` reads the resolved value directly from
`clarify-answers.json`, not from this fragment's contribution.

---

## Step 3: Phased-Migration Signal (Requirement 5.3)

If exactly one item is detected at unusually high coupling relative to the rest
of an otherwise-migratable inventory (a judgment call — e.g. heavy edge-runtime
coupling on a single route family while everything else is straightforward),
flag this explicitly:

```json
{
  "phased_migration_candidate": {
    "flagged": true,
    "component": "edge_runtime_routes",
    "note": "phased migration proceeds while this component is evaluated on a specialist path in parallel"
  }
}
```

This flag feeds the report's Coupling Score section — it is NOT itself a
Recommendation Engine input; the engine's precedence rules (Requirement 7) do not
branch on this flag. It is purely a report-authoring signal so the report can
avoid a blanket stay-on-Vercel framing when only one component is genuinely hard
(Requirement 5.3).

---

## Step 4: Output Contribution for Parent Orchestrator

The phase assembler (`discover-assemble.md`) owns `coupling-score.json`'s overall
structure. This fragment contributes the full `items[]` array (9 entries) plus
the optional `phased_migration_candidate` object. Each item's
`computed_from_inputs` is set per its detection method:

- Items detected purely from source configs/API (`isr`, `edge_middleware`,
  `edge_runtime_routes`, `image_optimization`, `streaming_ssr`,
  `server_actions_version_skew`, `vercel_managed_stores`,
  `vercel_injected_headers`): `computed_from_inputs: ["repo_access"]` or
  `["vercel_api_token"]` as appropriate.
- `preview_deployments`: `computed_from_inputs: ["clarify_q4_preview_dependence"]`
  (resolved downstream in Clarify, not here).

---

## Error Handling

| Error Category                                                                 | Behavior                                                                                                                                                      |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| An upstream fragment's contribution this item depends on is missing/incomplete | Record the item as `detected: "unknown"`, note the missing dependency, continue with remaining items                                                          |
| `knowledge/coupling-weights.json` fails to load                                | Halt this fragment specifically (a `_halt_and_inform`-equivalent condition surfaced at the phase's postconditions) — the item table is required, not optional |

---

## Scope Boundary

**This fragment covers Coupling Score computation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Pre-Flight Check computation (that is `discover-preflight.md`'s job, a
  separate fragment)
- Recommendation logic (the phased-migration flag is report-authoring signal
  only, never a Recommendation Engine input)
- AWS service names or recommendations

**Your ONLY job: compute the 9-item Coupling Score inventory unconditionally.
Nothing else.**
