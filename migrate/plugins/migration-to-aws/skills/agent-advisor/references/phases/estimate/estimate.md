---
_phase: estimate
_title: "Estimate — Coarse Cost Magnitude"
_requires_phase: design
_input:
  - design.json
_assemble:
  _file: phases/estimate/estimate-assemble.md
_produces:
  - estimate.json
_advances_to: generate
_interactive: false
_exec:
  _agent: rw
_preconditions:
  - _check_phase_completed: design
    _on_failure: _halt_and_inform
  - _check_file_exists: design.json
    _on_failure: _unrecoverable
  - _validate_json: design.json
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: estimate.json
    _on_failure: _halt_and_inform
  - _validate_json: estimate.json
    _on_failure: _halt_and_inform
  - _assert: "estimate.json states a monthly_magnitude_usd band (never a precise total), records pricing_source (cached|cached_stale|mcp), and lists every assumption behind the magnitude"
    _on_failure: _halt_and_inform
---

# Phase: Estimate — Coarse Cost Magnitude

Build paths only (build_scratch / build_deploy). Migrate skips Estimate; the add_capabilities
branch runs its own self-contained flow and never reaches here. Magnitude only — NOT precise
estimation (that's migration-to-aws's job). Mirrors migration-to-aws's pricing pattern.

## Step 1 — Read the design

Read `$RUN_DIR/design.json`.

## Step 2 — Pricing source (layered, same as migration-to-aws)

1. Primary: a small cached rate table (inline below — AgentCore vCPU/GB-hour, Fargate, Lambda,
   plus the model default's token rates as order-of-magnitude). Carry a "last updated" date.
2. Fallback for anything missing: the `awspricing` MCP if available.
3. Record `pricing_source`: `cached` | `cached_stale` (if >30 days old) | `mcp`.

Cached anchors (order-of-magnitude, us-east-1, verify):

- AgentCore: ~$0.0895/vCPU-hour (active CPU only), ~$0.00945/GB-hour
- Lambda MicroVMs: ~$0.0997/vCPU-hour, ~$0.0132/GB-hour
- Fargate: ~$0.04048/vCPU-hour, ~$0.004445/GB-hour
- Bedrock model token rates: defer to migration-to-aws pricing cache for exact figures

## Step 3 — Produce a magnitude, not a quote

Estimate a rough monthly band (e.g. "order of $50–150/month at this usage") from the runtime

- model + a stated usage assumption. State every assumption. Never present a precise total.

> Determinism note: this magnitude is computed in the LLM layer (convention-aligned with
> migration-to-aws, which also estimates in-skill). It is the one output that is NOT
> script-deterministic. Acceptable for v1 (magnitude-only, every assumption stated); flagged as
> a future candidate to move into a small deterministic script if precision is ever required.

## Step 4 — Write estimate.json

```json
{
  "monthly_magnitude_usd": "50-150",
  "pricing_source": "cached",
  "assumptions": ["1000 sessions/mo, 5 min avg, 60% I/O wait"],
  "note": "Order-of-magnitude only. For a precise estimate use migration-to-aws."
}
```

## Step 5 — Write state

Set `phases.estimate` = completed.
