# Implementation Plan: Vercel-to-AWS Migration Skill

## Overview

This plan implements the `vercel-to-aws` skill for the `migration-to-aws` plugin: a 5-backbone-phase + 1-checkpoint DSL skill (`prescan` -> `discover` -> `clarify` -> `recommend` -> `report`, with an optional `scaffold` checkpoint) per `design.md`. All "code" is markdown phase/fragment files carrying DSL frontmatter, JSON knowledge tables and schemas, and one new Python validator script with its pytest suite. The skill lives at `migrate/plugins/migration-to-aws/skills/vercel-to-aws/`, with one new sibling script under `migrate/plugins/migration-to-aws/scripts/`.

This is a new skill, not a modification to `gcp-to-aws` or `heroku-to-aws` — those skills are read-only precedent, not touched by this plan, except for the plugin-level `README.md` and `.claude-plugin`/`.codex-plugin`/`.cursor-plugin` manifests that need to list the new skill.

**Status: Implementation complete.** All tasks below are checked off. Verified via: the plugin's own `tools/frontmatter-validator` (structural DSL check — 0 problems across all 6 phases), the `test_validate_assessment_report.py` pytest suite (36/36 passing), both fixtures run end-to-end through the real validator script (reference passes, stub fails with the expected actionable errors), and byte-identity diffs on the two vendored files against canonical source.

## Tasks

