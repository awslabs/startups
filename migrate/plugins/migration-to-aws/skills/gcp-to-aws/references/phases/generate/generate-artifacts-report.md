# Generate Phase: HTML Migration Report

> Loaded by generate.md AFTER generate-artifacts-docs.md completes.

**Execute ALL steps in order. Do not skip or optimize.**

## Overview

Generate a single self-contained HTML report (`migration-report.html`) combining an executive summary with detailed appendix. The HTML file uses inline CSS — no external dependencies required. Users can open it in any browser and use "Print to PDF" if a PDF is needed.

**Output:**

- `migration-report.html` — Self-contained HTML report with executive summary and detailed appendix

**Non-blocking:** If report generation fails after `VALIDATE_OK` (HTML build error only), log a warning and continue. Validation `GATE_FAIL` is **not** a silent skip — always surface to the user. Do NOT fail the Generate phase for report issues.

## Step 0: Validate Artifacts (Read Only)

Load and execute `shared/validate-artifacts.md` **before** building report content.

- Run all **required** checks (field presence only — do not rewrite artifact prose).
- On any `GATE_FAIL`: output failure lines to the user, **do NOT write** `migration-report.html`, **do NOT patch artifacts**, return to parent `generate.md`.
- On `VALIDATE_OK`: proceed to Step 1.

## Prerequisites

At least one of these must exist in `$MIGRATION_DIR/`:

- Design artifact: `aws-design.json`, `aws-design-ai.json`, or `aws-design-billing.json`
- Estimation artifact: `estimation-infra.json`, `estimation-ai.json`, or `estimation-billing.json`
- Generation plan: `generation-infra.json`, `generation-ai.json`, or `generation-billing.json`

If **none** exist: skip report generation. Output: "Skipping HTML report — no migration artifacts found."

## Data Sources

Gather data from all available artifacts. Each section below notes which artifact provides the data.

| Data Point                                     | Primary Source                                                                                                                                                                                            | Fallback                                             |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| GCP services detected                          | `aws-design.json` clusters[].resources[]                                                                                                                                                                  | `aws-design-billing.json` services[]                 |
| AWS service mappings                           | `aws-design.json` resources[].aws_service                                                                                                                                                                 | `aws-design-billing.json` services[].aws_service     |
| Rationale per service                          | `aws-design.json` resources[].rationale                                                                                                                                                                   | `aws-design-billing.json` services[].rationale       |
| Current GCP monthly cost                       | `estimation-infra.json` current_costs.gcp_monthly                                                                                                                                                         | `estimation-billing.json`                            |
| Projected AWS monthly cost                     | `estimation-infra.json` projected_costs.aws_monthly_balanced                                                                                                                                              | `estimation-billing.json`                            |
| Cost breakdown per service                     | `estimation-infra.json` projected_costs.breakdown                                                                                                                                                         | `estimation-billing.json`                            |
| Cost tiers (premium/balanced/optimized)        | `estimation-infra.json` cost_comparison                                                                                                                                                                   | —                                                    |
| Optimization opportunities                     | `estimation-infra.json` optimization_opportunities                                                                                                                                                        | —                                                    |
| Migration timeline                             | `generation-infra.json` migration_plan.total_weeks                                                                                                                                                        | `generation-billing.json`                            |
| Top risks                                      | `generation-infra.json` risk_assessment                                                                                                                                                                   | `generation-billing.json`                            |
| Human expertise flags                          | Design artifact resources[].human_expertise_required                                                                                                                                                      | —                                                    |
| AI model mappings                              | `aws-design-ai.json`                                                                                                                                                                                      | —                                                    |
| AI cost estimates                              | `estimation-ai.json`                                                                                                                                                                                      | —                                                    |
| Migration decision / recommendation            | `estimation-infra.json` → `recommendation`                                                                                                                                                                | `financial_summary.recommendation` (string fallback) |
| Complexity and timeline hint                   | `migration-preview.json` → `complexity_signal`, `timeline_hint`                                                                                                                                           | —                                                    |
| Key decisions ahead                            | `migration-preview.json` → `key_decisions_ahead`                                                                                                                                                          | —                                                    |
| User configuration choices                     | `preferences.json` (read `.value` from wrapped fields)                                                                                                                                                    | —                                                    |
| AI capabilities and integration                | `ai-workload-profile.json` → `models[]`, `integration`, `agentic_profile`                                                                                                                                 | —                                                    |
| Deferred services                              | Design artifact `resources[].aws_service == "Deferred — specialist engagement"`                                                                                                                           | —                                                    |
| Observability cost callout                     | `estimation-infra.json` → `projected_costs.breakdown` (array: `service` contains "Observability"; object: key contains `observability` or `cloudwatch`)                                                   | —                                                    |
| **Combined AWS monthly run rate (infra + AI)** | Sum `estimation-infra.json` Balanced + `estimation-ai.json` → `cost_comparison.projected_bedrock_monthly` (or `recommended_model.monthly_cost`)                                                           | —                                                    |
| **Security baseline component costs**          | `estimation-infra.json` → `projected_costs.breakdown.security_baseline.components` (GuardDuty, cloudtrail_s3, etc.)                                                                                       | Static ranges in Appendix G when JSON absent         |
| **Implementation effort**                      | Sum distinct low/high ranges from `generation-infra.json` + `generation-ai.json`; legacy fallback: approximate `recommendation.estimated_total_effort_hours` values without double-counting parallel work | —                                                    |
| **Terraform validation status**                | `validation-report.json` → `status`, `provider_version`                                                                                                                                                   | —                                                    |
| **Pricing confidence / staleness**             | `estimation-infra.json` → `pricing_source`, `accuracy_confidence`                                                                                                                                         | `estimation-ai.json` accuracy fields                 |
| **AI optimization opportunities**              | `estimation-ai.json` → `optimization_opportunities`, `optimized_projection`                                                                                                                               | —                                                    |
| **What-if workshop scenarios**                 | `scenarios/index.json` + each `scenarios/scenario-NNN.json` manifest (`estimation_summary`, `preferences_subset`, optional `graviton_note`)                                                               | — (omit section when workshop unused)                |

