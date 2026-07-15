---
_fragment: adapter-build
_of_phase: discover
_contributes:
  - discovery.json (route_disposition, adapter_metadata sections)
---

# Discover Phase: Adapter API Build (Primary Path, Next.js >= 16.2)

> Self-contained fragment. Triggered only when `next_version >= 16.2` AND
> `next_build_health == "clean"` (per `discover.md` Step 1). This is the
> highest-authority signal source — it reads Next.js's stable, typed Adapter API
> contract rather than reverse-engineering build output.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Run the Adapter API Build

Run `next build` with the Adapter API's typed output enabled (per the project's
Next.js 16.2+ configuration). Consume the resulting typed, versioned description
of the app: routes, prerenders, runtime targets, caching rules, routing
decisions.

If the build fails here despite `prescan-collect.md` having recorded
`next_build_health: "clean"` (a transient failure, environment drift since
PreScan ran), record this discrepancy as a finding at LOW confidence and fall
back — signal `discover.md` to load `discover-manifests.md` instead for this run.
Do not silently retry indefinitely.

---

## Step 2: Route-Disposition Comparison (v1 Scope)

Per Requirement 4.2: produce a route-disposition comparison — which routes the
adapter treats as static / ISR / dynamic / edge — as an INFORMATIONAL finding.
This is tractable because it reads declarative output, not provisioning logic.

```json
{
  "route_disposition": [
    { "route": "/", "disposition": "static" },
    { "route": "/blog/[slug]", "disposition": "isr", "revalidate_seconds": 3600 },
    { "route": "/api/webhook", "disposition": "dynamic" },
    { "route": "/api/geo", "disposition": "edge" }
  ]
}
```

Record this with `confidence: "HIGH"` — the Adapter API's typed output is the
highest-authority signal defined in this skill's signal priority (Requirement
4.1), so a route-disposition finding sourced from it needs no
`upgrade_input`.

---

## Step 3: Explicit v1 Scope Boundary — No Full Infra Diff

Per Requirement 4.3: do NOT attempt a full "what Vercel provisions vs. what
OpenNext provisions" infrastructure diff. Adapter outputs are code paths, not a
declarative infra dump; naive diffing would overstate precision. This is
explicitly deferred until the verified AWS adapter reaches general availability
(see `SKILL.md` Philosophy and `requirements.md` Out of Scope). If asked to
produce this diff, decline and point to this scope boundary.

---

## Step 4: Contribute Adapter Metadata

Record which adapter version/contract was used, for the report's decision
traceability appendix:

```json
{
  "adapter_metadata": {
    "adapter_api_used": true,
    "next_version": "16.2.0",
    "adapter_contract_version": "<as reported by the build>"
  }
}
```

---

## Step 5: Output Contribution for Parent Orchestrator

The phase assembler (`discover-assemble.md`) owns `discovery.json`'s overall
structure. This fragment contributes the `route_disposition` array and
`adapter_metadata` object shown above, each finding carrying
`computed_from_inputs: ["repo_access"]` (this signal depends only on repo access

- a clean build, no Tier 2/3 input) so a warm re-entry's recompute logic knows
  these findings never need recomputation from a NEW Tier 2/3 input alone (they
  would only change if the repo itself changed, which is out of scope for the
  `newly_received`-input recompute mechanism).

---

## Error Handling

| Error Category                                                          | Behavior                                                                             |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Build succeeds but produces no typed output (misconfigured Adapter API) | Record `adapter_api_used: false` with a reason, fall back to `discover-manifests.md` |
| Build times out                                                         | Record a LOW-confidence finding, fall back to `discover-manifests.md`                |

---

## Scope Boundary

**This fragment covers the Adapter API build path ONLY.**

FORBIDDEN — Do NOT include ANY of:

- A full Vercel-vs-OpenNext infrastructure diff (explicitly out of scope, Step 3)
- AWS service names or recommendations
- Coupling Score or Pre-Flight Check computation (separate fragments)

**Your ONLY job: run the Adapter API build and produce the route-disposition
comparison. Nothing else.**