- [x] 1. Scaffold the skill shell and vendor the shared DSL
  - [x] 1.1 Create `skills/vercel-to-aws/SKILL.md`
    - Frontmatter: `name`, `description` with trigger phrases ("migrate from Vercel", "Vercel to AWS", "move off Vercel", "migrate Next.js off Vercel", "assess my Vercel migration", etc.), modeled on `heroku-to-aws/SKILL.md`'s frontmatter shape
    - Philosophy section: derive-don't-discover, assessment-is-the-durable-value, honest-by-construction, generation-aware (OpenNext v3 today, swappable for the verified Adapter API adapter), prose-to-gate parity — per requirements.md Introduction and design.md Overview
    - Declare the entry phase (`prescan`) explicitly, per `INTERPRETER.md` § The interpreter loop step 1 (cold start loads the declared entry directly, never scans for it)
    - State the "Clarify is mandatory" policy analogous to Heroku's, adapted: clarify cannot be skipped even though its questions are fewer and gated on PreScan/Discover output
    - File structure tree (mirrors design.md's File Structure section)
    - Context loading budget note (~800 lines per phase, same convention as Heroku)
    - _Requirements: Introduction, Requirement 2, Requirement 3_

  - [x] 1.2 Vendor the shared DSL and state schema into `references/vendored/`
    - Copy `skills/shared/dsl/INTERPRETER.md` -> `skills/vercel-to-aws/references/vendored/dsl/INTERPRETER.md` (byte-identical)
    - Copy `skills/shared/state/phase-status.schema.json` -> `skills/vercel-to-aws/references/vendored/state/phase-status.schema.json` (byte-identical)
    - Add `skills/vercel-to-aws/references/vendored/README.md` documenting the vendored-path -> canonical-source mapping, same shape as the existing `heroku-to-aws/references/vendored/README.md` table
    - Register the new vendored paths in `mise run shared:sync` / `mise run shared:check` so CI enforces byte-identity going forward
    - _Requirements: Introduction (DSL contract paragraph)_

  - [x] 1.3 Author `skills/vercel-to-aws/references/state/assessment-state.schema.json`
    - Full schema per design.md §2.1 (schema_version, migration_id, last_updated, inputs_received{tier1,tier2,tier3}, findings, clarify_answers, report_history)
    - This is skill-owned, NOT vendored — it has no canonical source elsewhere in the plugin
    - _Requirements: 11.1, 11.5_

- [x] 2. Checkpoint — Skill shell review
  - Ensure `SKILL.md` loads cleanly, vendored files are byte-identical to canonical source (`mise run shared:check` passes), ask the user if questions arise.

- [x] 3. Implement the `prescan` phase (entry phase)
  - [x] 3.1 Create `phases/prescan/prescan.md` (orchestrator)
    - Frontmatter per design.md §1.1 verbatim (`_init: true`, `_exec: rw`, `_fragments`, `_produces: [tier1-signals.json, assessment-state.json]`, `_preconditions`/`_postconditions`, `_forbids_files`)
    - Prose: Step 0 `_init` state setup (creates `.migration/`, `.phase-status.json`, AND `assessment-state.json` — the skill-owned ledger), Step 1 runs fragments, Step 2 assembles, Step 3 completion gate
    - _Requirements: 1.1, 1.2, 1.6, 1.7_

  - [x] 3.2 Create `phases/prescan/prescan-collect.md` (fragment: tier1-collect)
    - Validates the three Tier 1 preconditions: repo access + `next build` health check (non-fatal finding if the build isn't clean, per Requirement 1.2), read-only team-scoped Vercel API token with the least-privilege ask statement (Requirement 1.7), in-scope project list
    - Fragment frontmatter: `_fragment: tier1-collect`, `_of_phase: prescan`, `_contributes: tier1-signals.json (repo_access, next_build_health, vercel_token_present, project_list sections)`
    - _Requirements: 1.1, 1.2, 1.7_

  - [x] 3.3 Create `phases/prescan/prescan-scan.md` (fragment: build-free-scan)
    - Build-free pass: `package.json` (Next.js version, `packageManager`, `sharp` dep), lockfile census, `middleware.ts` existence check, `vercel.json` presence check, Vercel API project enumeration
    - Explicit prose guard: "Do NOT run `next build` or any build step in this fragment — that is Discover's job (Requirement 2.2)"
    - _Requirements: 2.1, 2.2_

  - [x] 3.4 Create `phases/prescan/prescan-assemble.md` (assembler)
    - Merges both fragments into `tier1-signals.json` per the schema implied by `prescan`'s `_postconditions` `_assert` (next_version, package_manager, has_middleware, has_vercel_json, project_list)
    - Seeds `assessment-state.json.inputs_received.tier1.*` and initializes empty `findings`/`clarify_answers`/`report_history`
    - Runs the completion gate, emits `HANDOFF_OK | phase=prescan | artifacts=...`
    - _Requirements: 1.5, 11.1_

- [x] 4. Checkpoint — PreScan phase integration
  - Manually verify: a repo with no `middleware.ts` produces `has_middleware: false` in `tier1-signals.json`; a repo with only one Vercel project skips project-scoping metadata. Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement the `discover` phase
  - [x] 5.1 Create `phases/discover/discover.md` (orchestrator)
    - Frontmatter per design.md §1.2 verbatim (7 fragments, `_knowledge` for `preflight-checks.json`/`coupling-weights.json`, `_re_entry_guard` against `clarify`)
    - Prose: signal-priority explanation (Requirement 4.1), explicit statement that Coupling Score and Pre-Flight fragments run unconditionally regardless of what Recommend will later decide (Requirement 6.2)
    - _Requirements: 4.1, 4.2, 4.3, 6.2_

  - [x] 5.2 Create `phases/discover/discover-adapter.md` (fragment: adapter-build)
    - Triggered only when `next_version >= 16.2 AND next build runs clean`
    - Runs the Adapter API build, consumes its typed/versioned output, produces the route-disposition comparison (static/ISR/dynamic/edge per route) as an informational finding (Requirement 4.2)
    - Explicit scope boundary: no full "what Vercel provisions vs. OpenNext provisions" infra diff in v1 (Requirement 4.3)
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.3 Create `phases/discover/discover-manifests.md` (fragment: manifest-fallback)
    - Triggered when `next_version < 16.2 OR next build does not run clean`
    - Reads `.next` routes manifest / prerender manifest as the fallback signal source
    - _Requirements: 4.1_

  - [x] 5.4 Create `phases/discover/discover-configs.md` (fragment: source-configs)
    - Always runs: parses `next.config.js` (route segment configs, `revalidate`, `runtime: 'edge'`, image config) and `middleware.ts` + matcher scope
    - Also parses `vercel.json` (headers, redirects, rewrites, function `maxDuration`/`memory`, regions, crons) per signal-priority order
    - _Requirements: 4.1_

  - [x] 5.5 Create `phases/discover/discover-api.md` (fragment: vercel-api)
    - Always runs: Vercel REST API calls for projects, deployments, env var names (never values), domains, cron jobs, Edge Config, KV/Postgres/Blob store enumeration, coarse usage metrics
    - Enforces Requirement 1.6: never persists secret values, Tier 3 env var collection scoped to hostnames only
    - _Requirements: 1.6, 4.1_

  - [x] 5.6 Create `phases/discover/discover-probe.md` (fragment: header-probe)
    - Triggered only when Tier 2's production URL + throwaway test account were supplied
    - Curl production routes, read `x-vercel-cache`/`cache-control`/`age` headers; explicitly confirmation-only, never primary (Requirement 4.1)
    - Records known probe limitations alongside any finding it produces (Requirement 4.6): auth walls, bot protection, geo variance, preview-vs-prod divergence
    - _Requirements: 4.1, 4.6_

  - [x] 5.7 Create `phases/discover/discover-coupling.md` (fragment: coupling-score)
    - Always runs: computes the full Coupling_Score inventory (ISR, edge middleware, edge runtime routes, image optimization, streaming SSR, Server Actions/skew, preview deployments, KV/Postgres/Blob/Edge Config/Cron, Vercel-injected headers), each with detection method + weight rationale
    - Implements the design.md §"Resolved Design Decisions" item 1 short-circuit preamble: before computing each item, check `assessment-state.json.findings.<finding_id>.computed_from_inputs` against `newly_received`; skip recompute for unaffected items on a warm re-entry
    - _Requirements: 5.1, 5.2, 11.3_

  - [x] 5.8 Create `phases/discover/discover-preflight.md` (fragment: preflight-checks)
    - Always runs: computes all 10 named checks (M1, M2, B1-B4, S1, I1, O1, U1) per the table in Requirement 6.1, each carrying its `applies_to` outcome set and (where applicable) `adapter_generation` tag
    - Explicit note that M1 is generation-independent (Requirement 6.5) and applies regardless of eventual outcome
    - Same recompute short-circuit preamble as 5.7
    - Loads `knowledge/preflight-checks.json` (see task 9.1) for the check definition table rather than inlining it
    - _Requirements: 6.1, 6.2, 6.5, 11.3_

  - [x] 5.9 Create `phases/discover/discover-assemble.md` (assembler)
    - Merges all 7 fragment contributions into `discovery.json`, `coupling-score.json`, `preflight-findings.json`
    - Assigns Confidence_Tier (LOW/MEDIUM/HIGH) to every finding per Requirement 4.4-4.5, naming the specific missing `upgrade_input` when sub-HIGH
    - Writes back into `assessment-state.json`: `inputs_received.tier2/tier3.*`, all `findings` entries with `computed_from_inputs` populated (per design.md §2.2)
    - Runs the completion gate including the "all 10 pre-flight checks present regardless of eventual recommendation" `_assert`
    - _Requirements: 4.4, 4.5, 6.1, 6.2, 11.1_

- [x] 6. Checkpoint — Discover phase integration
  - Manually verify: a fixture repo on Next.js 15 produces `manifest-fallback` findings only (no adapter-build); a fixture on Next.js 16.2+ with a clean build produces `adapter-build` findings; `preflight-findings.json` always has exactly 10 entries regardless of fixture. Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement the `clarify` phase
  - [x] 7.1 Create `phases/clarify/clarify.md` (orchestrator)
    - Frontmatter per design.md §1.3 verbatim (`_interactive: true`, no `_exec`, `_re_entry_guard` against `recommend`)
    - Prose: mandatory-clarify policy (cannot be skipped even if the founder asks), consult `tier1-signals.json` + `discovery.json` first to skip already-answered questions (Requirement 2.3)
    - _Requirements: 2.3, 3.1_

  - [x] 7.2 Create `phases/clarify/clarify-ask.md` (fragment: ask)
    - Implements the fixed question set (Requirement 3.1): traffic shape, migration trigger, team DevOps bandwidth, preview-dependence, Next.js-upgrade willingness
    - Skip logic: no middleware question when `tier1-signals.json.has_middleware == false`; no project-scoping question when only one in-scope project (Requirement 2.3)
    - Version-rule framing (Requirement 3.3-3.4): presents the Next.js-upgrade question as a "confidence upgrade offer," explicitly never as a migration gate; does not block on this answer (Requirement 3.5)
    - Every answer recorded with `prompt` + `design_consequence` fields (Requirement 3.2)
    - _Requirements: 2.3, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 7.3 Create `phases/clarify/clarify-assemble.md` (assembler)
    - Writes `clarify-answers.json`; writes `assessment-state.json.clarify_answers.*` per design.md §2.2
    - Completion gate `_assert`s per design.md §1.3: every answer has all three fields, no redundant question was asked, upgrade question was never gating
    - _Requirements: 3.2, 11.1_

- [x] 8. Checkpoint — Clarify phase integration
  - Manually verify: re-running Clarify against a repo with no middleware never surfaces the middleware question; the Next.js-upgrade answer never blocks phase completion when declined. Ensure all tests pass, ask the user if questions arise.

- [x] 9. Author knowledge tables (pure data, referenced by Discover/Recommend/Scaffold `_knowledge`)
  - [x] 9.1 Create `knowledge/preflight-checks.json`
    - One entry per named check (M1, M2, B1, B2, B3, B4, S1, I1, O1, U1) with: id, title, `applies_to` outcome set, severity rule (including conditional severity, e.g. M1's HIGH-vs-LOW branch), `adapter_generation` tag where applicable, detection method, remediation list
    - _Requirements: 6.1_

  - [x] 9.2 Create `knowledge/coupling-weights.json`
    - One entry per Coupling_Score item (ISR, edge middleware, edge runtime routes, image optimization, streaming SSR, Server Actions/skew, preview deployments, KV/Postgres/Blob/Edge Config/Cron, Vercel-injected headers) with: detection method, weight rationale
    - _Requirements: 5.1, 5.2_

  - [x] 9.3 Create `knowledge/peripheral-mappings.json`
    - Vercel peripheral -> AWS target table per Requirement 8.6: Blob->S3, Cron->EventBridge Scheduler, KV->ElastiCache (Upstash keep-alt), Postgres->RDS/Aurora (Neon keep-alt), Edge Config->Parameter Store/AppConfig, env vars->Secrets Manager/SSM
    - _Requirements: 8.6_

- [x] 10. Implement the Recommendation Engine
  - [x] 10.1 Create `references/shared/vercel-recommendation-engine.md`
    - Full decision-table document per design.md §3: signal sources table, 4 ordered decision steps (first-match-wins, explicitly NOT a collect-all-reasons scorer — call this distinction out in the doc itself so implementers don't flatten it to match the org engine's style), the Step-1-recursion rule for Outcome C's `backend_shape`, output schema (`recommendation.json` shape), constraints, fallback-behavior table
    - Explicitly encode Requirement 7.4 (EKS never recommended unless team runs K8s elsewhere) and 7.5 (Amplify not a default path, cited rationale) as report-prose callouts, NOT as engine outputs — the engine's `outcome` enum never contains `EKS` or `Amplify`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 10.2 Create `phases/recommend/recommend.md` (orchestrator)
    - Frontmatter per design.md §1.4 verbatim (`_knowledge` loads `vercel-recommendation-engine.md`, single fragment)
    - _Requirements: 7.1_

  - [x] 10.3 Create `phases/recommend/recommend-rules.md` (fragment: apply-rules)
    - Thin orchestrator prose: load and follow `vercel-recommendation-engine.md`'s decision steps against `discovery.json`/`coupling-score.json`/`preflight-findings.json`/`clarify-answers.json`; do not duplicate the decision table inline
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 10.4 Create `phases/recommend/recommend-assemble.md` (assembler)
    - Writes `recommendation.json` per the §3.3 output schema; adds the synthetic `fired_rule` finding entry to `assessment-state.json.findings` for the traceability appendix (design.md §2.2)
    - Completion gate `_assert`s per design.md §1.4: outcome enum validity, `separable`/`backend_shape` conditional presence rules, tiebreak-iff-rule-4 invariant
    - _Requirements: 7.1, 7.2, 7.3, 10.2_

- [x] 11. Checkpoint — Recommendation Engine integration
  - Manually verify against the worked-example table (build 4-6 signal-combination fixtures mirroring design.md §3's decision steps): load-bearing-previews + separable -> C; load-bearing-previews + not separable -> stay; websockets present -> B; spiky+high-coupling+small-team -> A; vague traffic answer + no log drain -> tiebreak [A,B]. Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement the `report` phase and its validator
  - [x] 12.1 Create `scripts/validate-assessment-report.py`
    - Fork of `scripts/validate-migration-report.py` (confirmed present on `main`, commit `f6f23f2`): same CLI contract shape, same exit-code semantics (0/1/anything-else)
    - Re-pointed `REQUIRED_SECTION_IDS` per design.md §4.2 (`exec-verdict`, `exec-tiebreak` conditional, `inputs-received` conditional, `what-you-gain`, `what-you-lose`, `coupling-score`, `preflight-findings`, `appendix-m1` conditional, `decision-traceability`, `out-of-scope` conditional, `next-steps`)
    - Reader-vocabulary check re-specified for Vercel's identifier set (check IDs M1/M2/B1-B4/S1/I1/O1/U1, `*.json` filenames, `aws_*.*` Terraform IDs, literal "route disposition") — Requirement 9.7
    - New cost-labeling check: every dollar figure must be adjacent to "estimated monthly" — Requirement 9.6
    - Fixture-bleed check with a new canary ID scoped to the Vercel reference fixture, same mechanism as the ported `_validate_fixture_bleed`
    - _Requirements: 9.6, 9.7, 12.1, 12.2, 12.5, 12.6_

  - [x] 12.2 Create `tests/test_validate_assessment_report.py`
    - Mirror `tests/test_validate_migration_report.py`'s structure and coverage (36 tests written); cover each of the 4.3-listed checks plus the ported 16, exit-code branching for all three cases (0/1/other), fixture-bleed both with and without `--migration-dir`
    - _Requirements: 12.2, 12.5, 12.6_

  - [x] 12.3 Create `fixtures/assessment-report-reference.html` and `fixtures/assessment-report-stub.html`
    - Reference: a golden report built from a reference startup profile that passes every check
    - Stub: deliberately fails multiple checks (missing section, a leaked `M1` in an `exec-*` section, an un-labeled dollar figure) with actionable error text
    - _Requirements: 12.7_

  - [x] 12.4 Create `phases/report/report.md` (orchestrator)
    - Frontmatter per design.md §1.5 verbatim
    - _Requirements: 12.1_

  - [x] 12.5 Create `phases/report/report-render.md` (fragment: render)
    - Renders `assessment-report.html` from all upstream artifacts, applying the outcome-based filter/reframe rule (Requirement 6.3) so a check not applicable to the recommended outcome is not surfaced in the primary findings section, while remaining available for an override (Requirement 6.4)
    - Applies the reader-vocabulary rule at render time (Requirement 9.7) and the cost-labeling rule (Requirement 9.6) as authoring discipline, backed by the validator as the enforcement mechanism
    - _Requirements: 6.3, 6.4, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 10.1, 10.3, 10.4_

  - [x] 12.6 Create `phases/report/report-assemble.md` (assembler)
    - Owns the retry-cap loop (Requirement 12.3-12.4): invoke `validate-assessment-report.py`, branch on exit code per the table in design.md §4.1, rename to `assessment-report.incomplete.html` on fail-with-errors, retry up to 2 additional times, stop and surface on cap exhaustion without presenting a stub as complete
    - Appends the `report_history` entry to `assessment-state.json` with the 5-entry FIFO cap (design.md "Resolved Design Decisions" item 2) and computes `diff_from_previous` (Requirement 11.4)
    - _Requirements: 11.4, 12.2, 12.3, 12.4_

- [x] 13. Checkpoint — Report phase and validator integration
  - Run `tests/test_validate_assessment_report.py`, confirm the stub fixture fails with actionable errors and the reference fixture passes cleanly. Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement the `scaffold` checkpoint phase
  - [x] 14.1 Create `phases/scaffold/scaffold.md` (orchestrator)
    - Frontmatter per design.md §1.6 verbatim (`_kind: checkpoint`, `_trigger` on founder opt-in, no `_advances_to`)
    - _Requirements: 8.1_

  - [x] 14.2 Create `phases/scaffold/scaffold-opennext.md` (fragment: outcome-a)
    - Triggered when `recommendation.outcome == 'A'` or `'C'` with `backend_shape == 'A-shaped'`
    - Emits the Next.js app surface via SST/OpenNext (server functions, CloudFront, ISR tag cache + revalidation queue provisioned TOGETHER, image optimization) per Requirement 8.2; when reached via the C-recursion, emits ONLY the backend serverless compute (API Gateway + Lambda) in Terraform, never a partial OpenNext/SST scaffold (Requirement 7.2)
    - Documents the SST-for-app-surface exception inline as an explicit, outcome-scoped exception to Terraform-first (Requirement 8.2)
    - _Requirements: 7.2, 8.2_

  - [x] 14.3 Create `phases/scaffold/scaffold-fargate.md` (fragment: outcome-b)
    - Triggered when `recommendation.outcome == 'B'` or `'C'` with `backend_shape == 'B-shaped'`
    - Emits Terraform only (ECS service running `next start` container, ALB, CloudFront, ECR, task defs, autoscaling); never emits SST/OpenNext artifacts (Requirement 8.3)
    - _Requirements: 8.3_

  - [x] 14.4 Create `phases/scaffold/scaffold-peripherals.md` (fragment: peripherals)
    - Always runs: applies `knowledge/peripheral-mappings.json` (task 9.3) to whatever peripherals Discover found
    - Wires each applicable Pre-Flight_Check remediation into the scaffold as a thin skeleton, not production-hardened (Requirement 8.5) — e.g. I1's tag cache + queue together, M2's CloudFront header mappings
    - Structures backend-compute/peripheral logic behind an interface so OpenNext v3 can later be swapped for the verified Adapter-API adapter without touching assessment/discovery/recommendation logic (Requirement 8.7)
    - _Requirements: 8.5, 8.6, 8.7_

  - [x] 14.5 Create `phases/scaffold/scaffold-assemble.md` (assembler)
    - Combines fragment outputs; for Outcome C, emits NO Next.js hosting scaffold at all (Requirement 8.4) — only backend compute + peripherals
    - Completion gate: `terraform/README.md` exists (warn-and-skip on failure, since scaffold is optional)
    - _Requirements: 8.4_

  - [x] 14.6 Create `references/shared/graviton.md` and default Scaffold compute to ARM64
    - Ported (scoped down, no Clarify question — this skill's compute is homogeneous Node.js, unlike gcp-to-aws's polyglot Q11b case) from `gcp-to-aws`'s Graviton feature
    - Wired into `scaffold-opennext.md` (`sst.aws.Nextjs`'s `server.architecture`, and the Outcome-C A-shaped backend's `aws_lambda_function.architectures`), `scaffold-fargate.md` (`aws_ecs_task_definition.runtime_platform.cpu_architecture` in both full app-surface and backend-only mode), and `scaffold-peripherals.md` (the Cron peripheral's EventBridge-invoked `aws_lambda_function.architectures`)
    - Confirmed `sharp` (this skill's one detected native dependency, Pre-Flight Check B3) ships prebuilt ARM64 Linux binaries and is not a Graviton blocker
    - _Requirements: 8.5_

- [x] 15. Checkpoint — Scaffold phase integration
  - Manually verify: an Outcome-A recommendation produces both `sst.config.ts` and `terraform/`; an Outcome-B recommendation produces `terraform/` only, zero SST files anywhere; an Outcome-C recommendation with `backend_shape: A-shaped` produces Terraform-only Lambda/API-Gateway resources, never `sst.config.ts`. Ensure all tests pass, ask the user if questions arise.

- [x] 16. Plugin-level integration
  - [x] 16.1 Update `migrate/README.md`
    - Add `vercel-to-aws` to the supported migration sources table and the "What This Does" / "How to Use" sections, mirroring how `heroku-to-aws` is listed today
    - _Requirements: Introduction_

  - [x] 16.2 Update `migrate/plugins/migration-to-aws/README.md` and the plugin manifests
    - Add the skill's trigger phrases to the plugin-level skill index
    - Update `.claude-plugin/marketplace.json`, `.codex-plugin`, `.cursor-plugin` manifests to list `vercel-to-aws` alongside `gcp-to-aws`/`heroku-to-aws` wherever they enumerate skills
    - _Requirements: Introduction_

  - [x] 16.3 Register the new script/tests in CI wiring
    - Add `scripts/validate-assessment-report.py` and `tests/test_validate_assessment_report.py` to whatever CI job runs `tests/test_validate_migration_report.py` (bandit scan scoping, pytest collection, etc.) — mirror the existing exclusion pattern for pytest-assert findings in the tests directory
    - _Requirements: 12.7_

- [x] 17. Final checkpoint — Full integration
  - Ran the plugin's `tools/frontmatter-validator` against the skill (structural DSL check independent of hand-verification) — found and fixed 2 real issues: `_knowledge` misplaced on a fragment instead of its phase (`scaffold-peripherals.md`/`scaffold.md`), and a `_postconditions` `_check_file_exists` gating on `terraform/README.md` without it being declared in `_produces` (`scaffold.md`/`scaffold-assemble.md`). Re-ran after fixes: 0 problems, matching `heroku-to-aws`'s clean result on the same tool. Re-ran the full pytest suite (36/36 passing) and both fixtures through the real validator script (reference -> `REPORT_OK` exit 0; stub -> `REPORT_FAIL` exit 1 with all 9 expected errors) after the fixes to confirm no regression. Re-diffed both vendored files against canonical source (still byte-identical). Ran the frontmatter-validator's own test suite (57/57 passing) as a sanity check on the tool itself.
  - **Live end-to-end dry-run: done.** Ran a full PreScan->Discover->Clarify->Recommend->Report pass against a real, buildable Next.js 15.3.0 fixture repo (actual `next build`, real manifests, real Vercel-API simulation, simulated founder Clarify answers), plus a simulated warm re-entry with a synthetic log-drain input verifying the `computed_from_inputs` selective-recompute mechanism and the `_re_entry_guard` stale-downstream reset both behave as documented. The dry-run surfaced 5 real gaps/bugs in the phase files (route-disposition coverage for API Route Handlers under the manifest-fallback path, single-enum middleware classification unable to represent mixed-behavior middleware, a confidence-rubric gap for deterministic source-code facts, a lowercase/uppercase confidence-vocabulary mismatch between `recommendation.json` and `assessment-state.json`, and the `_re_entry_guard`'s all-or-nothing downstream reset as an inherited architectural note) — all were fixed in the actual skill files except the last, which is shared vendored-DSL behavior, not a vercel-to-aws-specific defect. Two follow-up rounds of external (Cursor) review on the recommendation engine's edge cases and cross-file terminology surfaced further real issues (a `fired_rule`/`tiebreak` field contradiction for Outcome C's backend recursion, a Step 3 "no legal outcome" hole, an undefined traffic-shape boundary, and several stale terminology references) — all fixed and re-verified against `dprint`, `markdownlint-cli2`, the frontmatter validator, and the pytest suite.

## Notes

- Tasks are NOT marked optional in this plan (unlike `org-scp-support/tasks.md`'s `*` convention) — the validator and its fixtures are core to Requirement 12, not a stretch goal, per the spec's own effort estimate framing them as "days, not a week."
- Each task references specific requirements for traceability back to `requirements.md`.
- This is a prompt-based AI agent skill plugin — "implementation" means creating/modifying markdown reference files, JSON knowledge/schema files, and one Python script + its test suite.
- New top-level paths: `skills/vercel-to-aws/` (entire tree per design.md's File Structure section), `scripts/validate-assessment-report.py`, `fixtures/assessment-report-{reference,stub}.html`, `tests/test_validate_assessment_report.py`.
- Modified files: `migrate/README.md`, `migrate/plugins/migration-to-aws/README.md`, plugin manifests (`.claude-plugin/marketplace.json`, `.codex-plugin`, `.cursor-plugin`), `mise.toml` and `.github/workflows/security-scanners.yml` (bandit exclusion for `migrate/plugins/migration-to-aws/tests/`, backfilled to match `origin/main`).
- `gcp-to-aws` and `heroku-to-aws` are NOT modified by this plan.
- Out-of-scope items from `requirements.md` (full cost estimation parity, full Adapter-API infra diff, Cloudflare/VPS paths, production-hardened scaffolds, a promoted canonical `_check_*` DSL kind) are intentionally absent from this task list — do not add tasks for them without a spec update first.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["3.1", "3.2", "3.3", "9.1", "9.2", "9.3"] },
    { "id": 2, "tasks": ["3.4"] },
    { "id": 3, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8"] },
    { "id": 4, "tasks": ["5.9"] },
    { "id": 5, "tasks": ["7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3"] },
    { "id": 7, "tasks": ["10.1"] },
    { "id": 8, "tasks": ["10.2", "10.3"] },
    { "id": 9, "tasks": ["10.4"] },
    { "id": 10, "tasks": ["12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3", "12.4", "12.5"] },
    { "id": 12, "tasks": ["12.6"] },
    { "id": 13, "tasks": ["14.1", "14.2", "14.3", "14.4"] },
    { "id": 14, "tasks": ["14.5"] },
    { "id": 15, "tasks": ["16.1", "16.2", "16.3"] }
  ]
}
```

Checkpoints (2, 4, 6, 8, 11, 13, 15, 17) are sequencing gates, not independently schedulable tasks — each runs after its preceding wave completes and before the next wave begins.
