# Estimate — Pricing Mode Selection (canonical Step 0)

> Canonical pricing-mode procedure for estimate cost engines, vendored into
> each skill (`references/vendored/estimate/pricing-mode.md`) and kept
> byte-identical by `shared:sync`. The `cached_stale` enum bug happened because
> two copies of this logic evolved separately — do not fork this text again.
> Skill cost engines execute this file AS their Step 0, then own everything
> after it (baseline rungs, service formulas, tiers).

## Step 0a: Load the pricing cache

Read `references/vendored/pricing/aws-infra-pricing.json`. Check
`_meta.last_updated` against `_meta.staleness_days` (default 30):

- Within the window: **cached prices are the primary source.** No MCP calls
  needed for services in the file. Set `pricing_source: "cached"`.
- Past the window: infrastructure prices remain reliable. Attempt MCP (Step
  0b) for services not in the file; use cached rates as fallback with
  `pricing_source: "cached_stale"`.

Each service object carries its rates and (where relevant) a
`multi_az_handling` key. Look rates up from the file — never hardcode them.

## Step 0a-i: Check the target REGION against the cache's region

Read `_meta.region` and compare it with the design's target region. When they
differ, every rate in the file belongs to a different region than the one being
designed — commonly 5–12% low for European regions on compute and RDS.

- **MCP reachable:** reprice via MCP, **passing the target region on every
  `get_pricing` call**. A server-level `AWS_REGION` in `.mcp.json` is only that
  server's default; it does not follow the design.
- **MCP unreachable:** proceed with the cached rates, but state the mismatch
  next to every total ("rates are `<cache region>`; the target is `<target>`")
  and widen the stated accuracy band accordingly.

Never present one region's rates as another region's without saying so. Record the
comparison on the artifact so a reader does not have to infer it:

```json
"pricing_source": {
  "cache_region": "<_meta.region>",
  "target_region": "<the design's target region>",
  "region_mismatch": "<true when they differ>",
  "region_mismatch_note": "<REQUIRED when true — states the direction and rough size of the error>"
}
```

`region_mismatch: false` on an estate whose target differs from the cache region
is a false statement, not a simplification.

## Step 0a-ii: Check the RATE ROW, not just the service

A service can be present in the file while the specific rate row a design needs
is absent: `ec2` is there, `ec2.instances["m6i.2xlarge"]` may not be. **Service
presence is not rate availability**, and the hierarchy below keys on the row, not
the section.

Before pricing anything, resolve every concrete rate key the design requires —
each `instance_type`, `instance_class`, `node_type`, `broker_instance_type` — and
collect those with no row. A missing row then routes exactly like a missing
service: rung 2 (MCP), then rung 5.

**Never substitute a neighbouring row for a missing one** — an `m5` rate for an
`m6i` design, an `rds_postgresql` class for a DocumentDB one, a Linux rate for a
Windows-licensed instance. A near-miss rate is indistinguishable from a correct
one in the output, so the error is silent and permanent. This is the gap a
skill's sizing tables open when they are authored separately from these rates,
which is the normal case for a skill whose sizes come from source-cloud SKUs.

**A line whose rate is only PARTLY available is `"partial"`**, not `"cached"`:
its base rate resolved but a required component did not (the commonest case is
an instance priced Linux when the design says `license_model: "License
Included"`). Report the figure as a **floor**, name the missing component, and
exclude the line from any total presented as decision-grade. Rounding a partial
line up to `"cached"` hides a known understatement; rounding it down to
`"unavailable"` throws away a real number.

## Step 0b: MCP availability check (only if cache stale or service not listed)

Attempt the awspricing MCP with **up to 2 retries** (3 total attempts,
10-second timeout per attempt):

1. Attempt 1: `get_pricing_service_codes()`
2. Timeout/error → wait 1s, attempt 2
3. Timeout/error → wait 2s, attempt 3
4. All 3 fail → cached prices, `pricing_source: "cached_fallback"`

