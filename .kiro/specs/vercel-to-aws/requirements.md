# Requirements Document

## Introduction

This feature adds a `vercel-to-aws` migration skill to the `migration-to-aws` plugin, alongside the existing `gcp-to-aws` and `heroku-to-aws` skills. Unlike those two sources, Vercel's proprietary infrastructure (CloudFront behaviors, Lambda tuning, edge routing) cannot be exported or read directly from an API — it is derived instead from build output, source configs, and the Vercel REST API. The skill's deliverable is an honest assessment (discovery → coupling score → pre-flight checks → three-outcome recommendation) with an optional, thin Terraform/SST scaffold. Full cost-estimation parity with the GCP skill's Estimate phase is explicitly deferred to v2 — billing signal from Vercel is structurally thinner than GCP's line-item billing export.

The skill follows the same DSL contract every skill in this plugin follows: phase files carry YAML frontmatter (`_phase`, `_fragments`, `_assemble`, `_produces`, `_preconditions`/`_postconditions`, `_knowledge`, `_exec`) interpreted per `skills/shared/dsl/INTERPRETER.md`, vendored byte-identical into `references/vendored/dsl/` and CI-checked (`mise run shared:check`). This requirements document describes WHAT the skill must do; the DSL phase/fragment breakdown, the resumability state model, the recommendation-engine pattern, and the report validator adaptation are DESIGN decisions captured in `design.md`.

## Glossary

- **Discover_Phase**: Phase that reads Tier 1/2/3 inputs (repo access, Vercel API token, project scope, log drain, invoices) and produces a signal inventory, prioritized by authority (Adapter API build output > `.next` manifests > source configs > `vercel.json` > Vercel REST API > header probing)
- **PreScan**: A cheap, build-free pass over Tier 1 inputs only (`package.json`, lockfile census, `middleware.ts` existence, `vercel.json` presence, Vercel API project enumeration) that runs before Clarify so Clarify's questions can be fact-driven
- **Clarify_Phase**: Phase that asks Mom-Test-shaped questions PreScan and Full Discover cannot answer (traffic shape, migration trigger, team bandwidth, preview-dependence, Next.js upgrade willingness)
- **Coupling_Score**: Per-feature inventory of Vercel-proprietary dependence (ISR, edge middleware, edge runtime routes, image optimization, streaming SSR, preview deployments, KV/Postgres/Blob/Edge Config/Cron, Vercel-injected headers) rolled into a single score with per-item detail
- **PreFlight_Check**: A named, severity-tiered check (M1, M2, B1-B4, S1, I1, O1, U1) computed unconditionally during Discover/Coupling Score and filtered/reframed at report-render time by the recommended Outcome
- **Recommendation_Engine**: The component that evaluates the §8 precedence rules (preview-dependence -> separability -> Lambda-hostility -> traffic shape -> tiebreak) in a fixed order to select Outcome A, B, C, or "stay on Vercel"
- **Outcome_A**: OpenNext/SST full migration (serverless; SST + Terraform, an explicit documented exception to Terraform-first)
- **Outcome_B**: ECS Fargate full migration, containerized (`next start` behind ALB + CloudFront; Terraform only)
- **Outcome_C**: Hybrid — backend/peripherals migrate to AWS, Next.js hosting and PR previews stay on Vercel (Terraform only; backend compute shape recurses to A-shaped or B-shaped per rules 2-3, never emits SST)
- **Separability_Check**: The Outcome C precondition — a separable AWS-bound surface (API routes, crons, DB/storage peripherals, or a backend service) must exist, or the recommendation falls back to "stay on Vercel"
- **Confidence_Tier**: Per-finding label (LOW/MEDIUM/HIGH) keyed to which inputs were received, per the Startup Input Manifest; every sub-HIGH finding names the specific input that would upgrade it
- **Assessment_State**: The skill-owned resumability ledger (distinct from `.phase-status.json`) that persists inputs received, per-finding confidence + upgrade path, and Clarify answers with `prompt` + `design_consequence`, enabling "come back in a week" resumption without re-running completed work
- **Scaffold_Phase**: Optional checkpoint phase that emits IaC per the recommended Outcome's dialect split (Outcome A: SST + Terraform; Outcome B and C: Terraform only)
- **Assessment_Report**: The final HTML deliverable, gated by a post-write validator adapted from the GCP skill's `validate-migration-report.py` / `validate-migration-report.md` pattern

