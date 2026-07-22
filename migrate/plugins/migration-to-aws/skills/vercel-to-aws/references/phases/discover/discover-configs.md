---
_fragment: source-configs
_of_phase: discover
_contributes:
  - discovery.json (next_config, middleware_analysis, vercel_json_config sections)
---

# Discover Phase: Source Config Parsing (Always Runs)

> Self-contained fragment. Always runs regardless of signal-priority branch —
> `next.config.js`, `middleware.ts` + matcher, and `vercel.json` are direct
> source artifacts, independent of which build path was taken.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Parse `next.config.js`

Read the project's `next.config.js` (or `.mjs`/`.ts` variant). Extract:

- **Route segment configs:** any `revalidate`, `dynamic`, `runtime: 'edge'`
  declarations found in route files (cross-referenced against the file tree, not
  just `next.config.js` itself — segment configs live in the route files).
- **Image config:** `images.domains`, `images.remotePatterns`, custom loader
  configuration.
- **`outputFileTracingExcludes`:** presence/absence — feeds Pre-Flight Check B4
  (bundle contamination).

---

## Step 2: Parse `middleware.ts` + Matcher

Only if `tier1-signals.json.has_middleware == true` (from PreScan's cheap
existence check):

- Parse the `matcher` export/config to determine which routes middleware
  applies to.
- Analyze the middleware body for: auth gating patterns, A/B bucketing logic,
  geo-redirect logic, per-request rewrites, vs. simple header decoration or
  logging. This classification feeds Pre-Flight Check M1's severity rule
  directly (HIGH vs. LOW).
- Grep for Vercel-injected geo/IP headers (`x-vercel-ip-*` etc.) — feeds
  Pre-Flight Check M2 and the Coupling Score `vercel_injected_headers` item.

**When the matcher has more than one pattern, classify EACH pattern
independently — do not collapse a multi-pattern matcher into a single
classification.** A single `middleware.ts` file commonly branches on
`req.nextUrl.pathname` and does genuinely different things for different route
groups (e.g. an auth-gating redirect scoped to one matcher pattern, and an
unrelated geo-redirect scoped to a different one). Read the middleware body's
own path-branching logic (`if (pathname.startsWith(...))` or equivalent), not
just the `matcher` array, to determine which behavior applies to which
pattern(s). Record a `per_matcher_pattern` breakdown (Step 5) with one entry per
matcher pattern, each carrying its OWN classification — this is the
authoritative signal `discover-preflight.md`'s M1 computation reads. Only fall
back to a single collapsed `classification` value when the middleware's logic
is genuinely undifferentiated across the whole matcher (e.g. it applies the
same header-decoration logic to every matched path regardless of which pattern
matched).

If `has_middleware == false`, skip this step entirely — do not speculatively
parse a file that PreScan already confirmed doesn't exist.

---

## Step 3: Parse `vercel.json`

Only if `tier1-signals.json.has_vercel_json == true`:

- Extract: `headers`, `redirects`, `rewrites`, function `maxDuration`/`memory`
  per route, `regions`, `crons`.

If `has_vercel_json == false`, skip this step.

---

## Step 4: Detect Streaming Route Handlers

Scan route handlers for streaming response patterns (`ReadableStream`, a
`Response` constructed with a stream body) where the stream can legitimately
emit zero bytes. This feeds Pre-Flight Check S1.

---

## Step 5: Output Contribution for Parent Orchestrator

```json
{
  "next_config": {
    "route_segment_configs": [...],
    "image_config": {...},
    "has_output_file_tracing_excludes": false
  },
  "middleware_analysis": {
    "matcher": ["<pattern>", ...],
    "per_matcher_pattern": [
      { "pattern": "<matcher pattern>", "classification": "auth_gating" | "ab_bucketing" | "geo_redirect" | "rewrite" | "header_decoration" | "logging" }
    ],
    "classification": "auth_gating" | "ab_bucketing" | "geo_redirect" | "rewrite" | "header_decoration" | "logging" | null,
    "geo_ip_headers_used": ["x-vercel-ip-country", ...]
  },
  "vercel_json_config": {
    "headers": [...], "redirects": [...], "rewrites": [...],
    "function_config": {...}, "regions": [...], "crons": [...]
  },
  "streaming_routes_with_empty_body_risk": ["<route>", ...]
}
```

`middleware_analysis.per_matcher_pattern` is the authoritative field whenever the
matcher has more than one pattern with genuinely different behaviors (see Step
2) — `discover-preflight.md`'s M1 computation reads THIS field per-pattern,
not the collapsed `classification`. The top-level `classification` field is set
to `null` when `per_matcher_pattern` entries diverge (more than one distinct
classification value present) — it exists only for the single-pattern or
undifferentiated-behavior case, where all patterns share one classification and
`per_matcher_pattern` would be redundant (still populate `per_matcher_pattern`
in that case too, with every entry carrying the same value, so downstream
consumers can rely on one field unconditionally).

Each contributed finding carries `computed_from_inputs: ["repo_access"]` — these
are pure source-code facts, not dependent on any Tier 2/3 input.

---

## Error Handling

| Error Category                                                                | Behavior                                                                                                                                                                |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `next.config.js` uses dynamic/computed values that can't be statically parsed | Record what CAN be statically determined, note the rest as `"unresolvable:dynamic"`, continue                                                                           |
| `middleware.ts` classification is ambiguous                                   | Default to the MORE conservative classification (e.g. ambiguous-but-plausibly-auth defaults to `auth_gating`, not `header_decoration`) — never under-call M1's severity |
| `vercel.json` malformed JSON                                                  | Record a parse warning, skip, continue with `has_vercel_json` findings degraded                                                                                         |

---

## Scope Boundary

**This fragment covers source config parsing ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Computing the Pre-Flight Check findings themselves (that is
  `discover-preflight.md`'s job — this fragment only produces the raw facts
  those checks consume)
- Computing the Coupling Score itself (same — `discover-coupling.md`'s job)
- AWS service names or recommendations

**Your ONLY job: parse source configs and record raw facts. Nothing else.**
