---
_fragment: build-free-scan
_of_phase: prescan
_contributes:
  - tier1-signals.json (next_version, package_manager, has_sharp_dependency, lockfile_census, has_middleware, has_vercel_json sections)
---

# PreScan Phase: Build-Free Workspace + API Scan

> Self-contained fragment. Performs the cheap, build-free pass over the workspace
> and the Vercel API that lets Clarify ask fact-driven questions instead of
> guessing. Explicitly does NOT run `next build` or any build step — that
> distinction is the whole reason this fragment and Full Discover are separate
> (Requirement 2.2).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 1: Parse `package.json`

Read the workspace's `package.json` (the same Next.js project confirmed in
`prescan-collect.md` Step 1a).

- **Next.js version:** extract the `next` dependency's declared version. Record
  as `next_version` (e.g. `"16.2.0"`). This drives Discover's signal-priority
  fragment selection (Requirement 4.1) and Clarify's version-rule framing
  (Requirement 3.4).
- **`packageManager` field:** record as `package_manager` (e.g. `"pnpm@9.0.0"`,
  or `null` if absent).
- **`sharp` dependency:** check `dependencies` and `devDependencies` for a direct
  `sharp` entry. Record `has_sharp_dependency: true|false` — this feeds
  Pre-Flight Check B3 later in Discover.

---

## Step 2: Lockfile Census

Glob the workspace root for lockfiles: `package-lock.json`, `yarn.lock`,
`pnpm-lock.yaml`, `bun.lockb`.

- Record `lockfile_census`: the list of lockfiles found (there may be more than
  one — a monorepo misconfiguration). This feeds Pre-Flight Check B1
  (monorepo lockfile conflicts) later in Discover; this fragment only records the
  raw count/list, it does not compute the B1 finding itself.

---

## Step 3: `middleware.ts` Existence Check

Glob for `middleware.ts` / `middleware.js` at the project root or `src/`.

- Record `has_middleware: true|false`.
- **Do NOT parse the matcher or middleware body here** — that is Full Discover's
  job (`discover-configs.md`). This fragment only checks existence, cheaply.
  Note: this skill's fixed Clarify question set does not contain a
  middleware-specific question at all — Discover's static analysis
  (`middleware_analysis.per_matcher_pattern`) is the sole source for "what does
  your middleware do," at MEDIUM-HIGH confidence, and runs AFTER PreScan but
  BEFORE Clarify in this skill's backbone (`prescan` -> `discover` -> `clarify`
  -> ...). `has_middleware` is recorded here because Pre-Flight Check M1's
  detection and the Coupling Score's `edge_middleware` item both need to know
  whether a middleware file exists at all before Discover runs its own parse
  — not because Clarify consults this flag to decide whether to ask a
  question (see `clarify-ask.md`'s Skip Logic for the one place `has_middleware`
  IS consulted, which is to confirm no such question exists to skip).

---

## Step 4: `vercel.json` Presence Check

Glob for `vercel.json` at the project root.

- Record `has_vercel_json: true|false`. Do NOT parse its contents here — that is
  Full Discover's job (`discover-configs.md`).

---

## Step 5: Vercel Project Enumeration (via API)

Using the token validated in `prescan-collect.md` Step 2, enumerate projects via
the Vercel REST API. This is the SAME enumeration `prescan-collect.md` Step 3
uses for `project_list`/`project_scoping_needed` — do not duplicate the API call;
if `prescan-collect.md` already produced this data (fragments run independently,
so coordinate via a shared read of the API response if the host allows it,
otherwise a second lightweight call is acceptable), reuse it. Record nothing
further here beyond confirming the enumeration succeeded — `project_list` itself
is `prescan-collect.md`'s contribution.

---

## Step 6: Output Contribution for Parent Orchestrator

The phase assembler (`prescan-assemble.md`) owns `tier1-signals.json`'s overall
structure. This fragment contributes:

```json
{
  "next_version": "16.2.0",
  "package_manager": "pnpm@9.0.0",
  "has_sharp_dependency": false,
  "lockfile_census": ["pnpm-lock.yaml"],
  "has_middleware": true,
  "has_vercel_json": true
}
```

---

## Error Handling

| Error Category                                | Behavior                                                                                                                           |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `package.json` missing or unparseable         | Record `next_version: null`, reason: "package.json unreadable" — this degrades Discover toward manifest-fallback (Requirement 4.1) |
| Multiple lockfiles found                      | Record all of them in `lockfile_census` — do NOT resolve or warn here, that is Pre-Flight Check B1's job in Discover               |
| `middleware.ts` exists but is empty/malformed | Record `has_middleware: true` regardless — existence only, not validity                                                            |

---

## Scope Boundary

**This fragment covers the build-free scan ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Running `next build` or any build step
- Parsing `middleware.ts`'s matcher or body (existence check only)
- Parsing `vercel.json`'s contents (presence check only)
- Computing Coupling Score or Pre-Flight Check findings
- AWS service names or recommendations

**Your ONLY job: Perform the cheap, build-free scan and record raw facts. Nothing
else.**
