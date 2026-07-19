# Discover Phase: Capture (Main Window — Pre-Dispatch Work)

> Shell-and-network capture step for the Discover phase. **This file is NOT a
> fragment.** It runs in the MAIN window because it uses the shell (`next build`,
> `curl`) and holds the Vercel API token — things the dispatched `rw` worker
> (Read/Grep/Glob/Write/Edit, no Bash, no network) cannot do and must never
> receive. `discover.md` § Orientation says when to load it: after the entry
> gate passes, BEFORE the phase's work is dispatched.
>
> Its only outputs are raw captures under `$MIGRATION_DIR/capture/` plus a
> `capture/manifest.json` index. The parse-only fragments
> (`discover-adapter.md`, `discover-manifests.md`, `discover-api.md`,
> `discover-probe.md`) consume those files inside the worker. This file never
> writes `discovery.json` sections itself.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Security Contract (applies to every step)

1. **GET-only endpoint whitelist.** The Vercel REST API calls below are the ONLY
   network calls permitted, all HTTP GET. Vercel tokens cannot be scoped
   read-only (resource scoping only — account/team/project), so this whitelist
   IS the read-only guarantee. Never any POST/PATCH/DELETE, never a deploy,
   never an endpoint not in the table.
2. **Token hygiene.** The token lives ONLY in the `VERCEL_TOKEN` environment
   variable for the duration of this step. Never write it to any file (including
   the manifest), never echo it, never pass it as a literal in a logged command
   — always `-H "Authorization: Bearer $VERCEL_TOKEN"` via env interpolation.
3. **Env var VALUES never touch disk.** The env endpoint can return values.
   Request without decryption AND reduce the response to key names in the same
   pipeline (`jq`/`python3` projection) BEFORE redirecting to a file — the raw
   response must never be written. If no filter runtime exists, SKIP env capture
   entirely and record `skipped` in the manifest.
4. **Probe captures are headers-only.** `curl -sS -D <headers-file> -o /dev/null`
   — response BODIES are never saved (they can contain user data). Test-account
   credentials are used for the probe session only and never persisted.
