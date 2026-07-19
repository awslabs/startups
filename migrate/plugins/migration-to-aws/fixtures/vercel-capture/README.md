# Vercel capture fixtures (replay mode)

Canned capture output for testing the `vercel-to-aws` Discover phase's
capture/parse split (`discover-capture.md` → parse-only fragments → assembler)
without a Vercel account or a real Next.js build. The synthetic project
`acme-shop` exercises the designed-for paths:

- **Manifest fallback** — Next.js 15.1.0 (< 16.2), so `build.method:
  "manifests"`; the captured `capture/build/` manifests (`routes-manifest` /
  `prerender-manifest` / `app-path-routes-manifest`, exactly the three files
  the capture manifest's `build.files` names) drive route dispositions,
  including the two subtle
  cases: `/blog/[slug]` is genuinely ISR (real `initialRevalidateSeconds`
  entries in `prerender-manifest.json`), and `/api/checkout` is a Route Handler
  the manifests do NOT classify (must land `dynamic` at LOW confidence with the
  Adapter-API `upgrade_input`).
- **API captures with realistic gaps** — crons endpoint `skipped` (404 on plan;
  the `vercel.json` cron remains the source), usage aggregates `skipped`; env
  capture already reduced to KEY NAMES ONLY, deliberately including
  secret-looking names (`STRIPE_SECRET_KEY`, `KV_REST_API_TOKEN`) — if a value
  ever appears in output, the projection rule broke.
- **Storage integrations** — a KV store and a Postgres store feed
  `peripherals[]` (the separability check's input).
- **No probe** — `probe.attempted: false`; the probe fragment must not run.
- **Workspace files** — `package.json`, `vercel.json` (cron + headers +
  `maxDuration`), `middleware.ts` (auth gate + rewrite, with matcher),
  `next.config.js` for `discover-configs.md`.

## How to replay

1. Create a scratch directory; copy `workspace/*` into its root.
2. Create `.migration/0721-1725/` inside it; copy `capture/` and `seed/*`
   (including the dot-file `.phase-status.json`) into that run directory.
   The seed marks prescan `completed` (with its two artifacts) and discover
   `in_progress` — the state right after the capture pre-work finished.
3. Invoke the vercel-to-aws skill's Discover phase (resume the run).
4. Discover's capture `_precondition` passes via the existing
   `capture/manifest.json`; the fragments parse the captures — zero network
   calls, zero builds, no token anywhere.
5. Check the run dir against `expected-discovery.json`:
   `python3 check_expected_discovery.py <run-dir>` (exits non-zero on any
   failed assertion, including secret-hygiene checks).

**Estimate replay** (seeded mid-pipeline, no discover run needed):

1. Scratch directory with `workspace/*` at root; copy `seed-estimate/*`
   (including `.phase-status.json`) into `.migration/0721-1725/`. The seeds
   are a validated discover→clarify→recommend chain replay's outputs: Q6
   spend answered `$200-1000`, recommendation an unresolved `["A","B"]`
   tiebreak (Q1 traffic shape declined, no log drain).
2. Resume the run — the Estimate phase starts. Expect a `user_provided`
   baseline of exactly **$600/mo** (the documented range midpoint), BOTH
   outcomes priced (`projected_costs` = Outcome A, `tiebreak_alternative` =
   Outcome B, Property-16 on each), and tiebreak honesty in the summary.
3. `python3 check_expected_estimate.py <run-dir>`.

**Generate replay** (seeded post-estimate):

1. Scratch directory with `workspace/*` at root; copy `seed-generate/*`
   (including `.phase-status.json`) into `.migration/0721-1725/`.
2. Resume the run — Generate starts and, per `generate.md`, must ASK which
   tiebreak path to take: the replay founder answers "Outcome A
   (OpenNext/SST)".
3. Expect the full artifact set (sst.config.ts + terraform/ + scripts/ +
   docs + generation-warnings.json), OpenNext/Fargate mutual exclusion, no
   placeholder tokens, no compliance resources (Q8 = none), and assembler
   Step 6's terraform validate handled per environment (pass = no warning
   entry; fail/skip = exactly one entry with a founder-facing action).
4. `python3 check_expected_generate.py <run-dir>`.

**What a run must never produce:** env var values or token material anywhere;
any network call or `next build`; AWS recommendations inside discover
artifacts; a halt caused by the skipped crons/usage captures.

## Regenerating / extending

Captures follow `discover-capture.md`'s endpoint whitelist and file naming. If
you add an endpoint: whitelist row first, then fixture, then extend
`expected-discovery.json`. All ids, names, and hostnames are synthetic.