## Step 1: Build Executive Summary Section

**Load `references/shared/report-decision-core.md` and render it in `full` mode.** That file is the single source of truth for every executive-summary section (Decision Summary through "What this assessment rests on") — verdict typography, baseline-quality/not-comparable rules, Activate wording, and readability conventions all live there. Do not restate or paraphrase its rules here.

Full-mode notes:

- `generation-infra.json` and `terraform/` exist on this path — use them where the core's sections prefer them (Timeline from `migration_plan.total_weeks`, cluster order in the architecture diagram).
- **Replace, never patch:** if `decision-report.html` exists from a prior Decide run, leave it untouched and render `migration-report.html` fresh from the artifacts. Do not splice or extend the decision report's HTML. Note in the Generated Artifacts Catalog that the full report supersedes the decision report.

## Step 2: Build Detailed Appendix

The appendix follows the executive summary, clearly separated with an "Appendix: Detailed Migration Analysis" header.

### Appendix Section A — Service Recommendations

For each mapped service, include:

- GCP service name and type
- AWS service recommendation
- **How the mapping was chosen** — use **Standard pairing**, **Tailored to your setup**, or **Estimated from billing only** (`design-refs/fast-path.md` → User-facing vocabulary); JSON `confidence` may appear in parentheses for support
- Full rationale text from design artifact
- If the mapping was **Tailored to your setup** (`inferred`) and `rubric_applied` is present: list the 6 criteria evaluations (appendix detail — optional in executive summary)
- If `human_expertise_required: true`: include the specialist guidance callout

Source: design artifact (aws-design.json or aws-design-billing.json)

### Appendix Section B — Cost Estimates

**Per-service cost breakdown table** with columns: Service Category, AWS Service, Monthly Cost (Balanced), Calculation/Notes.

**Mandatory rows when present in `projected_costs.breakdown`:**

- compute, database, storage, networking
- **security_baseline** — include `mid` cost AND component sub-rows from `components` (e.g. GuardDuty, cloudtrail_s3, budgets)
- **observability** — include `mid` and `note` (GCP free-tier comparison)
- supporting (Secrets Manager, ECR, etc.)

Do NOT collapse security_baseline into "other". Surface GuardDuty explicitly.

**GCP baseline breakdown** (when `current_costs.breakdown` exists): table of compute/database/storage/networking/other vs infra total.

Source: estimation artifact projected_costs.breakdown, current_costs.breakdown

**Three-tier comparison table** with columns: **Tier** (name + subtitle as in Section 3), Monthly Cost, vs GCP Monthly, Annual Difference.

Repeat the **How to read cost tiers** callout from Section 3 here or include a one-line pointer: _See executive summary — three tiers are scenario $ only; generated Terraform matches **Balanced** baseline._

Source: estimation artifact cost_comparison

**Optimization opportunities table** with columns: Optimization, Target Services, Monthly Savings, Commitment, Effort.

Merge infra (`estimation-infra.json`) and AI (`estimation-ai.json`) optimization rows when both exist.

Source: estimation artifact optimization_opportunities

> **Security baseline costs** are included as a line item in the breakdown above. For Terraform resource names and GCP equivalents, see Appendix G.

### Appendix Section C — Migration Steps

Numbered migration phases from the generation plan, each with:

- Phase name and description
- Services included
- Estimated duration
- Dependencies and prerequisites

Source: generation plan

**Rollback procedure** — triggers, steps, and RTO from generation plan.

### Appendix Section D — AI Migration (conditional)

**Only include if `aws-design-ai.json` or `estimation-ai.json` exists.**

**D.1 — AI Stack Detected:**

Pull from `ai-workload-profile.json` when present:

| Aspect              | Detected                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| AI source           | `summary.ai_source`                                                                                        |
| Models              | `models[].model_id` — comma-separated list                                                                 |
| Capabilities in use | `integration.capabilities_summary` — keys where value is `true`                                            |
| Integration pattern | `integration.pattern`                                                                                      |
| Gateway/router      | `integration.gateway_type` or "None (direct SDK)"                                                          |
| Frameworks          | `integration.frameworks` or "None"                                                                         |
| Agentic             | If `agentic_profile` exists: "Yes — [framework], [orchestration_pattern], [agent_count] agents"; else "No" |

**D.2 — Why Bedrock (conditional):**

Show this section when `aws-design-ai.json` → `ai_architecture.honest_assessment` contains ANY of: `"recommend_stay"`, `"weak_migrate"`, or `"moderate_migrate"` where any model's Bedrock price exceeds the source provider price.

> **Why migrate to Bedrock when [source] may be cheaper per token?**
>
> - **Single-vendor billing:** One AWS bill instead of separate provider invoices
> - **VPC-private inference:** Model calls stay in your VPC — no data over public internet
> - **IAM access control:** No API keys to rotate; permissions follow your AWS IAM model
> - **Model evaluation:** A/B test models with Bedrock's built-in evaluation framework
> - **Guardrails:** Content filtering and PII detection at the platform level
> - **Commitment pricing:** Provisioned Throughput for predictable costs at scale
>
> These benefits matter most when: you handle sensitive data, need AI call audit trails, or want to consolidate vendors.