5. **Capture to files, not chat.** Redirect output to `$MIGRATION_DIR/capture/`;
   do not paste large outputs into the conversation. (`.migration/` is
   gitignored by prescan's `_init`.)

---

## Step 1: Build Capture (shell)

Read `tier1-signals.json` for `next_version` and `next_build_health`.

- **Adapter path** (`next_version >= 16.2` AND `next_build_health == "clean"`):
  run the Adapter API build (`next build` with typed output per the project's
  configuration). Copy the typed adapter output to
  `$MIGRATION_DIR/capture/build/adapter-output.json` (or the artifact set the
  adapter emits). Record `build.method: "adapter"`.
- **Manifest path** (anything else): if `.next/` exists from any prior build,
  copy `routes-manifest.json`, `prerender-manifest.json`, and
  `app-path-routes-manifest.json` into `$MIGRATION_DIR/capture/build/`. If no
  `.next/` exists at all, attempt ONE best-effort `next build` to produce them,
  then copy. Record `build.method: "manifests"` and which files were captured.
- **Neither produced artifacts:** record `build.method: "unavailable"` with the
  reason — the config-parsing fragment still runs; Discover degrades, never
  halts.

A build failing here despite PreScan's `"clean"` record is a discrepancy worth
keeping: note it in the manifest (`build.prescan_discrepancy: true`) so
`discover-adapter.md` can record its LOW-confidence finding.

## Step 2: API Capture (network, GET-only)

For each in-scope project from `tier1-signals.json.project_list`.

**Transport — prefer `vercel api`, fall back to `curl`:** when the Vercel CLI is
installed, run rows as `vercel api <endpoint> --token "$VERCEL_TOKEN"` — it
authenticates the same way, auto-paginates with `--paginate` (list endpoints cap
at 100 per page and return `pagination.next` cursors), and its `vercel api list`
subcommand exposes the live OpenAPI spec for the rows below marked
"OpenAPI-discovered". (The command is beta; on any wobble, fall back to raw
`curl`.) Raw-curl form: `curl -sS -H "Authorization: Bearer $VERCEL_TOKEN"`
against `api.vercel.com`, following `pagination.next` cursors manually when a
response is paginated. Either way, output goes to the named file under
`$MIGRATION_DIR/capture/api/`. On 403 (token scope) or 429 (rate limit, retry
once after backoff — documented per-endpoint limits are 200–1000 reads/min,
orders of magnitude above this capture's volume): record `failed`/partial in the
manifest and continue — never a halt.

| # | Endpoint (GET)                                                                           | Output file                  | Notes                                                                                                                                                                                                                                                                                                     |
| - | ---------------------------------------------------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | `/v2/teams`                                                                              | `teams.json`                 | team ids for subsequent calls                                                                                                                                                                                                                                                                             |
| 2 | `/v10/projects?teamId=<id>`                                                              | `projects.json`              | framework, latest deployment metadata                                                                                                                                                                                                                                                                     |
| 3 | `/v6/deployments?projectId=<id>&limit=20`                                                | `deployments-<project>.json` | production vs preview, timestamps, state                                                                                                                                                                                                                                                                  |
| 4 | `/v10/projects/<id>/env?teamId=<id>&decrypt=false` **piped through key-name projection** | `env-keys-<project>.json`    | KEY NAMES ONLY — e.g. `... \| jq '[.envs[].key] \| sort'`; never write the raw response (rule 3). The documented response schema carries `value`/`vsmValue`/`legacyValue` fields even with `decrypt=false` — the projection is the REAL protection, not the query param                                   |
| 5 | `/v9/projects/<id>/domains?teamId=<id>`                                                  | `domains-<project>.json`     | custom domains (paginated — max 100/page)                                                                                                                                                                                                                                                                 |
| 6 | project cron configuration — OpenAPI-discovered                                          | `crons-<project>.json`       | NOT in the public REST reference; look it up via `vercel api list` and use the GET endpoint found there, else record `skipped` (the `vercel.json` cron declarations from `discover-configs.md` remain the primary source)                                                                                 |
| 7 | storage/stores enumeration — OpenAPI-discovered                                          | `stores.json`                | store endpoints exist (documented rate limits) but their paths are NOT in the public REST reference; look up the GET endpoints via `vercel api list`, else record `skipped` and rely on env-name + dependency signals (`@vercel/kv`, `KV_REST_API_*`, etc.), which the coupling item already corroborates |
| 8 | usage/analytics aggregates as exposed for the plan (best-effort)                         | `usage-<project>.json`       | coarse invocation/bandwidth aggregates; absent on many plans — record `skipped`, not an error                                                                                                                                                                                                             |

## Step 3: Header-Probe Capture (network, Tier 2 only)

ONLY if a production URL + throwaway test account were supplied (Tier 2). For a
representative route sample (overlap with likely route dispositions):

```
curl -sS -D $MIGRATION_DIR/capture/probe/<route-slug>.headers -o /dev/null <url>
```

Headers only (rule 4). Authenticated probes use the test-account session for the
request only. Record each probed route + HTTP status in the manifest; 401/403 and
bot-challenge responses are captured as-is (they are findings, not errors).

## Step 4: Write the Manifest

`$MIGRATION_DIR/capture/manifest.json`:

```json
{
  "captured_at": "<ISO 8601 UTC>",
  "build": {
    "method": "adapter|manifests|unavailable",
    "files": ["..."],
    "prescan_discrepancy": false,
    "reason": null
  },
  "api": [
    {
      "endpoint": "/v10/projects",
      "file": "api/projects.json",
      "status": "ok|failed|skipped",
      "note": null
    }
  ],
  "probe": { "attempted": false, "routes": [] }
}
```

Every attempted or deliberately skipped row gets an entry. The manifest is the
parse fragments' index — its existence is what tells `discover.md` capture ran.

## Step 5: Return to `discover.md`

Tell the founder in one line what was captured and anything that failed or was
skipped, then continue per `discover.md` (dispatch the phase's work). Do NOT
parse captures here, do NOT write `discovery.json`, and do NOT update
`.phase-status.json`.

---

## Optional Enrichment: Vercel MCP (note, not a step)

If the founder's client is connected to Vercel's official MCP
(`https://mcp.vercel.com`, OAuth), its `get_runtime_logs` tool can substitute for
a log-drain export (upgrading LOW-confidence usage findings) and
`create_access_link`/`web_fetch_vercel_url` can substitute for a test account on
protected deployments. Treat MCP output as capture input: write what's needed to
`capture/` files and record it in the manifest with `source: "vercel_mcp"`.
Cautions: the OAuth grant is FULL account access and the server exposes
purchase/deploy tools — advise the founder to enable per-tool human confirmation;
never invoke any non-read MCP tool from this skill.

---

## Error Handling

| Error                                       | Behavior                                                                                                                               |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Token invalid/expired mid-capture           | Stop capturing; ask the founder for a fresh token (see `prescan-collect.md` Step 2); on resume re-run Step 2 rows (captures overwrite) |
| Individual endpoint 403/404                 | Record `failed`/`skipped` with the reason; continue                                                                                    |
| Rate limited (429)                          | Retry once after backoff; then record `failed`; continue                                                                               |
| Build tools unavailable                     | `build.method: "unavailable"` with reason; continue                                                                                    |
| No filter runtime (jq/python3) for env keys | Skip env capture entirely (rule 3); record `skipped`                                                                                   |

**Key principle:** partial capture degrades confidence downstream; it never
halts Discover.

## Scope Boundary

**This file covers capture ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Parsing captures into findings (the fragments' job, in the worker)
- Writing `discovery.json`, `coupling-score.json`, or `preflight-findings.json`
- Any non-GET API call, any deploy, any MCP tool that is not read-only
- Env var values, token values, or probe response bodies on disk

**Your ONLY job: run the shell/network capture and index it. Nothing else.**