## Requirements

### Requirement 1: Startup Input Manifest and Tiered Collection

**User Story:** As a founder migrating off Vercel, I want to provide inputs incrementally and see exactly what each additional input unlocks, so that I control the effort-for-confidence tradeoff instead of being asked for everything up front.

#### Acceptance Criteria

1. THE Discover_Phase SHALL require exactly these Tier 1 inputs before any discovery runs: repo access with a locally-runnable `next build`, a read-only team-scoped Vercel API token, and the in-scope Vercel project list
2. IF repo access is present but `next build` does not run clean locally, THEN THE Discover_Phase SHALL record this as a finding (build health) rather than treating it as a missing-input precondition failure
3. THE Discover_Phase SHALL treat each of the following as an optional Tier 2 input that upgrades specific findings when present: a 7-14 day log drain/observability export, the last 3-6 invoices or usage dashboard export, a production URL plus throwaway test account, and a one-sentence answer describing what `middleware.ts` does
4. THE Discover_Phase SHALL treat each of the following as an optional Tier 3 input: infrastructure-pointing env var hostnames (never secret values), the list of Vercel marketplace integrations and third-party webhooks, an analytics export for geo distribution, and any prior migration attempts
5. WHEN a Tier 2 or Tier 3 input is absent, THE Discover_Phase SHALL record in the corresponding finding which missing input would upgrade its Confidence_Tier and the approximate effort required to provide it
6. THE Discover_Phase SHALL NOT request or persist secret values (env var values, API keys beyond the read-only token itself) at any tier; Tier 3 env var collection is scoped to hostnames only
7. THE Discover_Phase SHALL state, when requesting the Vercel API token, that it is read-only, team-scoped, and should be revoked after the assessment completes

### Requirement 2: Pre-Scan Before Clarify

**User Story:** As a founder answering Clarify questions, I want the tool to already know facts it can derive cheaply, so that I am not asked questions the tool could have answered itself.

#### Acceptance Criteria

1. WHEN Tier 1 inputs are available, THE Discover_Phase SHALL run a PreScan pass before Clarify that reads `package.json` (Next.js version, `packageManager`, `sharp` dependency), performs a lockfile census, checks for `middleware.ts` existence, checks for `vercel.json` presence, and enumerates Vercel projects via the API
2. THE PreScan SHALL NOT run `next build` or any build-requiring step; build-dependent discovery is scoped to Full Discover
3. THE Clarify_Phase SHALL consult PreScan output to determine which questions are askable: THE Clarify_Phase SHALL NOT ask "what does your middleware do" when PreScan found no `middleware.ts`, and SHALL NOT ask project-scoping questions when PreScan found only one in-scope project
4. THE Clarify_Phase SHALL phrase the Next.js-version-dependent question using the PreScan-detected version rather than asking the founder to self-report it

### Requirement 3: Clarify Phase Questions and Version Rule

**User Story:** As a founder being asked migration questions, I want the tool to ask only what it genuinely cannot determine on its own, and I want upgrading my Next.js version framed as a choice, not a requirement.

#### Acceptance Criteria

1. THE Clarify_Phase SHALL ask, at minimum, the following questions when PreScan/Full Discover cannot answer them: traffic shape (spiky vs. sustained, rough peak:median ratio), what triggered the migration decision, team DevOps bandwidth for production ownership, how load-bearing PR preview deployments are for the team's workflow, and willingness to upgrade Next.js given the PreScan-detected current version
2. THE Clarify_Phase SHALL record each answer with a `prompt` field (the question asked) and a `design_consequence` field (what downstream decision the answer feeds), per the traceability requirement in Requirement 10
3. THE Clarify_Phase SHALL NOT treat the Next.js-upgrade question as a gate on which migration path is offered; the default recommended path for a cost-driven founder is migrate now on OpenNext v3 regardless of current Next.js version
4. WHEN the detected Next.js version is below 16.2, THE Clarify_Phase SHALL present upgrading as a "confidence upgrade offer" (unlocks the typed Adapter API build output and positions for the future verified AWS adapter) rather than as a migration prerequisite
5. THE Clarify_Phase SHALL NOT block progression to Full Discover, Coupling Score, Pre-Flight Checks, or Recommendation on the Next.js-upgrade answer