**D.3 — Model Mappings:**

- Model mappings (GCP model to AWS Bedrock model)
- AI cost estimates

**D.4 — Migration approach:**

- Migration approach (adapter pattern, A/B testing)

**D.5 — Post-migration AI cost optimization (conditional):**

**Only include if `generation-ai.json` exists in `$MIGRATION_DIR/` (AI track ran).**

After migration is validated and stable, three optimization levers are available (typical ranges from plugin guidance — validate against your traffic):

| Optimization               | Estimated savings        | When to apply                                    | Prerequisite                                                             |
| -------------------------- | ------------------------ | ------------------------------------------------ | ------------------------------------------------------------------------ |
| Intelligent Prompt Routing | 10–30%                   | After 2+ weeks of production traffic             | Same model family in multiple tiers (e.g., Claude Sonnet + Haiku)        |
| Prompt caching             | 20–50% on eligible calls | When prompts have long repeated context          | Minimum ~1K–4K tokens cacheable prefix; per-model minimums and TTL apply |
| Model distillation         | Up to ~75%               | After 30+ days of stable, high-volume production | Stable prompts, evaluation dataset, sufficient call volume               |

These are not migration steps — they are post-migration optimizations. Do not block migration on these. Surface as a "Month 2–3" roadmap item.

**Prompt caching caveat:** Caching only helps for long, repeated context windows. Evaluate actual prompt patterns before assuming savings.

**Full detail:** Open `ai-workload-profile.json` in this directory.

Source: `ai-workload-profile.json`, `aws-design-ai.json`, `estimation-ai.json`

### Appendix Section E — Generated Artifacts Catalog

List all files and directories generated during the Generate phase:

- `terraform/` — list .tf files and **`README.md`**
- `scripts/` — list migration scripts
- `ai-migration/` — list adapter files (if applicable)
- `MIGRATION_GUIDE.md`, `README.md`

Check for actual file/directory existence before listing.

**Data artifacts (for detailed review):**

| Artifact                      | Contents                                                   |
| ----------------------------- | ---------------------------------------------------------- |
| `preferences.json`            | All migration configuration choices and their sources      |
| `ai-workload-profile.json`    | Full AI model inventory, capabilities, evidence            |
| `gcp-resource-inventory.json` | Complete GCP resource inventory with classifications       |
| `estimation-infra.json`       | Detailed cost model, recommendation, per-service breakdown |
| `aws-design.json`             | Full architecture design with rationale per service        |

Open any JSON file with a text editor or `cat <filename> | python3 -m json.tool` for formatted output.

**AI migration artifacts (conditional — only list if they exist on disk):**

| Artifact                                                    | Description                                                                       |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `ai-migration/bedrock_monitoring.tf`                        | Bedrock budget alerts, anomaly detection, inference profiles for cost attribution |
| `ai-migration/STARTUP_PROGRAMS.md` or `STARTUP_PROGRAMS.md` | AWS Activate credit tiers, application URLs, eligibility guidance                 |
| `ai-migration/setup_bedrock.sh`                             | Bedrock model access setup script                                                 |
| `ai-migration/test_comparison.py`                           | A/B comparison harness for source vs Bedrock quality                              |

Do not list files that were not generated.

### Appendix Section F — Your Configuration (`appendix-config`, conditional)

**Only include if `preferences.json` exists in `$MIGRATION_DIR/`.**

Key decisions that shaped this migration plan. Read every object in `design_constraints`, `ai_constraints`, and `startup_constraints` (when present). Schema: `references/shared/schema-preferences.md`.

Render an HTML table with **five columns**, one row per constraint object (iterate every key in `design_constraints`, `ai_constraints`, and `startup_constraints` when present — do not hardcode a subset):

| Column                    | Source                                                                                                                                          |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Question / assumption** | `prompt` on each constraint object                                                                                                              |
| **Your choice**           | formatted `value` (human-readable; expand arrays)                                                                                               |
| **Source**                | `chosen_by` → "User answer", "Extracted from infrastructure", "Default applied", or "Derived"                                                   |
| **Source signal**         | the `source` field when present (shows provenance like `terraform:availability_type=ZONAL` or `default:Q16`); leave blank for user/derived rows |
| **Design consequence**    | `design_consequence` on each constraint object                                                                                                  |

**Assumption flag:** Rows where `source` starts with `"default:"` are unverified assumptions — render in a visually distinct style (e.g., lighter text or italic) so the reader can spot which values were not explicitly verified from infrastructure.

**Critical-default caveats (required when present):** If any of the following constraints have `chosen_by: "default"` AND the corresponding question ID appears in `metadata.questions_defaulted`:

- `compliance` (Q2): render a warning callout: _"⚠️ Compliance was not explicitly confirmed. The security baseline assumes no regulatory requirements. If SOC 2, PCI, HIPAA, or FedRAMP applies, re-run Clarify or manually add controls."_ **Also fire this callout whenever `compliance.value` contains `"unknown"`** (regardless of `chosen_by` — covers both "I don't know" answers and defaulted runs). `"unknown"` never triggers the Section 4 compliance-controls note or any compliance-specific architecture.
- `gcp_monthly_spend` (Q3): render a warning callout: _"⚠️ GCP spend was not confirmed by the user. Cost comparison uses the default band ($1K–$5K). Actual spend may differ — verify against your GCP billing console."_
- `availability` (Q6): render a warning callout: _"⚠️ Database availability was assumed (Multi-AZ) — the user never confirmed it. This assumption roughly doubles the database line vs single-AZ. Confirm the availability requirement (or compare a single-AZ scenario in the what-if workshop) before treating the database estimate as final."_