**If the MCP tool is not present in the host at all**, there is nothing to retry:
treat tool-absence as equivalent to three failures and proceed. Do not report a
retry ladder that was never executed.

### Tiebreak: a STALE cache and an unreachable MCP at the same time

This is the common case, not an edge case, and three rules above name two different
values for it — Step 0a says `cached_stale`, Step 0b and hierarchy row 3 say
`cached_fallback`. **Resolution: the top-level `pricing_source.status` is
`"cached_stale"`, and staleness wins.**

The reason is that the two labels answer different questions. `cached_fallback`
means "we tried live pricing and could not get it", which is about the attempt;
`cached_stale` means "these rates are older than the file says they should be",
which is about the DATA the reader is being handed. Only the second changes how
much to trust the number, so it is the one that belongs on the status. Record the
MCP failure in `pricing_source.message` and in `mcp_available: false`, so nothing
is lost.

Per-LINE `pricing_source` values remain the hierarchy's own: `cached`, `partial`,
`live`, `cached_fallback`, `estimated`, `unavailable`. **`cached_stale` is a
run-level status and never a per-line value** — every line in a stale-cache run
would otherwise be relabelled, which loses the distinction between a rate that
resolved and one that did not.

## Step 0c: Display the pricing mode

Before any calculation, surface the status:

- Cache fresh + all services covered: "Pricing source: cached (updated
  [date], ±5-10% accuracy). Live pricing API not required."
- Cache stale + MCP available: "Pricing source: live API (awspricing MCP).
  Cache is stale ([date]) — using real-time pricing."
- Cache stale + MCP unavailable: "Pricing source: stale cache only (updated
  [date]). The awspricing MCP server is unreachable. Proceeding with cached
  pricing; accuracy ±5-10% for infrastructure."
- Service or rate row not in cache + MCP unavailable: "Some services not in
  pricing cache and MCP unreachable. Those services will show
  `pricing_source: unavailable` in the estimate."
- Target region differs from `_meta.region` + MCP unavailable: "Rates are
  [cache region]; your target is [target region]. Proceeding with [cache
  region] rates — treat the totals as indicative, not regional."

## Pricing hierarchy (per-RATE-ROW lookup order)

"Found in the pricing file" below means **the concrete rate row resolved**, per
Step 0a-ii — not merely that the service's section exists.

| Priority | Source                                               | Condition                                                                                      | `pricing_source` value |
| -------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------- |
| 1        | `references/vendored/pricing/aws-infra-pricing.json` | Rate row found in the pricing file                                                             | `"cached"`             |
| 1b       | Same, base rate only                                 | Base row found but a required component is not priced (e.g. a Windows licence adder)           | `"partial"`            |
| 2        | MCP API (`get_pricing`)                              | Rate row NOT in the file, MCP available                                                        | `"live"`               |
| 3        | Pricing file after MCP failure                       | MCP attempted but failed, rate row IS in file                                                  | `"cached_fallback"`    |
| 4        | Formula constants / well-known published rate        | NOT in file, MCP failed, but the cost engine's own formulas carry the rate (state it verbatim) | `"estimated"`          |
| 5        | Unavailable                                          | NOT in file, MCP failed, no formula constant either                                            | `"unavailable"`        |

Row 4 is the documented home of the `services_by_source.estimated` bucket the
shared schema and assemblers carry: a service priced from a rate the cost
engine itself states (never a guessed or remembered number) is `"estimated"`,
always accompanied by a warning naming the rate and its source. **A rate the
model recalls rather than reads is not a formula constant** — it is rung 5.

Only a line with no cache row, no MCP, AND no stated formula rate is
`"unavailable"` and excluded from totals.

Row 1b lines are excluded from any total presented as decision-grade and
reported as a floor with the missing component named, per Step 0a-ii. Track them
in `pricing_source.services_by_source.partial[]` — the shared
`estimation-infra.schema.json` does not constrain that object's keys, so this
needs no schema change.
