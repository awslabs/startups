---
_fragment: preflight-checks
_of_phase: discover
_contributes:
  - preflight-findings.json (checks[] section)
---

# Discover Phase: Pre-Flight Checks (Unconditional, All 10 Always Computed)

> Self-contained fragment. ALWAYS runs, regardless of the signal-priority branch
> taken, which Tier 2/3 inputs are present, or — critically — which outcome
> Recommend will eventually select (Requirement 6.2: the recommendation does not
> exist yet at this point in the pipeline). Computes all 10 named checks (M1, M2,
> B1, B2, B3, B4, S1, I1, O1, U1) using the definitions in
> `knowledge/preflight-checks.json`.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Recompute Short-Circuit (Warm Re-Entry Only)

Before computing ANY check this fragment owns, check whether
`assessment-state.json.findings.preflight.<check_id>.computed_from_inputs`
intersects the `newly_received` list. If a given check's dependency set does NOT
intersect `newly_received`, copy its prior `value`/`confidence`/`computed_at`
forward UNCHANGED and skip recomputation for that check only. If it DOES
intersect (or this is a cold/fresh run), recompute normally per the steps below.

Same mechanism as `discover-coupling.md`'s short-circuit — see `design.md` §
Resolved Design Decisions item 1.

---

## Step 1: Load `knowledge/preflight-checks.json`

Load all 10 check definitions. For each, apply its `detection` method against
artifacts already produced by other fragments this Discover run
(`discover-configs.md`'s middleware/route analysis, `discover-api.md`'s usage
metrics, `prescan-scan.md`'s lockfile census and `has_sharp_dependency`).

---

## Step 2: Compute M1 (Flagship, Applies to All Outcomes — Compute First)

Detect the intersection of `middleware_analysis.matcher` (from
`discover-configs.md`) against static/ISR/CDN-cacheable routes (from
`route_disposition`, whichever signal-priority fragment produced it). A
non-empty intersection triggers this check.

**Evaluate per matcher pattern, not once for the whole middleware file.** Read
`middleware_analysis.per_matcher_pattern` (not the collapsed top-level
`classification`) — for EACH matcher pattern that intersects a cacheable route,
use THAT pattern's own classification to decide severity, since a middleware
file's different matcher patterns can carry genuinely different behaviors (e.g.
an auth-gating pattern scoped to one route group and an unrelated geo-redirect
pattern scoped to another). If a cacheable route is only covered by a
`header_decoration`/`logging` pattern while a DIFFERENT cacheable route is
covered by an `auth_gating`/`ab_bucketing`/`geo_redirect`/`rewrite` pattern, M1
still fires HIGH overall (the check's severity is the MAX across all
intersecting patterns, per the conservative-default principle in
`discover-configs.md`'s Error Handling table) — but `detail` MUST name which
SPECIFIC pattern/route intersection actually drove the HIGH verdict, not imply
the whole middleware file is auth-gating when only part of it is. A pattern
that does NOT intersect any cacheable route contributes nothing to this check's
severity, even if its own classification would independently be HIGH.

- Severity HIGH when the intersecting pattern's classification is
  `auth_gating`, `ab_bucketing`, `geo_redirect`, or a per-request `rewrite`.
- Severity LOW when the intersecting pattern's classification is
  `header_decoration` or `logging`.

Record with `applies_to: ["A", "B", "C"]` and `adapter_generation:
"independent"` — this check's applicability never changes regardless of which
outcome is eventually recommended (Requirement 6.5). Confidence is HIGH when the
underlying route-disposition and middleware-matcher signals are both HIGH
confidence; MEDIUM/LOW if either upstream signal is degraded.

---

## Step 3: Compute the Remaining 9 Checks

For M2, B1, B2, B3, B4, S1, I1, O1, U1: apply each check's `detection` method per
`knowledge/preflight-checks.json`, using the `severity_rule` (or
`severity_rule_by_outcome` for I1) to assign severity. Record each check's
`applies_to` set and `adapter_generation` tag verbatim from the knowledge table —
do NOT compute or infer these tags; they are fixed metadata, not derived from the
current repo's state.

For I1 specifically: compute BOTH the Outcome-A severity rule and the Outcome-B
severity rule now, per `severity_rule_by_outcome` — do not wait to know which
outcome applies. `report-render.md` selects which rule's wording to surface based
on the eventual recommendation.

---

## Step 4: Confirm All 10 Present, Unconditionally

Before contributing output, verify all 10 check IDs (M1, M2, B1, B2, B3, B4, S1,
I1, O1, U1) have an entry — even a check whose `applies_to` set will later
exclude the recommended outcome (e.g. B1 only applies to Outcome A) MUST still
have a computed entry here. This is what the phase's own `_postconditions`
`_assert` verifies later; this step is the fragment's own internal check before
handing off.

---

## Step 5: Output Contribution for Parent Orchestrator

```json
{
  "checks": [
    {
      "id": "M1",
      "detected": true,
      "severity": "HIGH",
      "applies_to": ["A", "B", "C"],
      "adapter_generation": "independent",
      "detail": "matcher pattern \"/dashboard/:path*\" (classification: auth_gating) intersects 1 ISR route (/dashboard); matcher pattern \"/blog/:path*\" (classification: geo_redirect) does not intersect any cacheable route in this run",
      "remediations": ["<copied from knowledge table>"]
    }
  ]
}
```

Each check's `computed_from_inputs` is set per its detection dependency: M1/M2
depend on `["repo_access"]` (source config parsing); B1/B2/B3 depend on
`["repo_access"]` (PreScan-level facts); U1 depends on
`["repo_access", "vercel_api_token", "log_drain_export"]` since it
cross-references route cache config against usage — a NEW log drain arriving on a
warm re-entry should trigger U1's recomputation specifically.

---

## Error Handling

| Error Category                                                     | Behavior                                                                                                                             |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| A check's detection dependency is missing/incomplete               | Record the check as `detected: "unknown"` with a note, but STILL include the entry (Step 4's "all 10 present" rule has no exception) |
| `knowledge/preflight-checks.json` fails to load                    | Halt this fragment — the check table is required                                                                                     |
| I1's severity_rule_by_outcome is ambiguous given available signals | Compute both branches with whatever confidence the signals support; do not force a single answer prematurely                         |

---

## Scope Boundary

**This fragment covers Pre-Flight Check computation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Filtering or reframing checks by outcome (that is `report-render.md`'s job —
  this fragment computes everything unconditionally)
- Coupling Score computation (separate fragment)
- Recommendation logic
- AWS service names beyond what the knowledge table's remediations already
  reference

**Your ONLY job: compute all 10 Pre-Flight Checks unconditionally. Nothing
else.**