Place these callouts at the top of Appendix F, before the table, so they're immediately visible.

**Sort order:** user-answered rows first, then extracted, then default, then derived.

**Legacy fallback:** If a constraint object lacks `prompt` or `design_consequence` (pre-extension runs), use the catalog in `schema-preferences.md` keyed by constraint name — never omit the appendix or leave cells empty.

**Do not** reduce this section to a key/value dump without question text and consequences.

Source: `preferences.json`

### Appendix Section G — Security Capabilities

Full security baseline capabilities. Executive summary shows a teaser; this appendix provides the complete picture.

| Control                | What it does for you                                                                | Threat mitigated                      | GCP equivalent                             | Monthly cost |
| ---------------------- | ----------------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------ | ------------ |
| GuardDuty              | Detects compromised credentials, crypto mining, unusual API patterns within minutes | Credential theft, resource hijacking  | Security Command Center (paid Premium)     | ~$2–25/mo    |
| CloudTrail             | Immutable audit log of every API call — who did what, when                          | Unauthorized changes, compliance gaps | Cloud Audit Logs (free for admin activity) | ~$0.50–3/mo  |
| IMDSv2 enforcement     | Blocks SSRF attacks from stealing instance/container credentials                    | Server-side request forgery           | N/A (GCP uses different metadata model)    | $0           |
| Access Analyzer        | Alerts when IAM policies or S3 buckets become publicly accessible                   | Accidental public exposure            | IAM Recommender (partial)                  | $0           |
| EBS default encryption | All storage volumes encrypted at rest by default                                    | Data exposure from stolen disks       | Default encryption (GCP default)           | $0           |
| Budget alerts          | Email when spend exceeds threshold                                                  | Bill shock from runaway resources     | GCP Budgets (free)                         | $0           |
| S3 Block Public Access | Account-wide prevention of any bucket being made public                             | Accidental data leaks                 | Uniform bucket-level access (opt-in)       | $0           |
| IAM password policy    | 14-char min, rotation, complexity for console users                                 | Weak password compromise              | Cloud Identity policies                    | $0           |

**Compliance-conditional (only when SOC 2/PCI/HIPAA/FedRAMP declared in preferences):**

| Control             | What it adds                                           | Compliance gap covered             | Monthly cost |
| ------------------- | ------------------------------------------------------ | ---------------------------------- | ------------ |
| AWS Config          | Continuous recording of resource configuration changes | Change audit trail for SOC 2 / PCI | ~$2–10/mo    |
| Security Hub + FSBP | Automated security checks against AWS best practices   | Baseline posture scoring           | ~$1–15/mo    |

**Cost guardrails (when `$MIGRATION_DIR/ai-migration/bedrock_monitoring.tf` exists):**

| Control                         | What it does for you                                                    | Threat mitigated                                   | GCP equivalent                                 | Monthly cost |
| ------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------- | ---------------------------------------------- | ------------ |
| Bedrock budget (1.5× projected) | Hard spend alert at 150% of estimated AI costs — fires before month-end | Runaway token spend from buggy retry loops         | GCP Budgets (free, but no per-service scoping) | $0           |
| Cost anomaly detection          | Daily digest when AI spend deviates from baseline (~24h data lag)       | Gradual cost creep, unexpected model-price changes | None (no GCP per-service anomaly equivalent)   | $0           |
| Inference profiles (tagged)     | Per-model cost attribution in Cost Explorer                             | Invisible cost distribution across models          | None                                           | $0           |

These are detective controls, not spend caps. You will know within ~24 hours if something goes wrong — not at invoice time.

**What the baseline does NOT cover (you still need):**

- SOC 2: Qualified auditor, formal policies, employee training, vendor management
- HIPAA: BAA with AWS, qualified HIPAA auditor, data handling policies
- PCI: QSA assessment, network segmentation validation, pen testing
- FedRAMP: Agency-level NIST 800-53 controls, ATO process

**For detailed cost breakdown:** See Appendix B (cost estimates include security baseline as a line item).

**To enable:** Run `terraform apply` on `baseline.tf`. To skip: delete `baseline.tf` before applying. See `terraform/README.md` for details.

Source: static content + `preferences.json` compliance values

### Appendix Section H — Security Gap Analysis (`appendix-security-gap`, REQUIRED when infra track ran)

Table: Capability | GCP (detected) | AWS (generated) | Gap / action

Minimum rows:

- Network perimeter (firewall rules → security groups)
- Identity & access (service accounts → IAM roles)
- Audit logging (Cloud Audit Logs → CloudTrail)
- Threat detection (SCC optional → GuardDuty in baseline.tf)
- Public data exposure (if public GCS/S3 detected in design)
- Observability cost shift (GCP larger free tier vs CloudWatch always-free tier; pull gap text from `estimation-infra.json` observability `note` — do **not** say CloudWatch has no free tier)

Source: `aws-design.json`, `terraform/baseline.tf`, `estimation-infra.json` observability note. Gap/action column should compare tier sizes (e.g. 50 GB GCP logging vs 5 GB CloudWatch always-free) and note the estimate assumes usage above free-tier limits — never "no free logging tier on AWS."

### Appendix Section I — Assumptions & Validation (`appendix-assumptions`, REQUIRED)

**Pricing confidence table:** domain, source, accuracy band, last updated (from `pricing_source` / `accuracy_confidence`).

**Exclusions list:**

- Deferred services (`deferred_services[]`, `excluded_from_totals`)
- GCP egress when `migration_cost_considerations.billing_data_available === false`
- Professional services / dual-run period (not modeled)

**Terraform validation:** from `validation-report.json` when present (`status`, provider version).

Source: estimation artifacts, `validation-report.json`, design warnings

