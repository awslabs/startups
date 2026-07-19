---
_fragment: manifest-fallback
_of_phase: discover
_contributes:
  - discovery.json (route_disposition, manifest_metadata sections)
---

# Discover Phase: `.next` Manifest Fallback (Next.js < 16.2 or Broken Build)

> Self-contained fragment. Triggered when `next_version < 16.2` OR
> `next_build_health != "clean"` (per `discover.md` Step 1). Reads the same
> artifacts OpenNext v3 itself consumes — the routes manifest and prerender
> manifest — as the fallback signal source when the Adapter API path is
> unavailable.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Read the Captured `.next` Build Manifests

Read the manifest files that `discover-capture.md` Step 1 copied to
`$MIGRATION_DIR/capture/build/` (whether from a pre-existing `.next/` or the
capture step's one best-effort `next build` — building is the capture step's
job in the main window; this worker has no shell):

- `routes-manifest.json` — static/dynamic route classification, redirects,
  headers, rewrites.
- `prerender-manifest.json` — ISR/SSG prerender configuration per route.
- `app-path-routes-manifest.json` — API Route Handler enumeration (Step 2).

If the capture manifest records `build.method: "unavailable"`, record
`manifest_availability: "unavailable"` and produce route-disposition findings
from `discover-configs.md`'s source-config parsing alone, at reduced
confidence.

---

## Step 2: Route-Disposition Comparison (Fallback Confidence)

Produce the same shape of finding as `discover-adapter.md` Step 2, but at LOWER
confidence since this is the fallback signal.

**Classify PAGE routes from the manifests, never from source-level `revalidate`
exports alone.** `routes-manifest.json`'s `staticRoutes`/`dynamicRoutes` and
`prerender-manifest.json`'s `routes` map are the build's OWN routing decision,
which can override a source-level `export const revalidate = N`: a dynamic
route segment (e.g. `/blog/[slug]`) with a `revalidate` export but NO
`generateStaticParams` has nothing to prerender, so Next.js classifies it
`dynamic` in `routes-manifest.json` and it never appears in
`prerender-manifest.json` at all — despite the `revalidate` export still being
present in source. Only a route that actually appears in
`prerender-manifest.json` with an `initialRevalidateSeconds` value is genuinely
`isr`. Do not infer `isr` from a source-level `revalidate` export by itself;
always cross-check against `prerender-manifest.json`'s actual routes:

```json
{
  "route_disposition": [
    { "route": "/", "disposition": "static" },
    {
      "route": "/blog/[slug]",
      "disposition": "dynamic",
      "note": "declares revalidate=3600 in source but has no generateStaticParams; routes-manifest.json places it in dynamicRoutes and it has no entry in prerender-manifest.json - the build's own routing decision overrides the source-level revalidate export"
    },
    { "route": "/dashboard", "disposition": "isr", "revalidate_seconds": 60 }
  ]
}
```

**API Route Handlers (`app/api/*/route.ts`) are NOT covered by
`routes-manifest.json`'s `staticRoutes`/`dynamicRoutes` arrays or by
`prerender-manifest.json`** — those manifests classify page routes only. A
Route Handler compiles straight to `route.js` under
`.next/server/app/<path>/route.js` with no static/ISR manifest entry anywhere,
regardless of whether it's cacheable. For each API route (from
`app-path-routes-manifest.json`'s `*/route` keys, or the file tree directly):
record it with `disposition: "dynamic"` UNLESS the route file itself declares
`export const dynamic = "force-static"` (the one case where a Route Handler can
be static), and set `confidence: "LOW"` (not the fragment's default
`"MEDIUM"`) with
`upgrade_input: "upgrade to Next.js >= 16.2 for the Adapter API's typed build output, which classifies Route Handlers directly (this fragment's manifest sources only classify page routes, so this value is inferred from the absence of a static-export declaration rather than manifest-sourced)"`.

For all PAGE routes classified from the manifests directly (the `static`/`isr`/
`dynamic` entries above), record with `confidence: "MEDIUM"` and
`upgrade_input: "upgrade to Next.js >= 16.2 for the Adapter API's typed build output (a confidence upgrade offer, never a migration prerequisite)"`
— per Requirement 3.4's framing, this upgrade offer must be worded as an offer,
not a gate, even inside the finding's own upgrade_input text.

---

## Step 3: Contribute Manifest Metadata

```json
{
  "manifest_metadata": {
    "adapter_api_used": false,
    "next_version": "<as detected in prescan>",
    "manifest_availability": "available" | "unavailable",
    "fallback_reason": "next_version < 16.2" | "build not clean"
  }
}
```

---

## Step 4: Output Contribution for Parent Orchestrator

The phase assembler (`discover-assemble.md`) owns `discovery.json`'s overall
structure. This fragment contributes the `route_disposition` array (MEDIUM
confidence) and `manifest_metadata` object, each finding carrying
`computed_from_inputs: ["repo_access"]`.

---

## Error Handling

| Error Category                                         | Behavior                                                                                                               |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Capture manifest records `build.method: "unavailable"` | Record `manifest_availability: "unavailable"`, degrade to source-config-only findings, continue — do not halt Discover |
| Captured manifest JSON malformed                       | Record a parse warning, skip the malformed section, continue with what parsed                                          |

---

## Scope Boundary

**This fragment covers the `.next` manifest fallback path ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Running `next build` or any shell command — any best-effort build ran in the
  main window (`discover-capture.md` Step 1); this worker has no shell
- Parsing the Adapter API output path (that is `discover-adapter.md`'s job, and
  this fragment is mutually exclusive with it)
- AWS service names or recommendations
- Coupling Score or Pre-Flight Check computation

**Your ONLY job: read `.next` manifests and produce a reduced-confidence
route-disposition comparison. Nothing else.**
