---
_fragment: header-probe
_of_phase: discover
_contributes:
  - discovery.json (header_probe_results, probe_limitations sections)
---

# Discover Phase: Header-Probe Confirmation (Tier 2 Only)

> Self-contained PARSE-ONLY fragment. Triggered ONLY when the capture manifest
> records probe captures (`capture/manifest.json` → `probe.attempted: true` —
> the probing itself, with the Tier 2 production URL + throwaway test account,
> happened in the main window via `discover-capture.md` Step 3; this worker has
> no network). This fragment is CONFIRMATION-ONLY per Requirement 4.1 — its
> findings never serve as a primary signal; they confirm or contradict what
> `discover-configs.md`/`discover-adapter.md` already determined.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Parse Probed Route Headers

Read each `capture/probe/<route-slug>.headers` file listed in the manifest —
header captures of a representative route sample, ideally overlapping with the
route-disposition comparison from `discover-adapter.md`/`discover-manifests.md`
so the probe can confirm or contradict those findings.

For each probed route, read from its headers file:

- `x-vercel-cache` — hit/miss/stale, confirms actual caching behavior.
- `cache-control` — the response's actual cache directive.
- `age` — how long the response has been cached.

---

## Step 2: Cross-Reference Against Existing Findings

For each probed route, compare the observed caching behavior against the
route-disposition finding already recorded (static/ISR/dynamic/edge). Record
agreement or disagreement:

- **Agreement:** does NOT upgrade the existing finding's confidence tier by
  itself (per Requirement 4.1, header probes never serve as primary) — but MAY
  be cited as corroborating evidence in the report's decision traceability.
- **Disagreement:** record as a new, separate LOW-confidence finding flagging
  the discrepancy for founder attention. Do NOT silently overwrite the
  higher-authority finding.

---

## Step 3: Record Probe Limitations (Requirement 4.6, Mandatory)

ALWAYS record known probe limitations alongside any finding this fragment
produces, regardless of whether the probe succeeded cleanly:

```json
{
  "probe_limitations": [
    "auth walls may prevent probing routes behind login",
    "bot protection (e.g. Vercel's own) may return different responses to automated probes than to real users",
    "geo variance - CDN edge location probed from may not represent all regions",
    "preview-vs-prod divergence - probing preview URLs does not confirm production behavior"
  ]
}
```

This list is NOT optional or conditional — it accompanies every use of this
fragment's output in the report.

---

## Step 4: Output Contribution for Parent Orchestrator

```json
{
  "header_probe_results": [
    {
      "route": "/blog/[slug]",
      "x_vercel_cache": "HIT",
      "cache_control": "s-maxage=3600",
      "age": "120",
      "agrees_with_disposition": true
    }
  ],
  "probe_limitations": ["<see Step 3 list>"]
}
```

Every finding here carries `confidence: "LOW"` at most (confirmation-only, never
primary) and `computed_from_inputs: ["production_url_and_test_account"]`.

---

## Error Handling

| Error Category                                   | Behavior                                                                                                                                  |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Route returns a 401/403 (behind auth wall)       | Record as `"blocked: auth_wall"`, do not retry with different credentials — the test account's actual permissions are what's being tested |
| Route returns a CAPTCHA/bot-protection challenge | Record as `"blocked: bot_protection"`, this is itself informative (confirms bot protection exists)                                        |
| Test account credentials expired/invalid         | Record `"probe_unavailable: invalid_credentials"`, do not fail Discover — this is an optional Tier 2 input                                |

---

## Scope Boundary

**This fragment covers header-probe-capture PARSING only.**

FORBIDDEN — Do NOT include ANY of:

- Any network call or `curl` — probing already happened in the main window
  (`discover-capture.md` Step 3, which enforces headers-only capture and the
  founder-authorization rule)
- Treating any probe result as a PRIMARY signal (always confirmation-only)
- AWS service names or recommendations

**Your ONLY job: confirm or flag discrepancies against existing findings via
header probing, with limitations always disclosed. Nothing else.**
