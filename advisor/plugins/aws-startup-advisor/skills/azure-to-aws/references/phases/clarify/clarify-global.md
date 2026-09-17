---
_fragment: global
_of_phase: clarify
_contributes:
  - preferences.json (global section; created here, finalized by the assembler)
---

# Clarify — Global Preferences

> **Fragment unit.** See `clarify.md` for how it is composed into the phase.

Gathers the estate-wide answers every Azure migration needs regardless of what the
inventory contains: target AWS region (mapped from the estate's Azure regions rather
than assumed), migration window, environment scope (which of the discovered
subscriptions and environments are in scope), CPU architecture, and cost-optimization
appetite.

**The architecture default is `x86_64`, and that is a deliberate divergence from the
rest of this repo.** Graviton is the default in the GCP and Heroku skills. Azure
fleets carry Windows and .NET routinely, which is exactly the escape path in
`references/shared/graviton.md`, so defaulting to Graviton here would produce a
recommendation that has to be walked back on a large fraction of real estates.
Graviton is offered as an optimization with its own savings line.

## Step: Return rows

> **This fragment asks nothing.** `clarify-assemble.md` owns the conversation — see
> `clarify.md` § Step: Run the phase for why presentation is centralised.

### Q-A1 — Target AWS region

**Disposition:** DETECTED when every resource shares one Azure region and the map resolves
it; **ESSENTIAL** when the estate spans regions (there is no defensible way to pick one for
someone). **Default when DETECTED:** the mapped region.

Map from the estate's Azure regions via `knowledge/design/azure-region-map.json` — do not
assume `us-east-1` when the estate is plainly European. `westeurope` → `eu-west-1`.

### Q-A2 — Environment scope

**Disposition:** DETECTED from the resource groups and name patterns present.
**Default:** every environment found.

Under an obfuscated RDfA report the `prod_` / `nonprod_` prefixes give this directly. From
Terraform it is a name-pattern heuristic (`-dev`, `-prod`, `d-`, `t-`, `s-`), so treat it as
a strong hint and show what was inferred rather than asserting it.

### Q-A3 — Migration window

**Disposition:** PROPOSED. **Default:** `null` — unstated.

Left null rather than guessed. It shapes the timeline in the report and nothing in the
design, so an invented window would add false precision to the one output people quote.

### Q-A4 — Cost optimization appetite

**Disposition:** PROPOSED. **Default:** `balanced`.

```
[A] Conservative — like-for-like capacity, lowest risk
[B] Balanced — right-size where measured data supports it     (default)
[C] Aggressive — smallest defensible footprint
```

**Consequence line:** _Balanced right-sizes only where measurement supports it. Aggressive
can cut the estimate materially and needs load testing before cutover._

Feeds the aggressiveness slider in `knowledge/estimate/rightsizing-thresholds.json`. With no
utilization data it changes nothing — say so on the row rather than implying it will.

### Q-A5 — Azure baseline spend

**Disposition:** DETECTED when a billing export was discovered; **ESSENTIAL** otherwise —
there is no way to infer what someone pays.

Anchors the migrate-versus-stay comparison. With no billing source the whole comparison is
absent from the report, which is worth stating rather than leaving the reader to notice.

## Rows returned

```jsonc
"global": {
  "target_region":     { "disposition": "DETECTED", "value": "eu-west-1", "default": "eu-west-1" },
  "environment_scope": { "disposition": "DETECTED", "value": ["prod"],   "default": ["prod"] },
  "migration_window":  { "disposition": "PROPOSED", "value": null,       "default": null }
},
"design_constraints": {
  "cost_optimization": { "disposition": "PROPOSED", "value": null, "default": "balanced" }
},
"baseline": {
  "azure_monthly_spend": { "disposition": "ESSENTIAL", "value": null, "default": null }
}
```

`cpu_architecture` is **not** here — it belongs to `clarify-compute.md`, because whether it
is a question at all depends on whether Windows is present.

## Status — build step 5

Implemented. `knowledge/design/azure-region-map.json` **exists** — look the region up
there, and do NOT emit a "table absent" flag. Where the row's `same_country` is false the
move crosses a border: surface that as a residency warning rather than resolving it
silently.