## Step 3: Generate HTML

### Pre-Write Sanity Check (mandatory)

Immediately before writing the file, **re-read from disk**:

1. `estimation-infra.json` → `recommendation.path_label` present OR Step 1 fallback documented.
2. `migration-preview.json` → `complexity_signal` present (if file exists).
3. Assembled HTML string contains `<section id="decision-summary">`.

If any check fails: emit `GATE_FAIL | phase=generate | field=<path> | reason=missing`, do **not** write the file, return to parent.

Write the complete HTML to `$MIGRATION_DIR/migration-report.html`.

### HTML Structure (required section IDs)

The output MUST include these `id` attributes (content from Steps 1–2; gates check **presence only**):

| Section ID           | Content                                |
| -------------------- | -------------------------------------- |
| `decision-summary`   | Section 0 — Migration Decision Summary |
| `exec-services`      | Primary services summary               |
| `exec-costs`         | Cost comparison headline / tier table  |
| `exec-timeline`      | Timeline + effort                      |
| `exec-risks`         | Top risks                              |
| `appendix-services`  | Appendix A                             |
| `appendix-costs`     | Appendix B                             |
| `appendix-steps`     | Appendix C                             |
| `appendix-artifacts` | Appendix E                             |

Optional IDs (include when data exists): `exec-tco`, `exec-architecture`, `exec-security-teaser`, `what-if-scenarios`, `appendix-ai`, `appendix-config`, `appendix-security`, `appendix-security-gap`, `appendix-assumptions`.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GCP to AWS Migration Assessment</title>
  <style>
    /* All CSS inline — see CSS specification below */
  </style>
</head>
<body>
  <div class="report">
    <h1>GCP to AWS Migration Assessment</h1>
    <p class="subtitle"><!-- project · run id · date --></p>
    <div class="executive-summary">
      <section id="decision-summary"><!-- verdict + hero metrics FIRST — the thesis before any menu --></section>
      <nav class="toc" id="toc" aria-label="Table of contents"><!-- AFTER the decision summary, never before --></nav>
      <section id="exec-services"><!-- Primary services --></section>
      <section id="exec-costs"><!-- Cost headline --></section>
      <!-- <section id="what-if-scenarios"> when scenarios/index.json has ≥2 entries -->
      <section id="exec-timeline"><!-- Timeline --></section>
      <section id="exec-risks"><!-- Top risks --></section>
    </div>
    <div class="appendix">
      <section id="appendix-services"><!-- Appendix A --></section>
      <section id="appendix-costs"><!-- Appendix B --></section>
      <section id="appendix-steps"><!-- Appendix C --></section>
      <!-- <section id="appendix-ai"> when AI artifacts exist -->
      <section id="appendix-artifacts"><!-- Appendix E --></section>
      <!-- <section id="appendix-config"> when preferences.json exists -->
      <!-- <section id="appendix-security"> Appendix G -->
    </div>
    <footer>
      Generated by GCP to AWS Migration Advisor — draft for review; verify figures against source JSON artifacts before executive sign-off.
    </footer>
  </div>
</body>
</html>
```

### CSS Specification

The inline CSS is a **readability contract**, not a loose example. Full and
decision reports MUST use the same shell and selectors so visual quality does
not drift between phases. The validator checks the required selectors and
layout properties. Keep the report self-contained: no external fonts,
stylesheets, scripts, or images.

**Layout:**

- `:root`: define reusable semantic colors for page background, surface,
  text, muted text, border, AWS navy, link blue, success, warning, and danger.
- `*`: `box-sizing: border-box`
- `body`: system font stack; margin `0`; color `#1f2328`; background
  `#f6f8fa`; line-height `1.55`; font-size `15px`
- `.report`: max-width `1040px`; margin `0 auto`; padding
  `2rem 1.5rem 4rem`
- `section`: white surface, `1px` border, `8px` radius, padding
  `1.25rem 1.5rem`, margin-bottom `1rem`, and `scroll-margin-top: 1rem`.
  Every executive and appendix section is therefore a distinct card instead
  of prose floating on a white page.
- `.executive-summary` and `.appendix`: use normal document flow; never nest
  `<section>` elements.
- `.appendix-header`: dark AWS-navy visual divider before the detailed
  appendix. It is a `<div>`, not a `<section>`, so section validation remains
  unambiguous.

**Typography:**

The sizes below form a deliberate five-step scale (~1.25 ratio on a `15px`
base): **2rem** display (verdict headline, hero metric values) → **1.85rem**
page title → **1.3rem** section headings → **1.05rem** subheadings →
**0.88rem** table/data text → **0.78rem** captions and labels. When adding a
new element, pick the nearest step — do not invent in-between sizes; a report
whose type sits on a scale reads as designed, one with ad-hoc sizes reads as
assembled.

- `h1`: font-size `1.85rem`; margin-bottom `0.25rem`; border-bottom
  `3px solid #ff9900`; padding-bottom `0.5rem`
- `h2`: font-size `1.3rem`; margin-top `0`; border-bottom `1px solid` the
  border color; padding-bottom `0.45rem`
- `h3`: font-size `1.05rem`; margin-top `1.1rem`; color `#424a53`
- `p`, `ul`, and `ol` inside cards: compact vertical rhythm; default bottom
  margin no larger than `0.8rem`
- `.subtitle` and secondary labels: muted color, smaller type
- `.verdict-headline`: large (`2rem`) typography-first statement with a
  visible accent; meaning must still be carried by its words, not color
- `.verdict`: positive recommendation callout with pale green background,
  green border, and stronger left border. Use it only for go/migrate outcomes;
  stay/defer recommendations use the warning/neutral callout treatment.