### Requirement 4: Discovery Signal Priority and Confidence Scoring

**User Story:** As a founder reading the assessment, I want to know how much to trust each finding, so that I can decide whether to invest more effort before acting on a recommendation.

#### Acceptance Criteria

1. THE Discover_Phase SHALL prioritize discovery signals in this order when multiple are available for the same finding: Adapter API typed build output (Next.js >= 16.2) as highest authority, then `.next` build manifests (fallback for Next.js < 16.2), then source configs (`next.config.js`, `middleware.ts` + matcher), then `vercel.json`, then the Vercel REST API, then header probing as confirmation-only and never as a primary signal
2. WHEN Next.js >= 16.2 and a clean `next build` is available, THE Discover_Phase SHALL run the Adapter API build and produce a route-disposition comparison (static/ISR/dynamic/edge classification per route) as an informational finding
3. THE Discover_Phase SHALL NOT attempt a full "what Vercel provisions vs. what OpenNext provisions" infrastructure diff in v1; this is out of scope until the verified AWS adapter reaches general availability
4. THE Discover_Phase SHALL assign every finding a Confidence_Tier of LOW, MEDIUM, or HIGH, keyed to which inputs the finding rests on: a finding resting solely on header probes or coarse usage aggregates SHALL be marked LOW; a finding backed by log-drain data or invoice data SHALL be eligible for HIGH
5. WHEN a finding is below HIGH confidence, THE Discover_Phase SHALL name the specific missing input that would upgrade it
6. WHEN header probing is used for confirmation, THE Discover_Phase SHALL record known probe limitations (auth walls, bot protection, geo variance, preview-vs-prod divergence) alongside the finding

### Requirement 5: Coupling Score

**User Story:** As a founder deciding whether to migrate, I want a single score summarizing how deeply my app depends on Vercel-proprietary features, with enough per-feature detail to understand what drives the score.

#### Acceptance Criteria

1. THE Discover_Phase SHALL compute a Coupling_Score inventorying, at minimum: ISR/on-demand revalidation, edge middleware, edge runtime routes, image optimization, streaming SSR, Server Actions/version-skew exposure, preview deployments, Vercel KV/Postgres/Blob/Edge Config/Cron usage, and Vercel-injected headers (`x-vercel-ip-*` etc.)
2. THE Discover_Phase SHALL record, for each Coupling_Score item, the detection method used and a weight rationale
3. WHEN the Coupling_Score inventory identifies a single high-coupling component alongside otherwise-migratable code, THE Recommendation_Engine SHALL be able to express this as a phased migration proceeding while that component is evaluated on a specialist path in parallel, rather than defaulting to a blanket stay-on-Vercel recommendation

### Requirement 6: Pre-Flight Checks

**User Story:** As a founder planning a migration, I want to know which Vercel-specific behaviors will change and how severe each change is, filtered to the outcome that was actually recommended for me.

#### Acceptance Criteria

1. THE Discover_Phase SHALL compute all of the following named Pre-Flight_Checks unconditionally, before the Recommendation_Engine runs, each tagged with an `applies_to` outcome set and (where applicable) an `adapter_generation` tag:
   - M1 (cached-route x middleware intersection), applies to A, B, C, severity HIGH when middleware does auth gating/A-B bucketing/geo-redirects/per-request rewrites on cacheable routes, LOW for header decoration/logging
   - M2 (geo/IP header dependence), applies to A, B, C, severity MEDIUM
   - B1 (monorepo lockfile conflicts), applies to A only, severity HIGH
   - B2 (Yarn packageManager pin), applies to A only, severity MEDIUM
   - B3 (sharp as a direct dependency), applies to A only, severity LOW-MEDIUM, no finding on B
   - B4 (bundle contamination), applies to A only, severity LOW
   - S1 (streaming routes with potentially-empty bodies), applies to A only, suppressed on B, severity MEDIUM
   - I1 (ISR/on-demand revalidation completeness), applies to A and B (reframed differently per outcome), severity HIGH under the conditions specified in the design
   - O1 (build environment consistency), applies to A only, advisory severity, generic hygiene note on B
   - U1 (uncached high-invocation routes / cost driver flag), applies to A, B, C, informational severity
