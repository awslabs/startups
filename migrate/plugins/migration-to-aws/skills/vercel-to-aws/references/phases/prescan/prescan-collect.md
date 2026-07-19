---
_fragment: tier1-collect
_of_phase: prescan
_contributes:
  - tier1-signals.json (repo_access, next_build_health, vercel_token_present, project_list sections)
---

# PreScan Phase: Tier 1 Input Collection

> Self-contained fragment. Validates the three required Tier 1 inputs and records
> their state. Does NOT determine `_preconditions` pass/fail itself — that is the
> parent `prescan.md`'s `_assert` — this fragment produces the DATA the assert
> reads.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Repo Access + `next build` Health Check

### 1a. Confirm Repo Access

Confirm the workspace contains a readable Next.js project (a `package.json` with a
`next` dependency, or equivalent). If no such project is found anywhere in the
workspace, record `repo_access: false` and stop this fragment — the parent's
`_preconditions` `_assert` will fail `_unrecoverable` on this.

### 1b. Run `next build` Locally

Per Requirement 1.1-1.2: attempt to run `next build` in the detected project root.

- **If the build runs clean (exit 0):** record `next_build_health: "clean"`.
- **If the build fails or exits non-zero:** record `next_build_health: "failed"`
  plus a short summary of the failure (do NOT paste the full build log — summarize
  the error class, e.g. "TypeScript error", "missing environment variable",
  "dependency resolution failure"). **This is NOT a precondition failure** — a
  broken build outside Vercel's CI is itself a finding (Requirement 1.2), not a
  blocker. Continue.
- **If `next build` cannot be attempted at all** (no package manager available,
  no `node_modules`, etc.): record `next_build_health: "unattempted"` with the
  reason. Continue — this degrades Discover's signal priority (Requirement 4.1)
  toward the manifest-fallback path, but is not fatal here.

Record `repo_access: true` once a Next.js project is confirmed readable,
regardless of the build outcome.

---

## Step 2: Vercel API Token

Per Requirement 1.7: when requesting the token from the founder, state explicitly:

> "I'll need a Vercel API token to enumerate your projects, deployments, env var
> names, domains, crons, and storage integrations. Two honest notes before you
> create one:
>
> 1. **Vercel tokens can't be made read-only** — they scope by resource
>    (account / team / single project), not by permission. On my side, this
>    assessment only ever issues read (GET) requests, enforced by the endpoint
>    whitelist in the capture step — but the token itself could do more, so
>    scope it as narrowly as possible: a **project-scoped** token if one project
>    is in scope (Dashboard → Account Settings → Tokens, or
>    `vercel tokens create <name> --project <PROJECT_ID>` if you already hold a
>    classic account token), team-scoped only if we need to discover multiple
>    projects.
> 2. Pick the **shortest practical expiration**, and revoke it the moment this
>    assessment completes (`vercel tokens rm <token-id>`, or from the same
>    dashboard page)."

The token is held ONLY as an environment variable (`VERCEL_TOKEN`) in the main
window for this run — see `discover-capture.md`'s Security Contract for how the
capture step uses it without it ever entering an artifact or a dispatched
worker.

- If a token is supplied: validate it can authenticate against the Vercel API
  (a lightweight call, e.g. listing the team). Record `vercel_token_present: true`.
- If no token is supplied: record `vercel_token_present: false`. The parent's
  `_preconditions` `_assert` will fail `_unrecoverable` on this — Tier 1 requires
  it (Requirement 1.1).
- **Never** log, persist, or echo the token value itself anywhere in
  `tier1-signals.json`, `assessment-state.json`, or any output message.

---

## Step 3: Project Scope

Using the validated token, enumerate the founder's Vercel projects/teams.

- If exactly one project is found: record `project_list: [<that project>]` and a
  `project_scoping_needed: false` flag (Requirement 2.3 — Clarify will skip the
  project-scoping question).
- If multiple projects are found: record the full `project_list` and
  `project_scoping_needed: true`. Do NOT resolve scoping here — Clarify asks the
  founder which project(s) are in scope (per PreScan's role: gather facts, not
  make decisions).
- If zero projects are found despite a valid token: record `project_list: []`.
  The parent's `_preconditions` `_assert` fails `_unrecoverable` — Requirement 1.1
  requires at least one in-scope project.

---

## Step 4: Opportunistic Tier 2/3 Detection

If the founder has ALREADY supplied any Tier 2/3 inputs unprompted at this point
(e.g. dropped a log drain export into the workspace, or mentioned invoices), record
them in `inputs_received.tier2`/`tier3` contributions now rather than waiting for
Discover to re-ask. This is opportunistic only — do not prompt for Tier 2/3 here;
that would defeat PreScan's cheap, minimal-friction purpose.

---

## Step 5: Output Contribution for Parent Orchestrator

The phase assembler (`prescan-assemble.md`) owns `tier1-signals.json`'s overall
structure. This fragment contributes:

```json
{
  "repo_access": true,
  "next_build_health": "clean" | "failed" | "unattempted",
  "next_build_failure_summary": "<short summary, only if failed>",
  "vercel_token_present": true,
  "project_list": ["<project-name>", ...],
  "project_scoping_needed": false
}
```

---

## Error Handling

| Error Category                                    | Behavior                                                                                              |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `next build` command not found (no npm/pnpm/yarn) | Record `next_build_health: "unattempted"`, reason: "no package manager available"                     |
| Vercel API token invalid/expired                  | Record `vercel_token_present: false`, do NOT retry with the same token silently                       |
| Vercel API rate-limited                           | Record a `vercel_api_warning` field, retry once after a short backoff, then proceed with partial data |

---

## Scope Boundary

**This fragment covers Tier 1 validation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Full Discover-level signal extraction (Adapter API build, manifest parsing)
- AWS service names or recommendations
- Coupling Score or Pre-Flight Check computation
- Clarify questions

**Your ONLY job: Confirm the three Tier 1 inputs and record their state.**