- links: visible blue with underline on hover and a high-contrast
  `:focus-visible` outline for keyboard readers

**Tables:**

- `table`: width `100%`; border-collapse collapse; margin
  `0.75rem 0 1rem`; background white; font-size `0.88rem`
- `th`, `td`: **horizontal rules only** — `border: 0; border-bottom: 1px solid` the border color; `0.45rem 0.65rem` padding, left/top alignment. Never add vertical cell borders: grid + zebra + hover is three redundant separation cues (data-ink)
- `thead th`: heavier bottom border (`2px`) to anchor the header row
- `th`: subtle gray background and semibold text (do not use a large dark
  header block for every table)
- `td.num, th.num`: `text-align: right; font-variant-numeric: tabular-nums` — apply `class="num"` to **every numeric column** (currency, hours, weeks, percentages) and its header so magnitudes align for scanning; label/prose columns stay left-aligned
- alternating body rows use a subtle background; hover must not be the only
  way to distinguish rows
- on viewports below `700px`, tables become horizontally scrollable rather
  than shrinking text to an unreadable size

**Cards (for executive summary metrics):**

- `.metrics`: CSS grid using
  `repeat(auto-fit, minmax(180px, 1fr))`, gap `0.75rem`, margin `0.85rem 0`
- `.metric`: white or subtly tinted surface, `1px` border, `8px` radius,
  padding `0.85rem 1rem`; never use inline-block cards with uneven wrapping
- `.metric strong`: block, `1.45rem`, compact line-height
- `.metric span`: muted `0.78rem` uppercase label with slight letter spacing
- `.metric small`: block, muted supporting context
- Put the decision's 3–5 most useful numbers in this grid: combined AWS
  monthly run rate (or the single-track estimate), timeline, per-track costs,
  effort. Do not duplicate the same number merely to fill a card.
- `.metric-hero`: white background, `2px` accent border (e.g. `#0d7377`),
  value ~`1.9rem` — the one or two **primary** decision metrics (run rate,
  timeline) render first with this treatment; the reader should not have to
  rank the numbers themselves.
- **Activate credits are never a metric card** — a credit offer is a
  call-to-action with a link, not a measurement; rendering it in the grid
  gives it false equivalence with the run rate. It renders as the 💡 callout
  (see the Activate callout rules in `report-decision-core.md`), with the
  clickable apply link (`https://aws.amazon.com/startups/credits/`) inside.
- `.chip-warn`: inline pill (pale yellow background, amber border, small bold
  text) for per-metric caveats — e.g. "⚠ not comparable" on the GCP baseline
  card (see the not-comparable rendering rule in `report-decision-core.md`).
- When a supported comparable baseline produces a savings value, apply the
  green `.savings` class to the numeric value. Use `.increase` for a supported
  increase. Never color absolute costs or non-comparable deltas as savings.

**Cost comparison highlight:**

- `.savings`, `.cost-savings`: green and semibold/bold for supported savings
- `.increase`, `.cost-increase`: red and semibold/bold for supported increases

**Warning callout (for human_expertise_required):**

- `.callout`: shared padding, radius, margin, and readable font size
- `.callout-warning`, `.callout-info`, `.callout-ok`: distinct pale
  backgrounds plus borders. Use an icon or explicit label as well as color.

**Confidence badges (visible text = user-facing vocabulary, not JSON):**

- `.badge`: display inline-block; padding 2px 8px; border-radius 12px; font-size 0.75rem; font-weight 600
- `.badge-deterministic`: background #e6f4ea; color #137333 — label **Standard pairing**
- `.badge-inferred`: background #fef7e0; color #b05a00 — label **Tailored to your setup**
- `.badge-billing`: background #fce8e6; color #c5221f — label **Estimated from billing only**

**Risk badges (Top Risks table):**

- `.badge-impact-critical`: background #fce8e6; color #c5221f
- `.badge-impact-high`: background #fef7e0; color #b05a00
- `.badge-like-low`: background #f1f3f4; color #545b64
- `.badge-like-medium`: background #fef7e0; color #b05a00

**Navigation aids:**

- `nav.toc` carries `id="toc"`
- `h2 .toplink`: float right; small, muted, no underline — every section `<h2>` ends with `<a class="toplink" href="#toc">↑ contents</a>`; hidden in `@media print`
- `details.reading-guide`: muted collapsible for how-to-read explanations that would otherwise sit between the reader and the data (see Content Rules)

**Verdict badges (Section 0):**

- `.badge-verdict-migrate`: background #e6f4ea; color #137333 — `migrate_optimized`
- `.badge-verdict-phased`: background #e8f0fe; color #1a73e8 — `migrate_phased`
- `.badge-verdict-stay`: background #fef7e0; color #b05a00 — `stay`
- `.badge-complexity`: background #f1f3f4; color #545b64 — complexity signal

**Print styles:**

- `@media (max-width: 700px)`: reduce report/card padding, force the metric
  grid to one column, make the TOC one column, and allow tables/diagrams to
  scroll horizontally
- `@media print`: white page background, compact report padding, preserve card
  borders, avoid breaks inside metric cards/callouts/table rows, and start the
  appendix on a new page. Do not apply `break-inside: avoid` to entire long
  sections because that creates large blank areas in printed reports.

**Footer:**

- `footer`: margin-top 3rem; padding-top 1rem; border-top 1px solid #e8e8e8; text-align center; color #687078; font-size 0.8rem

### Content Rules