2. THE Discover_Phase SHALL NOT gate execution of any Pre-Flight_Check on the Recommendation_Engine's output, since the recommendation does not exist yet at Pre-Flight Check computation time
3. THE Assessment_Report SHALL filter and/or reframe each Pre-Flight_Check's presented wording according to the recommended Outcome (or the outcome the founder overrides to); a check not applicable to the recommended outcome SHALL NOT be surfaced in the primary findings section
4. WHEN the founder overrides the recommended outcome, THE Assessment_Report SHALL be able to surface the previously-computed-but-suppressed findings relevant to the overridden outcome without re-running discovery
5. THE Assessment_Report SHALL note, for M1 specifically, that it is generation-independent (reflects CDN-in-front-of-origin architecture, not build-output reverse-engineering) and applies regardless of which AWS outcome is chosen

### Requirement 7: Three-Outcome Recommendation Engine

**User Story:** As a founder deciding how to migrate, I want a recommendation that follows a fixed, explainable decision order rather than an opaque model judgment, so that I can see exactly why I got the answer I got.

#### Acceptance Criteria

1. THE Recommendation_Engine SHALL evaluate precedence rules in exactly this order and SHALL stop at the first rule that fires:
   1. IF preview deployments are load-bearing per the Clarify answer, THEN check separability (a separable AWS-bound surface: API routes, crons, DB/storage peripherals, or a backend service worth moving); IF separable THEN recommend Outcome_C with the backend compute shape recursing to rules 2-3; IF NOT separable THEN recommend staying on Vercel (or a thin carve-out of whatever peripheral does exist)
   2. IF a Lambda-hostile workload is present (websockets, long-running jobs, sustained heavy SSR, tasks exceeding 15 minutes, or an existing separate API service), THEN recommend Outcome_B
   3. OTHERWISE, decide between Outcome_A and Outcome_B using traffic shape and coupling: spiky traffic + high ISR/edge coupling + small team favors Outcome_A; sustained traffic (peak:median under ~3:1) or a stated preference for debuggability favors Outcome_B
   4. IF traffic-shape confidence is LOW (no log drain, vague Clarify answer), THEN present Outcome_A and Outcome_B side by side naming the specific input (14 days of log drain data) that would resolve the tie, rather than forcing a single pick
2. WHEN rule 1 recommends Outcome_C and the backend compute shape recurses to an "A-shaped" result, THE Recommendation_Engine SHALL emit that as serverless backend compute (API Gateway + Lambda) in Terraform, and SHALL NOT emit a partial OpenNext/SST scaffold for the Next.js app, since the Next.js app remains on Vercel under Outcome_C
3. WHEN a conflicted profile arises (e.g., heavy ISR + sustained traffic + load-bearing previews), THE Recommendation_Engine SHALL resolve it deterministically via the rule order (rule 1 fires first) and THE Assessment_Report SHALL state explicitly that this is a conflicted profile resolved by precedence, not a judgment call
4. THE Recommendation_Engine SHALL classify EKS as never recommended unless the team already operates Kubernetes elsewhere, and SHALL note the existence of funded Vercel-to-EKS marketplace offerings as the anti-pattern the assessment differentiates against, while separately noting that AWS migration funding programs are a legitimate line item regardless of target
5. THE Recommendation_Engine SHALL classify AWS Amplify as not a default path, and the report SHALL cite the rationale (shared CDN owned by the Amplify team, resources outside the founder's account, closed-source) as sourced from the OpenNext team's assessment and flagged for periodic re-check
6. THE Recommendation_Engine SHALL include, for every report it produces, an out-of-scope honesty paragraph: a pre-revenue founder with a single low-traffic app and no AWS credits is told a VPS or Cloudflare is a rational choice and this tooling is not targeted at them; Cloudflare migration paths themselves SHALL NOT be built

### Requirement 8: Optional Scaffold Layer

**User Story:** As a founder who has decided to migrate, I want runnable IaC scaffolding that matches my recommended outcome, without receiving a dialect mismatch (SST where Terraform was expected, or vice versa).

#### Acceptance Criteria

1. THE Scaffold_Phase SHALL be an optional checkpoint phase entered only when the founder opts in after receiving the Assessment_Report
2. WHEN the recommended/chosen outcome is Outcome_A, THE Scaffold_Phase SHALL emit the Next.js app surface via SST/OpenNext (server functions, CloudFront, ISR tag cache and revalidation queue provisioned together, image optimization) and SHALL emit all peripherals via Terraform; this SST-for-app-surface exception SHALL be documented inline as an explicit, outcome-scoped exception to the plugin's Terraform-first convention
3. WHEN the recommended/chosen outcome is Outcome_B, THE Scaffold_Phase SHALL emit Terraform only (ECS service running the `next start` container, ALB, CloudFront, ECR, task definitions, autoscaling) and SHALL NOT emit any SST or OpenNext artifacts
4. WHEN the recommended/chosen outcome is Outcome_C, THE Scaffold_Phase SHALL emit no Next.js hosting scaffold (Next.js hosting remains on Vercel) and SHALL emit Terraform only for backend compute (per the Requirement 7 recursion) and peripherals (RDS/S3/EventBridge/etc.)
5. THE Scaffold_Phase SHALL wire each applicable Pre-Flight_Check remediation into the emitted scaffold (e.g., I1's tag cache and revalidation queue provisioned together, M2's CloudFront header mappings) as thin working skeletons, not production-hardened stacks
6. THE Scaffold_Phase SHALL map Vercel peripherals to AWS targets at minimum as follows: Blob -> S3, Cron -> EventBridge Scheduler, KV -> ElastiCache (noting Upstash as a keep-alternative), Postgres -> RDS/Aurora (noting Neon as a keep-alternative), Edge Config -> Parameter Store/AppConfig, env vars -> Secrets Manager/SSM
7. THE Scaffold_Phase SHALL generate its backend-compute and peripheral logic behind an interface such that OpenNext v3 output can be replaced by a future verified Adapter-API-based AWS adapter without changing assessment/discovery/recommendation logic

### Requirement 9: Report Structure and Reader-Vocabulary Rules

**User Story:** As a founder reading the assessment report, I want the executive summary in plain language I can act on, with internal implementation detail (check IDs, filenames, Terraform resource names) confined to appendices.

#### Acceptance Criteria

1. THE Assessment_Report SHALL include, at minimum, these sections: executive summary with recommendation (A/B/C/stay) and confidence level; inputs received by tier with confidence-upgrade offers; what the founder gains; what the founder loses (preview deployments first); Coupling_Score with per-feature detail; Pre-Flight_Check findings filtered/reframed by outcome; a decision traceability appendix; an out-of-scope honesty paragraph where applicable; and an ordered Next Steps list
2. THE Assessment_Report SHALL render a verdict banner whenever a recommendation exists, and SHALL render an "Outcome A and B side by side" section whenever the Requirement 7 rule-4 tiebreak fired
3. THE Assessment_Report SHALL render the confidence-upgrade-offers section whenever any finding is below HIGH confidence
4. THE Assessment_Report SHALL render an M1 section whenever `middleware.ts` was detected during PreScan
5. THE Assessment_Report SHALL render the separability rationale whenever Outcome_C or stay-on-Vercel was the recommendation
6. THE Assessment_Report SHALL phrase every dollar figure anywhere in the report as an "estimated monthly cost/savings" figure, including figures produced by the U1 Pre-Flight_Check, even though full cost estimation is deferred to v2
7. THE Assessment_Report SHALL NOT contain, within executive-flow sections (verdict, decision summary, gain/lose sections), any Pre-Flight_Check ID (e.g. "M1"), artifact filename, Terraform resource identifier, or the term "route disposition"; such identifiers SHALL appear only in technical appendices
8. THE Assessment_Report SHALL present the Next.js-upgrade offer in the Next Steps section as a confidence-upgrade offer, never as a migration prerequisite

### Requirement 10: Decision Traceability

**User Story:** As a founder or a reviewer of the assessment, I want to see exactly which precedence rule fired and which input drove which decision, so that the recommendation is auditable rather than opaque.

#### Acceptance Criteria

1. THE Assessment_Report SHALL always render a decision traceability appendix, regardless of which outcome was recommended
2. THE Assessment_Report SHALL derive the traceability appendix from the Assessment_State record of Clarify answers, each carrying its `prompt` and `design_consequence` fields
3. THE Assessment_Report SHALL state which Requirement 7 precedence rule fired and why, mapping at least the preview-dependence answer and the traffic-shape answer (or its absence) to their design consequences
4. WHEN the Requirement 7 rule-4 tiebreak fired, THE Assessment_Report SHALL state which rule would have applied had the missing input (log drain data) been available

### Requirement 11: Resumable, Idempotent Assessment State

**User Story:** As a founder who does not have log drain data yet, I want to turn on logging, come back in a week, and have the tool pick up where it left off instead of restarting the whole assessment.

#### Acceptance Criteria

1. THE Discover_Phase SHALL persist an Assessment_State record to the repository, separate from `.phase-status.json`, tracking at minimum: inputs received (by tier), findings with their Confidence_Tier and upgrade-input pointer, Clarify answers with `prompt` and `design_consequence`, and timestamps
2. WHEN the skill is re-invoked and Assessment_State already exists, THE Discover_Phase SHALL load previously-collected inputs and answers rather than re-collecting them
3. WHEN a new input is supplied on a re-invocation (e.g., a log drain export that did not exist previously), THE Discover_Phase SHALL recompute only the findings that input affects, and SHALL leave unaffected findings and their Confidence_Tier unchanged
4. WHEN findings are recomputed on a re-invocation, THE Assessment_Report SHALL be able to render a diff against the immediately prior report, showing which findings changed Confidence_Tier or value
5. THE Assessment_State SHALL be readable and writable independently of `.phase-status.json`, and a corrupt or missing Assessment_State SHALL NOT be treated as a corrupt or missing `.phase-status.json` (the two files fail independently)

### Requirement 12: Report Validation Gate

**User Story:** As a founder receiving the assessment report, I want assurance the report is structurally complete and does not contain another company's numbers, before I read it as my own.

#### Acceptance Criteria

1. THE Discover_Phase's downstream Report phase SHALL run a post-write validator script immediately after writing the Assessment_Report, adapted from the existing `migrate/plugins/migration-to-aws/scripts/validate-migration-report.py` pattern
2. THE Report phase SHALL branch on the validator's shell exit code, not on pattern-matching stdout text alone: exit code 0 SHALL be treated as pass, exit code 1 SHALL be treated as fail-with-errors, and any other exit code SHALL be treated as "the validator did not run" and reported to the user as such — never silently treated as a pass
3. WHEN the validator reports fail-with-errors, THE Report phase SHALL rename the incomplete report to `assessment-report.incomplete.html` (never delete unless the user asks), emit all failure lines to the user, and retry report generation up to a maximum of 2 additional attempts
4. WHEN the retry cap is reached without a passing validation, THE Report phase SHALL surface the incomplete report and its failures to the user and SHALL stop; it SHALL NOT present a stub report as complete, and the underlying assessment SHALL still be considered complete (the report is the deliverable's rendering, not the assessment itself)
5. THE validator SHALL check, at minimum: each required section ID appears exactly once, table-of-contents anchors match section IDs, appendix content is rendered findings rather than JSON stubs or bare links to JSON, the Requirement 9 conditional gates, the Requirement 9 reader-vocabulary rule, and the Requirement 9 cost-labeling rule
6. THE validator SHALL check for fixture bleed: on a real run, distinctive strings from the reference fixture (its startup name, route paths, dollar figures) SHALL NOT appear in the generated report
7. THE plugin SHALL maintain a golden reference report fixture that passes validation and an inverse stub fixture that deliberately fails with actionable errors, both wired into CI regression, mirroring the existing GCP skill's fixture pattern

## Out of Scope (v1)

- Full cost estimation / line-item savings parity with the GCP skill's Estimate phase (Vercel billing data is structurally too thin for this; U1's cost-driver flag is the one exception, and even it is labeled as an estimate)
- Full "what Vercel provisions vs. what OpenNext provisions" infrastructure diff (deferred until the verified Adapter-API-based AWS adapter reaches general availability)
- Cloudflare or VPS migration paths (acknowledged in the out-of-scope honesty paragraph, never built)
- Production-hardened scaffolds (v1 scaffolds are deliberately thin skeletons)
- A promoted canonical `_check_*` DSL primitive for script-exit-code branching (the validator runs via phase prose calling the script directly, matching the current GCP skill pattern; promoting this to a closed-vocabulary check kind is a possible v2 cleanup, not a v1 requirement)