1. **All data must come from artifacts** — do not invent numbers or services. If an artifact field is missing, omit that section.
2. **Currency formatting**: Monthly figures as whole dollars with thousands separators (`$1,415`, `$118`). Use cents only where sub-dollar precision is meaningful (`$1.50`, `$0.40`). Be consistent within the report — do not mix `$118.00` and `$118`.
3. **Percentage formatting**: Include `+` or `-` prefix. Use green styling for savings, red for increases.
4. **No external resources**: No CDN links, no external fonts, no images. Everything inline.
5. **Valid HTML5**: Output must be valid, well-formed HTML5.

### Readability Conventions (enforced by `validate-migration-report.py`)

These move from "example in the fixture" to enforced gate. See `references/shared/validate-migration-report.md` and `fixtures/migration-report-reference.html`.

**Governing principle — structure is information, not decoration.** Every structural device in the report (numbering, labels, badges, dividers, ordering) must encode something true about the content: numbers only for real sequences, badges only for real classifications, position only for real priority (the verdict before the menu, heroes before supporting metrics). When adding a new device, ask what fact it encodes; if the answer is "it looks organized," leave it out. The rules below are applications of this principle.

1. **No numbered headings.** Rendered `<h2>`/`<h3>` headings use plain titles ("Estimated AWS Monthly Run Rate"), never `Section N — …`. The "Section N" labels used elsewhere in _this spec_ are authoring references only and must not appear in output. The table of contents carries structure: executive sections in an ordered `<ol>`, appendices in a separate lettered list (avoids "11. Appendix A" double-numbering). The validator fails on a literal `Section 0` or any `<hN>Section N — …` heading. **Genuine sequences keep their numbers.** This ban targets _decorative_ heading labels only. Real sequences — the migration cluster order, phased timeline weeks, migration phases, and rollback steps — MUST stay ordered (`<ol>` or a numbered table column) because the order carries information the reader needs. Do not flatten them to bullets to satisfy this rule.
2. **No internal scoring trace.** Per-cluster mapping rationale goes in a collapsible `<details class="why">` ("Why this mapping?") block — never a bare `Rubric:` line. The validator fails on a literal `Rubric:` in the body.
3. **Security teaser up top, full detail in the appendix.** `exec-security-teaser` carries a 2–3 line summary that links down to `appendix-security` (full control table) and `appendix-security-gap`. Do not render the full control table in the executive flow.
4. **Expand acronyms** on first use and include a glossary (monthly run rate,
   DMS, OAI, RTO, CUD, SCC, IMDSv2, P95, RAG) in the assumptions section —
   the audience is startup founders, not AWS specialists. Render the glossary
   as a bordered two-column `<table class="glossary-table">` with `Term` and
   `Meaning` headers, one distinct cell per term and definition, a caption,
   and `scope="col"` headers. Do not render it as a `<dl>` or loose paragraphs.
   Define monthly run rate as recurring modeled cloud-service charges and
   explicitly distinguish it from total cost of ownership.
5. **Accessible tables and diagrams.** Every table has a `<caption>` and `scope="col"` on header cells. The architecture diagram is wrapped in `<figure role="img" aria-label="…">` with a `<figcaption>` text alternative.
6. **State the verdict.** The decision summary includes a one-sentence recommendation banner (e.g. "Recommendation: Migrate, phased over 10 weeks — ~$497/mo savings, BigQuery deferred") in addition to the `path_label` badges.
7. **Reader vocabulary in the executive flow.** Artifact filenames (`estimation-infra.json`) and Terraform resource IDs (`aws_guardduty_detector.baseline`) are internal build vocabulary. Use them only in the technical appendices (`appendix-services`, `appendix-costs`, `appendix-security`, `appendix-artifacts`, etc.). In the executive flow (`decision-summary`, `exec-tco`, `exec-costs`, `exec-services`, `exec-architecture`, `exec-security-teaser`, `what-if-scenarios`, `exec-timeline`, `exec-risks`), name things by what the reader controls — "the generated security baseline", "the infrastructure cost estimate", "workshop scenario comparison" — not by the file or resource that produced them. Rewrite tooling-availability notes (e.g. "awsknowledge MCP not invoked") to reader-facing impact, or drop them. The validator fails on a `*.json` artifact filename or an `aws_<resource>.<name>` Terraform ID inside any `exec-*`, `what-if-scenarios`, or `decision-summary` section.
8. **One name per concept.** Use a single consistent label for each recommended choice across the whole report. The recommended Bedrock model and the chosen cost tier keep the same name in the verdict, tables, and appendices (always "Claude Sonnet 4.6 (recommended)", always "Balanced"). Do not alternate "recommended / selected target / design target / projected" for the same item — one label is how the reader keeps their bearings.
9. **Ordered action lists.** In `decision-summary`, `Key decisions ahead` and `Next steps` MUST use `<ol class="compact">`, not `<ul>`. The validator fails when either heading is followed by a bullet list. `Migrate if` / `Stay if` remain unordered lists.
10. **Data first, explanation adjacent.** Never make the reader wade through a how-to-read paragraph or callout to reach the table it explains. Render the data first; put reading guidance in a `<details class="reading-guide">` immediately **after** the table (e.g. "How to read the three cost tiers"). Mandatory caveats that must not be collapsible (the not-comparable rule, baseline-quality labels) attach to the figure they qualify — a `.chip-warn` pill on the metric card plus one line in its `<small>` — rather than a standalone paragraph above the section's data.
11. **Numeric columns aligned.** Every table column whose cells are currency, hours, weeks, or percentages carries `class="num"` on its `<td>`s and header (right-aligned, tabular figures). Mixed cells (a number plus a qualifying `<small>`) still count as numeric.
12. **Corrections and derivations go in disclosures.** When a figure was corrected or derived (e.g. a tier-rule effort estimate replaced by a bottom-up range), the report states the **corrected value plus one clause** in the visible flow and puts the how-we-got-here narrative in a `<details class="why">` ("Why this is lower than the automatic estimate"). Internal classification history is machinery, not decision input — same principle as rule 2.

> **Section IDs are stable anchors, not placement hints.** Some `appendix-*` IDs render in the executive flow on purpose (notably `appendix-assumptions`). Do not rename IDs to match position — the validator and TOC key on them.

## Step 4: Self-Check and Post-Write Validation

After generating the HTML file, verify:

1. **Required section IDs**: Each required ID appears **exactly once** on `<section id="...">` (not on `<div>` or other elements). See validator script.
2. **TOC integrity**: Every `<nav class="toc">` link `href="#id"` resolves to a `<section id="id">`; all required sections are linked.
3. **Appendix not a stub**: Appendix B contains ≥3 cost line items with dollar amounts; Appendix A contains per-cluster or per-service mappings (not only JSON file links).
4. **Security baseline surfaced**: When `projected_costs.breakdown.security_baseline` exists, GuardDuty or dollar-formatted component costs appear in `appendix-security` / `appendix-costs`.
5. **Combined AWS monthly run rate**: When **both**
   `estimation-infra.json` and `estimation-ai.json` exist, exactly one
   `exec-tco` section (legacy ID) with the summed AWS recurring service
   estimate. Never label it TCO. Sum the GCP side only when every source
   baseline is comparable; otherwise show "Not comparable."
6. **Data accuracy**: Cost figures in HTML match the estimation artifact values exactly — **manual / agent self-check**; the automated validator does not verify numerics (see `validate-migration-report.md` scope).
7. **Conditional sections**: AI appendix only present if AI artifacts exist; billing caveats shown when billing_data_available is false; Bedrock monitoring row only when `bedrock_monitoring.tf` exists; startup credits callout only when `STARTUP_PROGRAMS.md` or preference indicates eligibility
8. **Decision summary**: Migration Decision Summary present when estimation or preview artifacts exist; uses `recommendation.path_label` when block present, plus a one-sentence recommendation banner
9. **Human expertise flags**: Warning callouts appear for all services with `human_expertise_required: true`
10. **Valid HTML**: Opening and closing tags match, no broken table structures
11. **No placeholders**: No `[placeholder]` or `TODO` text in the report output
12. **Footer disclaimer**: Footer contains "draft for review"
13. **Readability**: No literal `Rubric:` and no numbered headings (`Section 0`, `Section 1b`, `<hN>Section N — …`); security teaser up top with full table in the appendix; tables have `<caption>`/`scope`; acronyms expanded; one-sentence recommendation banner in decision summary
14. **Reader vocabulary**: No artifact filenames (`*.json`) or Terraform resource IDs (`aws_*.*`) inside `decision-summary` / `exec-*` sections — those names live only in the technical appendices.
15. **Consistent labels**: The recommended model and the chosen cost tier use one consistent name across verdict, tables, and appendices (no "recommended / selected / design target" drift for the same item).
16. **Configuration provenance**: When `preferences.json` exists, `appendix-config` table has Question/assumption, Your choice, Source, and Design consequence columns populated from `prompt` and `design_consequence` fields (see `schema-preferences.md`).
17. **Ordered next steps**: `Key decisions ahead` and `Next steps` in `decision-summary` use `<ol>`, not `<ul>`.

**Run automated validator (mandatory when HTML was written):**

Load `shared/validate-migration-report.md`. Resolve script from plugin root: `$PLUGIN_ROOT/scripts/validate-migration-report.py`.

```bash
python3 "$PLUGIN_ROOT/scripts/validate-migration-report.py" \
  "$MIGRATION_DIR/migration-report.html" \
  --estimation-infra "$MIGRATION_DIR/estimation-infra.json" \
  --estimation-ai "$MIGRATION_DIR/estimation-ai.json" \
  --migration-dir "$MIGRATION_DIR"
```

Pass `--estimation-infra` / `--estimation-ai` only when those files exist in `$MIGRATION_DIR`. Use `--no-readability` only for non-customer test fixtures — not for normal Generate runs.

- On `REPORT_OK`: proceed to Step 5.
- On `REPORT_FAIL`: **rename** to `migration-report.incomplete.html` (default; do not delete), emit all failure lines to the user, and report to parent: "Report generation incomplete — re-run report step or expand appendix per fixtures/migration-report-reference.html". Do **not** claim a complete report was delivered or present a stub/numbered/jargon report as complete.

## Step 5: Open Report in Browser

After writing the HTML file, open it in the user's default browser so they can view it immediately.

Run: `open "$MIGRATION_DIR/migration-report.html"` (macOS) or `xdg-open "$MIGRATION_DIR/migration-report.html"` (Linux).

If the open command fails, fall back to presenting the full file path to the user:

```
Migration report ready — open in your browser:
file://$MIGRATION_DIR/migration-report.html
```

## Completion

Report to the parent orchestrator. **Do NOT update `.phase-status.json`** — the parent `generate.md` handles phase completion.

Output:

```
Migration report saved to $MIGRATION_DIR/migration-report.html

Report sections:
- Executive Summary: Section 0 Migration Decision Summary, [services count] primary services, [cost comparison], [timeline]
- Appendix A: Service Recommendations
- Appendix B: Cost Estimates
- Appendix C: Migration Steps
- [Appendix D: AI Migration — if applicable]
- Appendix E: Artifacts Catalog
- [Appendix F: Your Configuration — if preferences.json exists]
- Appendix G: Security Capabilities
- [Appendix H: Security Gap Analysis — when infra track ran]
- [Appendix I: Assumptions & Validation — always recommended]
```
