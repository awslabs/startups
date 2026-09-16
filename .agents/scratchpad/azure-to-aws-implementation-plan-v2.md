# Azure-to-AWS Migration Skill — Implementation Plan (rev 2, corrected)

> **Where this document lives.** The authoritative copy is
> `.agents/scratchpad/azure-to-aws-implementation-plan-v2.md` in the `awslabs/startups`
> repo, on the branch carrying the work. The Pippin artifact is a **mirror**, published
> from that file.
>
> They forked once already: §11 and §12 were added to the repo copy on 2026-09-04 and the
> Pippin copy sat 8k characters behind them, still describing a build order that §12
> inverts and an Azure SQL disposition that §11.3 overrules. Nothing enforces the sync, so
> if you are editing, **edit the repo file and re-publish** — never the mirror.

Revision of the product owner's plan. Section numbering is preserved so this is diffable
against rev 1. Every change is marked **[CORRECTED]**, **[DECIDED]**, or **[ADDED]**, with
the reason. Claims about this repo were verified against the working tree; file:line
references are given where a claim is load-bearing.

Four decisions locked by the owner before this revision:

1. **DSL-native.** The skill is built on the vendored frontmatter DSL, not a prose state machine.
2. **Correct the repo-mechanics errors** in rev 1.
3. **Honor deprecations** — App Runner is not recommended anywhere. Telemetry must be wired
   even though the backend is not live yet.
4. **Follow gcp-to-aws's product patterns** — decision gate / `run_mode`, assumption-sheet
   wizard, multi-route design/estimate/generate, workshop + feedback sidebars.

---

## 0. Architecture decision

Azure-to-aws is **gcp-to-aws's capability surface implemented on heroku-to-aws's machinery.**

| Borrow from       | What                                                                                                                                                                                                                                                                                                            |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **heroku-to-aws** | The entire execution model: vendored `references/vendored/dsl/INTERPRETER.md`, per-phase `_fragments` + exactly one `_assemble`, `_preconditions`/`_postconditions`, `HANDOFF_OK`/`GATE_FAIL`, `_exec` agent dispatch, `_re_entry_guard`, `_forbids_files`, `_knowledge` JSON data, `_kind: sidebar` + `_gates` |
| **gcp-to-aws**    | The product surface: category-based `design-refs/` (`index.md` + `fast-path.md` + per-category), split-by-concern discovery, assumption-sheet wizard Clarify, multi-route design/estimate/generate, the post-Estimate decision gate and `run_mode`, the confidence vocabulary                                   |

### [CORRECTED] Rev 1 contradicted itself on the state engine

Rev 1 §0 and §10 said "borrow heroku's vendored DSL," but §2 and §3 specified a gcp clone:
`SKILL.md # orchestrator + state machine (gcp-style prose table)`, "follow gcp-to-aws/SKILL.md's
structure section-for-section," "State Machine — identical table shape to gcp's." The rev 1 file
tree contained **no `-assemble.md` in any phase** and declared no fragments.

These are mutually exclusive. `INTERPRETER.md` _derives_ the phase chain from `_advances_to` /
`_requires_phase`; a hand-maintained state-machine table is the exact drift surface the DSL
exists to remove.

The failure mode is silent, which is why this matters more than a style nit:

```
$ node advisor/plugins/aws-startup-advisor/tools/frontmatter-validator/validate.ts \
        advisor/plugins/aws-startup-advisor/skills/gcp-to-aws
frontmatter validation: OK (0 phase file(s) with frontmatter checked)
```

`parse.ts:49` returns null for any file that does not start with `---`, so files without
frontmatter are skipped entirely. A gcp-style clone passes `mise run lint:frontmatter` **green
while being completely unvalidated.** Building rev 1 as written would have shipped a skill the
team believed was DSL-checked and was not.

Consequences for the rest of this document: rev 1 §3 items 5 and 6 (State Machine table, Phase
Summary Table) are **deleted** — the interpreter owns both. `SKILL.md` becomes thin, matching
`heroku-to-aws/SKILL.md`, not `gcp-to-aws/SKILL.md`.

### [ADDED] Where the tunable constants live

Rev 1 put sizing tables in `design-refs/*.md` prose, following gcp. Use heroku's pattern
instead: `knowledge/<phase>/*.json`, referenced from a phase's `_knowledge` with a `_when`
guard. `docs/01-concepts.md` §3 makes this a rule, not a preference — extract data and tunable
constants, never logic or contract.

These are all data and belong in JSON, not prose:

- right-sizing P95 thresholds (`<35%` quarter, `35–70%` half, `≥70%` same) and the
  Low 50 / Medium 60 / High 70 / Aggressive 90 aggressiveness slider
- GPU/HPC series tables (ND/NC/NV/HB/HX → P/G/hpc7a)
- Cosmos RU/s → WCU/RCU divisors, write-percentage and consistency multipliers
- Managed Disk → EBS breakpoints (gp3 to 80K IOPS, then io2)
- Azure region → AWS region map
- VM/AKS/App-Service-plan → EC2/EKS-node/EB-instance sizing tables

`design-refs/*.md` keeps the _rubric_ (how to choose), never the table.

### Startup-weighted, not enterprise-weighted

Unchanged from rev 1 and correct. Postgres/MySQL Flexible Server and Cosmos Core API get full
depth; Azure SQL Database / MI / on-VM, AHUB licensing, and elastic-pool consolidation sit
behind a specialist gate that only fires on detection, mirroring gcp's BigQuery gate.

---

## 1. Repo-wide wiring — corrected and completed

### [CORRECTED] There _is_ an automated cross-tree parity gate

Rev 1: _"There is no automated sync mechanism between the two trees — they are two
independently-maintained copies that happen to currently be kept in parity by hand."_

False. `mise run drift:check` runs `advisor/plugins/aws-startup-advisor/tools/cross-plugin-drift.ts`,
which fails the build on any non-allowlisted byte difference after normalizing three token
classes (invocation prefix, repo paths, schema `$id` form). It is inside `mise run lint`, which
CI runs. `mise run shared:check` separately enforces that each skill's `references/vendored/`
tree is byte-identical to `skills/shared/`.

Two direct consequences rev 1 gets wrong:

- **`SKILLS` at `cross-plugin-drift.ts:33` is `["agent-advisor", "gcp-to-aws", "heroku-to-aws",
  "llm-to-bedrock", "tf-best-practices", "shared"]` and there is no `gcp-to-aws` key in
  `ALLOWLIST`.** So every gcp-to-aws file must be byte-identical across trees after
  normalization. Rev 1 §1 edits `migrate/.../gcp-to-aws/SKILL.md` and
  `migrate/.../heroku-to-aws/SKILL.md` descriptions in the `migrate/` tree only. Neither file
  is allowlisted, and a description edit is not a normalizable token. **Rev 1 §1 as written
  fails CI.** Every skill edit is a two-tree edit.
- **The tool hardcodes `SRC = migrate`, `DST = advisor` and walks SRC only** (`:120`). An
  advisor-only skill added to `SKILLS` walks an empty source tree, checks zero files, and
  passes vacuously — the opposite of protection.

### [DECIDED] Build in both trees

Rev 1 said treat advisor as primary and make mirroring to `migrate/` a judgment call given
pending deprecation. Build **both**, for three reasons: the drift gate only protects a skill
present in both; users on either installed plugin get Azure support simultaneously; and the
mirror is a file copy plus three token rewrites (`aws-startup-advisor:` → `migration-to-aws:`,
the two path rewrites), which `drift:check --list` verifies in one command.

If the team later decides advisor-only, the deliberate action is to **leave `azure-to-aws` out
of the `SKILLS` array with a comment explaining why** — not to add it and accept a check that
silently passes.

### [CORRECTED] Paths in rev 1 that do not exist in this repo

| Rev 1 reference                                                                        | Reality                                                                                                                                                                                                              |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `startups-pr/README.md`                                                                | Does not exist. The file is root `README.md` — and its advisor-tree comment still lists a `migration-to-aws` skill that is not there. Fix it.                                                                        |
| `solution-architecture/plugins/aws-dev-toolkit/skills/migration-azure-to-aws/SKILL.md` | Does not exist. `solution-architecture/` contains only `README.md` and `OWNERS.yaml`. Rev 1 §1's last row and §4b's "reuse its `az` commands" both depend on this file — locate it elsewhere or drop the dependency. |
| "stale flat `migration-to-aws` folder under `advisor/.../skills/`"                     | Not present. `advisor/.../skills/` is already fully split into 10 siblings. Moot.                                                                                                                                    |
| `architect-for-startups/references/migration-azure-to-aws.md`                          | **Exists.** Rev 1's content-source claim and its routing edit are both correct.                                                                                                                                      |

### Complete wiring checklist

Every row is **both trees** unless marked otherwise.

| File                                                                  | Change                                                                                                                                                                             |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `skills/gcp-to-aws/SKILL.md`                                          | Description: `"Do not use for: Azure or on-premises…"` → `"…on-premises migrations to AWS (see azure-to-aws for Azure)…"`                                                          |
| `skills/heroku-to-aws/SKILL.md`                                       | Drop the Azure exclusion; point at `azure-to-aws`                                                                                                                                  |
| `skills/azure-to-aws/SKILL.md` (new)                                  | `"Do not use for: GCP migrations (see gcp-to-aws), Heroku migrations (see heroku-to-aws), general AWS architecture advice without migration intent (see architect-for-startups)."` |
| `.claude-plugin/plugin.json`                                          | Keywords: `azure`, `azure-to-aws`, `aks`, `app-service`, `azure-sql`, `cosmos-db`, `azure-openai`, `entra-id`, `blob-storage`, `bicep`, `arm-template`                             |
| `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`             | **[ADDED]** rev 1 missed these; both trees carry all three manifest flavors                                                                                                        |
| `.claude-plugin/marketplace.json` (root)                              | **[ADDED]** both plugin descriptions mention GCP/Heroku by name; add Azure                                                                                                         |
| `.cursor-plugin/marketplace.json`, `.agents/plugins/marketplace.json` | **[ADDED]** same edit, three more marketplace files exist                                                                                                                          |
| `mise.toml` `lint:frontmatter`                                        | **[ADDED]** two new `validate.ts` lines, one per tree — without these the skill is never validated                                                                                 |
| `tools/cross-plugin-drift.ts` `SKILLS`                                | **[ADDED]** add `"azure-to-aws"`                                                                                                                                                   |
| `hooks/telemetry/emit.mjs` `SKILL_INVENTORY` (`:431`)                 | **[ADDED]** `AZURE_TO_AWS: { inventory: "azure-resource-inventory.json", provider: "AZURE" }`                                                                                      |
| `hooks/telemetry/cursor/hooks.json`                                   | **[ADDED]** currently references only `GCP_TO_AWS` — `HEROKU_TO_AWS` is already missing there; add both it and Azure                                                               |
| `advisor/AGENTS.md`                                                   | **[ADDED]** carries a per-skill section for every sibling; add `azure-to-aws` and the migration-intent routing line                                                                |
| root `README.md`, `migrate/README.md`                                 | Skill tables, supported-sources bullets, "What It Detects" column                                                                                                                  |
| `skills/architect-for-startups/SKILL.md` (advisor only)               | Route real migration intent to `azure-to-aws`; keep `references/migration-azure-to-aws.md` for the pre-decision advisory conversation                                              |

Untouched: `knowledge-base-for-startups`, `prompt-library-for-startups`, `start-building-for-startups`.

---

## 2. File tree

Frontmatter kind is noted per file. **Every phase directory has exactly one `-assemble.md`** —
mandatory, and the single biggest structural gap in rev 1.

```
azure-to-aws/
├── SKILL.md                                    # THIN. Philosophy, definitions, telemetry
│                                               #   consent, cold-start entry phase, sidebar
│                                               #   placement, input security. NO state machine,
│                                               #   NO phase summary table, NO gate recipes.
├── knowledge/                                  # [CORRECTED] data, not prose (was design-refs)
│   ├── design/
│   │   ├── vm-ec2-sizing.json
│   │   ├── aks-eks-sizing.json
│   │   ├── appservice-eb-sizing.json
│   │   ├── flexible-server-rds-sizing.json
│   │   ├── redis-elasticache-sizing.json
│   │   ├── cosmos-dynamodb-conversion.json     # RU→WCU/RCU divisors + multipliers
│   │   ├── disk-ebs-sizing.json                # gp3→io2 breakpoints
│   │   ├── gpu-hpc-sizing.json                 # ND/NC/NV/HB/HX → P/G/hpc7a
│   │   ├── fast-path-services.json             # deterministic 1:1 entries
│   │   └── azure-region-map.json
│   └── estimate/
│       ├── estimate-defaults.json
│       └── rightsizing-thresholds.json         # P95 bands + aggressiveness slider
├── data/
│   └── (none — sdk-capability-map.json promoted to shared/, see §6a)
├── references/
│   ├── vendored/                               # byte-synced; `mise run shared:sync`
│   │   ├── dsl/INTERPRETER.md
│   │   ├── state/phase-status.schema.json
│   │   ├── estimate/{complexity-tiers.json,estimation-infra.schema.json,pricing-mode.md}
│   │   ├── pricing/aws-infra-pricing.json
│   │   ├── workshop/workshop-invariants.md
│   │   └── ai/                                 # promoted shared AI content, §6a
│   ├── shared/
│   │   ├── schema-discover-azure.md            # azure-resource-inventory + clusters
│   │   ├── arm-type-canonicalization.md        # azurerm_* → Microsoft.* table (§7a.7)
│   │   ├── extract-terraform.md                # per-dialect extraction rules, loaded by
│   │   ├── extract-bicep.md                    #   discover-iac.md only for the dialects
│   │   ├── extract-arm.md                      #   actually present (§4d budget mitigation)
│   │   ├── schema-discover-rdfa.md             # reservations + utilization profiles
│   │   ├── schema-discover-ai.md
│   │   ├── schema-discover-billing.md
│   │   ├── schema-workshop-scenarios.md
│   │   ├── schema-preferences.md
│   │   ├── azure-live-security-contract.md     # [ADDED] see §4b — the expensive one
│   │   ├── azure-pricing-cache.md
│   │   └── migration-complexity.md
│   ├── design-refs/                            # RUBRICS only; tables live in knowledge/
│   │   ├── index.md
│   │   ├── fast-path.md
│   │   ├── compute.md                          # App Service → Elastic Beanstalk / Fargate
│   │   ├── database.md                         # Flexible Server primary, Cosmos secondary
│   │   ├── database-specialist-gate.md
│   │   ├── licensing.md                        # conditional load
│   │   ├── storage.md
│   │   ├── networking.md
│   │   ├── messaging.md
│   │   ├── analytics.md
│   │   ├── identity.md
│   │   ├── gpu-hpc.md
│   │   ├── specialist-gates.md                 # gate TABLE, not 5 inlined blocks (§7a.4)
│   │   └── patterns.md                         # pattern catalog + recognition rules (§7a.8)
│   ├── clustering/                             # §4f — RG seed + typed edges
│   │   ├── classification-rules.md             # primary/secondary (ported)
│   │   ├── typed-edges-strategy.md             # ported + Azure edge types
│   │   ├── clustering-algorithm.md             # RG seed, then split/merge
│   │   └── tiering.md                          # fixed tiers, replaces depth-calculation
│   └── phases/
│       ├── discover/                           # _init, _exec rw, _interactive false
│       │   ├── discover.md                     # PHASE
│       │   ├── discover-live-capture.md        # [ADDED] MAIN-WINDOW pre-work, not a fragment
│       │   ├── discover-iac.md                 # FRAGMENT — Terraform + Bicep + ARM,
│       │   │                                   #   _always trigger, exits clean if none
│       │   ├── discover-rdfa.md                # FRAGMENT
│       │   ├── discover-live.md                # FRAGMENT (parses live-capture/)
│       │   ├── discover-app-code.md            # FRAGMENT
│       │   ├── discover-billing.md             # FRAGMENT
│       │   └── discover-assemble.md            # ASSEMBLER
│       ├── clarify/                            # _interactive true, no _exec
│       │   ├── clarify.md
│       │   ├── clarify-global.md
│       │   ├── clarify-compute.md
│       │   ├── clarify-database.md
│       │   ├── clarify-licensing.md            # _when Windows/SQL detected
│       │   ├── clarify-identity.md
│       │   ├── clarify-ai.md
│       │   ├── clarify-ai-only.md
│       │   └── clarify-assemble.md             # ASSEMBLER
│       ├── design/
│       │   ├── design.md
│       │   ├── design-infra.md
│       │   ├── design-ai.md
│       │   ├── design-billing.md
│       │   └── design-assemble.md              # ASSEMBLER
│       ├── estimate/
│       │   ├── estimate.md
│       │   ├── estimate-infra.md               # dual non-optimized/optimized output
│       │   ├── estimate-ai.md
│       │   ├── estimate-billing.md
│       │   └── estimate-assemble.md            # ASSEMBLER — owns the decision gate
│       ├── workshop/                           # [ADDED] sidebar, was missing from rev 1
│       │   ├── workshop.md
│       │   ├── workshop-sheet.md
│       │   ├── workshop-refresh.md
│       │   ├── workshop-compare.md
│       │   └── workshop-assemble.md            # ASSEMBLER
│       ├── generate/                           # _exec rw, _interactive false
│       │   ├── generate.md
│       │   ├── generate-artifacts-infra.md
│       │   ├── generate-artifacts-scripts.md
│       │   ├── generate-artifacts-ai.md
│       │   ├── generate-artifacts-docs.md
│       │   ├── generate-artifacts-report.md
│       │   ├── generate-handoff-ai.md
│       │   └── generate-assemble.md            # ASSEMBLER
│       └── feedback/                           # sidebar
│           ├── feedback.md
│           ├── feedback-collect.md
│           ├── feedback-trace.md
│           └── feedback-assemble.md            # ASSEMBLER
```

---

## 3. SKILL.md — thin, not a gcp clone

**[CORRECTED]** Rev 1 item 5 (State Machine table) and item 6 (Phase Summary Table) are
deleted. `INTERPRETER.md` derives phase order, gates, and state transitions from frontmatter;
restating them is duplication the concepts doc explicitly forbids. Model on
`heroku-to-aws/SKILL.md`, which is 324 lines to gcp's 504 and carries no state machine.

What SKILL.md keeps:

1. **Frontmatter** — `name`, `description`, and the telemetry hooks block (§3a).
2. **Description triggers** — "migrate from Azure", "Azure to AWS", "move off Azure",
   "migrate AKS to EKS", "migrate App Service to AWS", "migrate Azure SQL to RDS",
   "migrate Cosmos DB to DynamoDB", "migrate Azure OpenAI to Bedrock", "estimate AWS costs
   for my Azure infrastructure", plus the shared AI phrases.
   **[CORRECTED]** Rev 1's trigger phrase was _"migrate App Service to App Runner"_ — see §3b.
3. **Philosophy** — re-platform by default; dev sizing unless specified; no human-labor costs;
   live-first discovery (§4b); startup-weighted with SQL/AHUB/Synapse specialist-gated;
   **[ADDED]** Windows/.NET inverts the repo's Graviton default (`shared/graviton.md` already
   has the x86 escape path for Windows/.NET Framework, GPU/CUDA, RDS SQL Server — Azure fleets
   hit it routinely where GCP fleets do not).
4. **Context loading rules** — ~800-line per-phase budget. Do not maintain a load-condition
   table here; each phase declares its own via fragment `_trigger` and `_knowledge` `_when`.
5. **Phase Structure (frontmatter)** — the paragraph pointing at the vendored `INTERPRETER.md`
   as the contract, verbatim in shape from heroku's.
6. **Execution** — telemetry consent, then cold-start entry phase (`discover`, the one with
   `_init: true`), then hand control to the interpreter loop.
7. **Input security** — untrusted-data clause covering Terraform, Bicep, ARM, app code, billing
   exports, RDfA ZIPs, and `az` CLI captures.
8. **Sidebar placement** — where `workshop` and `feedback` are offered. This is orchestration
   prose and legitimately belongs in SKILL.md.
9. **Scope notes and defaults.**

### [ADDED] 3a. Telemetry — wire it now

> **[DEFERRED 2026-09-06] Not on this branch.** This branch is cut from `main`, and
> `hooks/telemetry/` exists only on `feat/telemetry-hooks` — there is no emitter to wire
> to, so `azure-to-aws/SKILL.md` carries no `hooks:` block and no consent step. Everything
> below is still the intended design; it lands as a follow-up commit on the telemetry
> branch, or after that branch merges. The two `emit.mjs` defects described below are
> likewise unfixed here and still need fixing there.


Rev 1 omits telemetry entirely. Both existing migration skills carry it and it is a shipping
requirement. Backend liveness is irrelevant to the wiring.

- **Skill frontmatter hooks** — `PostToolUse` matching `Write|Edit` and `Stop` with
  `--reconcile`, both calling `emit.mjs --skill AZURE_TO_AWS`. Copy heroku's block verbatim,
  including the comment recording that a `SessionEnd` hook in skill frontmatter is never
  invoked and must be registered in the plugin's own `hooks/hooks.json`.
- **Consent step** in SKILL.md Execution, cold start only, **before the first
  `.phase-status.json` write** — including the `$EMIT` resolution ladder verbatim. Asking after
  Discover writes state permanently loses that run's first transitions.
- **`SKILL_INVENTORY` entry** at `emit.mjs:431`.

**Two defects in `emit.mjs` that a third skill triggers.** Both are silent, and both land in
the telemetry work currently in flight on `feat/telemetry-hooks`:

- **`emit.mjs:868`** — the run-ownership guard resolves a single "other" skill via
  `.find(([name]) => name !== skill)`. With three skills registered, a GCP-registered hook
  looking at an Azure run resolves `other` to `HEROKU_TO_AWS`, whose inventory file is absent,
  so the guard does not fire and the Azure run is reported as `sourceProvider: GCP`. Needs
  `.filter()` over all other skills, with the guard firing if _any_ other skill's inventory is
  present and its own is not.
- **`emit.mjs:459`** — `costContainer` reads `current_costs ?? gcp_baseline`. An Azure
  billing-only route needs `azure_baseline` (or a provider-keyed lookup) or every spend
  attribute silently drops. This is the bug the comment above that line documents having
  already happened once, at $685M measured spend.

### [CORRECTED] 3b. App Runner is not recommended anywhere

`heroku-to-aws/SKILL.md:36` is a standing repo rule: _"Do not recommend AWS App Runner (no
longer accepting new customers as of April 2026)."_

Rev 1 violates it in three places: `compute.md` ("App Service→App Runner/EB"), the §7 CloudRays
port row, and — worst — the SKILL.md **description trigger phrase**, which is the string the
model matches on. Recommending a closed service in the skill's own trigger text is the highest-
visibility possible placement.

Correct mapping, consistent with heroku's PaaS-to-PaaS posture:

- **App Service (Linux/Windows) → Elastic Beanstalk (default)**, Fargate as the override for
  direct container control, EKS for teams with existing Kubernetes expertise.
- ECS Express Mode may be mentioned only as a forward-look on the Fargate override path.

---

## 4. Discover — five sources, one artifact shape

Fragments are a flat, independent set: none reads another's output, each has one reason to
change. Every source fragment `_contributes` to `azure-resource-inventory.json`; the
**assembler** is its single creator and also derives `azure-resource-clusters.json`.

### [ADDED] 4.0 The consent problem the DSL creates

`discover` runs under `_exec: { _agent: rw }` with `_interactive: false`, because Azure
discovery is bulky and self-contained. A dispatched worker is file-only and **cannot prompt the
user** — CI rejects `_exec` without `_interactive: false`.

Live `az` discovery needs consent _and_ interactive preflight. Heroku already solved this and
azure must copy the solution exactly: `discover-live-capture.md` is **main-window pre-work**,
not a fragment. It is invoked from the phase's `_preconditions` `_assert` prose, runs consent +
capture to `$MIGRATION_DIR/live-capture/`, and then the dispatched `live` fragment merely parses
that directory. See `heroku-to-aws/references/phases/discover/discover.md` `_preconditions` for
the pattern.

RDfA needs no such split — reading a ZIP the customer already handed over is not interactive —
so it stays a plain fragment.

### [DECIDED] 4a/4b. Live `az` is offered first; RDfA is the accuracy upgrade

Rev 1 makes RDfA the default and live CLI the fallback. Inverted, for consistency with rev 1's
own startup-weighting principle:

- RDfA asks the customer to run a PowerShell script and hand over a ZIP **before they have
  decided to migrate**. That is a real ask at the top of the funnel.
- `heroku-to-aws` is explicitly live-first because "most startups have no `heroku_*` Terraform,
  and the account is authoritative for what actually runs." The same logic holds for Azure.
- The owner asked for "`az` cli just like we did gcp-cli," where live discovery is first-class.

So: **offer live `az` first** when a session is authenticated. Present RDfA as the upgrade when
right-sizing dollars matter, and recommend it outright above roughly a handful of subscriptions
(RDfA has built-in parallelism, resume, and obfuscation; the live path has no equivalent).
Everything else in rev 1 §4a is kept and is good:

- **Reservation `$0` trap** — VMs at `$0` in consumption are pre-paid RIs, not free. Write
  `azure-reservations-profile.json`; Estimate uses the RI-equivalent rate as baseline, never
  literal `$0`. Dedicated fixture and asserter.
- **Obfuscation prefix as a free signal** — extract `prod_` / `nonprod_` directly as the
  environment classification rather than re-deriving it from names.
- **Metrics lookback affects confidence** — read the actual `-MetricsLookbackDays` from report
  metadata; downgrade right-sizing confidence below ~14 days.

**Azure Migrate is correctly excluded** — it discovers on-premises estates for moving _into_
Azure and has no role here.

### [ADDED] 4b-security. The `az` security contract is the most expensive file in the skill

Rev 1 §4b lists commands (`az vm list --show-details`, `az resource list`, `az aks list`,
`az webapp list`, `az cosmosdb list`, `az network vnet list`, `az role assignment list --all`,
`az graph query`) with **no security contract at all**. gcp's `discover-live.md` is 482 lines
dominated by exactly that contract. Azure needs a stricter one, because ordinary _read_ commands
return secrets by default:

| Command                                   | Returns                | Rule                                 |
| ----------------------------------------- | ---------------------- | ------------------------------------ |
| `az webapp config appsettings list`       | app setting **values** | name-only `--query "[].name"`        |
| `az functionapp config appsettings list`  | app setting **values** | name-only projection                 |
| `az webapp config connection-string list` | connection strings     | name-only projection                 |
| `az storage account keys list`            | account keys           | **banned**                           |
| `az keyvault secret show`                 | the secret             | **banned** (`secret list` for names) |
| `az account get-access-token`             | credentials            | **banned** (gcloud analogue)         |

`references/shared/azure-live-security-contract.md` must carry:

1. **Exact-command whitelist** with a mandatory `--query` projection per entry. A verb ban alone
   is insufficient here — that is the substantive difference from gcloud.
2. **Mutating-verb ban**: `create`, `update`, `delete`, `set`, `add`, `remove`, `deploy`,
   `start`, `stop`, `restart`, `purge`, `invoke`, plus interactive `az login`.
3. **Always-explicit scope** — `--subscription "$AZURE_SUBSCRIPTION"` on every command; never
   rely on the active CLI context.
4. **Capture to files, not context** — write under `$MIGRATION_DIR/live-capture/` (gitignored by
   `_init`); process anything large with a throwaway extraction script.
5. **Sensitive-key redaction** applied to every config field before it enters an artifact.
6. **Resource Graph consent sub-gate** — `az graph query` needs
   `az extension add --name resource-graph`, which is an _install_. It requires its own consent
   step and a per-service `az ... list` fallback when declined.
7. **Scope `az role assignment list --all`** or drop it — a tenant-wide identity graph is a lot
   of sensitive data to pull for a lightweight identity recommendation (§5 Category J).

Also specify where a customer-supplied RDfA ZIP is written and that its extracted contents land
under `$MIGRATION_DIR/` so the existing `.gitignore` covers them.

### 4c/4d. Billing-only and IaC

Billing-only unchanged: Azure Cost Management CSV/JSON, `billing_inferred`, no utilization.

**[DECIDED] IaC is ONE fragment covering all three dialects.** Terraform `azurerm_*`, `.bicep`,
and ARM JSON all live in a single `discover-iac.md`, as rev 1 specified and as gcp does.

An earlier draft of this revision proposed splitting them three ways on the DSL's one-source-per-
fragment rule (`docs/01-concepts.md` §4). Overruled, and the single fragment is defensible on the
same rule: Bicep compiles _to_ ARM and both key off the same `Microsoft.*` resource-type
namespace, so they share one reason to change; all three converge on one output section of one
artifact; and the extraction semantics (Azure resource type → inventory entry) are shared, with
only the surface syntax differing. It is also a guideline in the concepts doc, not a mechanical
validator check — nothing fails either way.

Three implementation consequences follow from the single-fragment choice, and all three need
handling:

1. **Trigger must be `{ _always: true }`, not a `_glob`.** No single glob spans `.tf`, `.bicep`,
   and ARM templates (ARM is plain `.json`, identifiable only by a `$schema` containing
   `deploymentTemplate`). A `_when` would work but fails open — a misjudgment silently drops all
   IaC discovery. Use heroku's precedent instead: `discover-terraform.md` runs on
   `{ _always: true }` and exits cleanly when it finds nothing. Detect the dialects _inside_ the
   fragment. This removes the fails-open risk entirely rather than mitigating it.
2. **Context budget is the real cost.** gcp's `discover-iac.md` is 402 lines for Terraform alone;
   heroku's `discover-terraform.md` is 560 for Terraform plus Procfile/app.json. Three dialects
   in one file lands well past the skill's own ~800-line-per-phase budget, and `discover` also
   loads the app-code, billing, RDfA, and live fragments. Mitigation: keep `discover-iac.md` as
   the single fragment and contract, but push per-dialect extraction rules into
   `references/shared/` files it loads only for the dialects actually present — the pattern gcp
   already uses when `discover-iac.md` loads `schema-discover-iac.md`. One fragment, bounded
   loads.
3. **Provenance must be asserted per dialect.** Because one fragment always runs and may exit
   empty, the phase's `_postconditions` cannot infer "IaC ran" from "the fragment ran." Copy
   heroku's assert shape: `metadata.discovery_sources` reflects which dialects actually produced
   data, and _if_ `.tf` / `.bicep` / ARM files were found in the workspace, `resources[]` contains
   at least one entry sourced from each dialect that was found.

All three dialects ship in v1 — Bicep is what Azure users actually write, and it is the piece
with no gcp analogue, so excluding it would leave a real gap.

### [CORRECTED] 4e. Confidence vocabulary — rename `rdfa_inferred` to `measured`

Four tiers, as rev 1 proposed, with the third renamed:

| Label              | Meaning                                                    | Source                                              |
| ------------------ | ---------------------------------------------------------- | --------------------------------------------------- |
| `deterministic`    | fixed 1:1 table lookup                                     | `fast-path.md` direct mappings                      |
| `measured`         | rubric backed by observed utilization, not declared config | RDfA 31-day rollup **or** `az monitor metrics list` |
| `inferred`         | rubric from declared config only                           | IaC, or live CLI without metrics                    |
| `billing_inferred` | billing-only fallback                                      | Cost Management export                              |

Naming the tier after one tool means the live path can never earn it even when it supplies the
same evidence — and rev 1 §4b itself notes live metrics are reachable. `measured` keeps the
4-tier design and drops the coupling. User-facing label unchanged: **"Measured from your actual
usage."**

### 4f. Clustering — RG seeds the partition, typed edges refine it

**[CORRECTED — supersedes both rev 1 and an earlier draft of this revision.]** An earlier draft
said "cluster by Resource Group, skip gcp's typed-edges and depth machinery, one file, done."
That optimizes for cheapness and defeats the stated purpose of clustering, which is to make the
recommendation **holistic** — per-resource mappings miss the architecture.

**Resource groups alone do not express relatedness.** Real estates lay them out four ways:

| RG layout                                         | Does RG-only clustering work?                       |
| ------------------------------------------------- | --------------------------------------------------- |
| one app per RG                                    | yes                                                 |
| one RG per environment, several apps              | no — splits nothing                                 |
| horizontal RGs by type (`rg-databases`, `rg-app`) | no — actively separates things that belong together |
| one RG for everything (startup default)           | no signal at all                                    |

So RG is a good **seed** and a bad final answer.

**Azure's edge data is richer than GCP's, and does not require IaC.** GCP's graph comes from
Terraform reference expressions, so it exists only when IaC does. Azure embeds full ARM resource
IDs inside resource _properties_, so edges survive every discovery source:

| Edge                                           | Meaning                                            |
| ---------------------------------------------- | -------------------------------------------------- |
| `serverFarmId` on a web app → App Service Plan | hard edge; also what fixes the §7a.6 cost trap     |
| `subnetId` / `virtualNetworkSubnetId`          | VNet colocation                                    |
| private endpoint → the resource it fronts      | explicit app-to-data edge                          |
| Key Vault reference in app settings            | secret dependency                                  |
| managed identity + role assignment scope       | "app X reads storage Y" — cleaner than GCP exposes |
| `app=` / `workload=` tags                      | declared intent when present                       |

**Algorithm: seed from RG, then split and merge.**

1. Seed one candidate cluster per resource group.
2. **Split** a candidate whose contents have no edges between them (the per-environment case).
3. **Merge** candidates when edges cross RG boundaries (the horizontal-RG case).
4. Assign tier (below) and emit `azure-resource-clusters.json` including **the edge set that
   justified each cluster** — the Clarify assumption sheet needs it to explain _why_ five
   resources were called one workload.

Which of gcp's four clustering files are needed, revising the earlier "one file" claim:

| gcp file                  | Verdict                                                                                                                                                    |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `classification-rules.md` | **Port** — primary/secondary; an earlier draft wrongly called this net-new                                                                                 |
| `typed-edges-strategy.md` | **Port and extend** — Azure has more edge types than GCP                                                                                                   |
| `clustering-algorithm.md` | **Adapt** — seed from RG instead of building from nothing                                                                                                  |
| `depth-calculation.md`    | **Simplify** — replace topological depth with fixed tiers: network/identity/secrets → data → compute → edge. This is also what Generate's sequencing wants |

**Consequence for rubric criterion 5 (Cluster Context).** With real edges it becomes a valid
signal again. Under RG-only clustering it would have been misleading — affinity across an
arbitrary filing boundary is noise, and an RG containing a Kubernetes cluster plus an unrelated
static site would have actively corrupted mappings. No change to the criterion is needed once
edges exist.

### 4g. [ADDED] Source precedence — the five sources are additive, and disagreements are drift

Rev 1 says the discovery paths "produce the same artifact shape" but never states what happens
when two of them disagree about the same resource. Both siblings define this explicitly — heroku's
rule is "live wins for current state, Terraform supplements structure and provenance, and
disagreements are surfaced as drift, never silently resolved." With five sources Azure needs more
than a one-liner.

**The sources are complementary, not redundant:**

- **Terraform / Bicep / ARM** carry _declared intent_ — module structure, naming, what is
  parameterized. This is what Generate needs to emit idiomatic replacement Terraform, and it is
  the only source for resources that are declared but not yet deployed.
- **RDfA / live `az`** carry _actual state_, including resources that drifted from IaC or were
  never in it. RDfA uniquely adds 31-day utilization and reservations, which is what turns
  right-sizing into a measurement instead of a guess (§7a.5).

So a customer with both IaC and RDfA gets a materially better result than either alone.

**Precedence, highest first:**

| Rank | Source    | Authoritative for                                                                                                                |
| ---- | --------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1    | live `az` | current existence and configuration — it is _now_                                                                                |
| 2    | RDfA      | utilization, reservations, consumption. Loses to live on state (a ZIP may be days old), wins on measurement (live has no rollup) |
| 3    | IaC       | nothing about state; authoritative for provenance, module structure, and declared-but-undeployed resources                       |
| 4    | billing   | fallback only — `billing_inferred`                                                                                               |

**Any disagreement becomes a drift entry, never silently reconciled.** The inventory records both
values, their sources, and which one won, so the report can surface "your Terraform says
`Standard_D2s_v3`, your tenant is running `Standard_D4s_v3`" rather than quietly picking one. This
is also a customer-visible value in its own right — drift they did not know they had.

`metadata.discovery_sources` records which sources actually produced data, and the §4d provenance
asserts extend to it.

### 4h. App-code discovery

Kept from rev 1. Port gcp's `discover-app-code.md` (secret-file exclusion, dependency-manifest
scanning, agentic signals 3B.1–3B.9 are cloud-agnostic). Azure-specific additions:

- Python `AzureOpenAI` client, `openai.api_type = "azure"`, env vars `AZURE_OPENAI_ENDPOINT` /
  `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT_NAME`
- Node `@azure/openai`, `AzureOpenAI` client
- `azure-ai-inference` / `@azure-rest/ai-inference` (AI Foundry model catalog)
- New `ai_source: "azure_openai"`, routed to the **same** `ai-openai-to-bedrock.md` — the model
  catalog and Bedrock mapping do not change based on which endpoint served the calls.

---

## 5. Clarify — Azure-specific categories

Follow gcp's disposition catalog (DETECTED / PROPOSED / ESSENTIAL / N/A) and assumption-sheet
wizard. Both new categories kept exactly as rev 1 specified — they are well-judged:

- **Category I — Licensing**, conditional. N/A and `licensing.md` never loads when there are no
  Windows VM images, no `Microsoft.Sql/*`, and no SQL-on-VM signatures. When it fires: one
  essential question (License Included vs BYOL via Dedicated Hosts). Azure Edition Windows
  Server is a special case — no question, a hard blocker warning, since MGN will refuse the
  image until it is re-imaged.
- **Category J — Identity**, always fires, one shallow question, defaults to `[A]` fresh IAM
  Identity Center re-invite. Option B (full Entra ID) exists but is not the assumed path.

Database tiering unchanged: Flexible Server primary/full depth with gcp's Q6-style availability
selector; Cosmos Core API secondary; Azure SQL / MI / on-VM / elastic pools specialist-gated
with no AHUB core-minimum math or bin-packing ported.

**[ADDED] Cosmos needs a per-API routing table even though depth stays on Core.** Rev 1 covers
only the Core (SQL) API. Add: Mongo API → DocumentDB (the one startups actually hit, since it is
the drop-in), Cassandra → Keyspaces, Gremlin → Neptune, Table → DynamoDB. Depth on Core, routing
for all five.

---

## 6. AI handoff

### 6a. Promote shared AI content — [ADDED] risk detail

Rev 1's promotion list is correct, and correctly omits `ai-gemini-to-bedrock.md` (genuinely
GCP-specific). Three corrections:

- **[CORRECTED] `mise run shared:sync` needs no extension.** Rev 1 says it "currently only
  covers the DSL files — extend it." It does not work that way:
  `sync-vendored-shared.ts:53-70` walks each skill's `references/vendored/` tree and requires
  each file to match `skills/shared/<same relative path>`. Create `skills/shared/ai/*.md` and
  `azure-to-aws/references/vendored/ai/*.md` and the existing machinery covers it. Partial
  vendoring is fine — it walks the vendored side, not the canonical side, so gcp and azure need
  not vendor identical subsets.
- **[ADDED] Promote `data/sdk-capability-map.json` too.** Rev 1 says "copy of gcp's; extend with
  Azure OpenAI entries." A copy is a third drift surface, by rev 1 §6a's own argument. Move it
  to `skills/shared/ai/` and vendor it.
- **[ADDED] Blast radius.** This is the highest-risk item in the plan and rev 1 underweights it.
  It is a simultaneous two-tree change that also rewrites every path reference inside
  gcp-to-aws (its SKILL.md conditional-load table, `design-refs/index.md`, `design-ai.md`,
  `clarify-ai.md`), and `shared` is itself in the drift `SKILLS` array with only three
  allowlisted files. Land it as its own PR, before any azure work, with gcp's AI-only flow
  smoke-tested after.

### 6b/6c. Handoff mechanism

Kept as-is: pointer + `handoff-summary.md`, not a live Skill-tool call, reusing
`agent-advisor`'s existing Gate 1 decline pattern. Route A vs B off
`agentic_profile.is_agentic`. `generate-handoff-ai.md` writes the summary.

**[CORRECTED] Minor contradiction.** Rev 1 §6c says azure "does not need its own AI-only entry
point," but the §2 tree includes `clarify/clarify-ai-only.md`. Keep the file — an Azure-OpenAI-only
run that enters through azure-to-aws still needs the AI-only Clarify path — and drop the §6c
sentence. The pure `llm-to-bedrock`-initiated route is unchanged and still goes through
gcp-to-aws's cloud-agnostic mode.

---

## 7. Design-refs depth

Rev 1 §7's CloudRays sourcing table stands, with three changes:

- **App Service → Elastic Beanstalk / Fargate**, never App Runner (§3b).
- **[CORRECTED] Event Hubs → a rubric, not a flat 1:1.** Rev 1 maps Event Hubs → Kinesis. Event
  Hubs exposes a Kafka-protocol endpoint, so MSK is materially lower-friction for anyone using
  that surface. Rubric: Kafka-protocol consumers → MSK; native AMQP / Event Hubs SDK → Kinesis.
- **Tables move to `knowledge/*.json`** (§0); `design-refs/*.md` keeps the rubric.

Everything else holds: full depth on compute right-sizing (the largest savings lever), GPU/HPC
tables, storage, networking "free on AWS" wins, Flexible Server, Redis; Cosmos conversion kept
assumption-sensitive with its caveat intact; Synapse specialist-gated, Databricks full depth;
licensing detection-and-warn only; identity sourced from
`architect-for-startups/references/migration-azure-to-aws.md`. Rev 1's "explicitly NOT ported"
list is correct and complete.

---

## 7a. [ADDED] The mapping algorithm

Rev 1 named mapping _targets_ but never specified the algorithm that assigns them, or which
targets are pre-determined versus reasoned. This section defines both. It is the port of gcp's
`design-infra.md` + `fast-path.md` + `design-refs/*.md`, with the Azure deltas made explicit.

**Two product goals it has to satisfy at once:**

1. **Holistic recommendations** — the output should describe workloads, not 40 independent rows.
2. **Pre-determined recommendations where there is no ambiguity** — an unambiguous service should
   not be routed through a rubric that could reason its way to a different answer.

These pull in opposite directions the moment a workload-level decision disagrees with a
per-resource one, so §7a.2 defines a precedence order and an invariant that reconciles them.

### 7a.1 What gcp's algorithm does (the thing being ported)

Five stages in `design-infra.md`, driven by four tables in `fast-path.md`:

1. **Order clusters** by `creation_order_depth`.
2. **Pass 1 — fast-path.** Exact Terraform type match in **Direct Mappings**; if the row's
   `Conditions` hold, assign the target with `confidence: deterministic` and run **no rubric**.
   14 rows today.
3. **Pass 2 — rubric.** Specialist gate first (BigQuery, a hardcoded `google_bigquery_` prefix
   check → `Deferred — specialist engagement`), then category lookup via `index.md`, then six
   criteria applied **in order, first match wins**: Eliminators, Operational Model, User
   Preference, Feature Parity, Cluster Context, Simplicity → `confidence: inferred`. An unknown
   type not in `index.md` and not name-pattern-matchable → **STOP**.
4. **Post-rubric override gates.** The Cloud SQL Q6 availability gate _forces_ RDS vs Aurora
   regardless of rubric output, and `multi-az-ha`/`multi-region` are never inferable from IaC.
   Then a **Preferred AWS Target** substitution pass with named exemptions.
5. **Secondaries → awsknowledge validation** (regional availability, feature parity;
   non-blocking) → write `aws-design.json` with per-resource `rationale` + `rubric_applied`.

Two-tier confidence vocabulary throughout: JSON keeps the enum; user-facing text says "Standard
pairing" / "Tailored to your setup" / "Estimated from billing only" (Azure adds "Measured from
your actual usage" — §4e).

### 7a.2 Precedence order and the invariant

Azure's order, extending gcp's with the pattern stage:

1. Skip Mappings — not a target at all
2. **Specialist gates → `Deferred`** — "we do not know" must never be overridden by anything below
3. **Eliminators** — hard technical blockers (Lambda's 15-minute ceiling is physics)
4. **Direct Mappings → `deterministic`** — the pre-determined recommendations
5. **Pattern constraint** — the holistic layer; applies to whatever is left
6. **6-criteria rubric** — chooses _within_ the pattern's candidate set
7. Preferred-target substitution
8. Post-selection: right-sizing from measured utilization (§7a.5), CPU architecture

> **INVARIANT: a pattern may never change a `deterministic` mapping's target. It may only choose
> among rubric candidates.**

If a pattern could override a fast-path row, the `deterministic` tier would stop meaning anything
and its user-facing label ("Standard pairing") would be false. So a genuine pattern/fast-path
conflict is evidence the row does not belong in Direct Mappings — the fix is to demote the row,
never to let the pattern win.

### 7a.3 The admission test for Direct Mappings

The invariant yields a sharper test than "is it 1:1?": **is this target correct regardless of the
surrounding architecture?** Architecture-invariant rows are admissible; everything else is rubric.

**Direct Mappings — 10 rows, all infrastructure primitives, no compute:**

| Azure (canonical ARM type)                         | AWS                              | Conditions |
| -------------------------------------------------- | -------------------------------- | ---------- |
| `Microsoft.Storage/storageAccounts` (blob)         | S3                               | Always     |
| `Microsoft.Compute/disks`                          | EBS                              | Always     |
| `Microsoft.Network/virtualNetworks`                | VPC                              | Always     |
| `Microsoft.Network/networkSecurityGroups`          | Security Group                   | Always     |
| `Microsoft.Network/dnsZones`                       | Route 53 hosted zone             | Always     |
| `Microsoft.KeyVault/vaults`                        | Secrets Manager (+ KMS for keys) | Always     |
| `Microsoft.Cache/Redis`                            | ElastiCache Redis                | Always     |
| `Microsoft.ContainerRegistry/registries`           | ECR                              | Always     |
| `Microsoft.ManagedIdentity/userAssignedIdentities` | IAM Role                         | Always     |
| `Microsoft.ContainerService/managedClusters`       | EKS                              | Always     |

**Demoted from an earlier draft:** `Microsoft.Web/sites` (kind=functionapp) → Lambda **fails** the
test and moves to the rubric. A function inside an otherwise Fargate-based workload may belong on
Fargate, and durable or long-running functions hit the eliminator anyway.

The resulting split is the clean expression of both product goals: **pre-determined for
primitives, holistic for workloads.** Disk sizing (gp3 → io2 by IOPS) is post-selection, so it
does not compromise the `Always` condition on the disks row.

### 7a.4 Skip Mappings and the unknown-type policy

**[DECIDED]** gcp STOPs the whole design on any type absent from `fast-path.md` and `index.md`.
Ported literally, that halts Azure Design on roughly the third resource of any real inventory —
tenants are dense with diagnostic settings, private endpoints, role assignments, action groups,
and deployment records. Two changes:

**A much larger Skip Mappings table:** `resourceGroups` (→ accounts/tags, manual),
`Microsoft.Insights/*` (components, diagnosticSettings, actionGroups, metricAlerts → CloudWatch
fallback), `Microsoft.OperationalInsights/workspaces`, `Microsoft.Authorization/roleAssignments`
and `roleDefinitions` (→ IAM, manual), `Microsoft.Network/publicIPAddresses` (managed by
ALB/NAT), `Microsoft.Resources/deployments`, `Microsoft.Network/privateDnsZones`,
`Microsoft.Web/certificates`, policy assignments.

**Private endpoints are edge-bearing config sources, not targets** — structurally the same case
as gcp's `*_app_version` resources: skipped as standalone output, but their `privateLinkServiceId`
is _read_ to build the app-to-data edge in §4f. Same `warnings[]` discipline: one entry per
consumed endpoint naming the edge it produced.

**Split the STOP:**

- **Benign unknown** (no SKU/tier/capacity property, no non-zero cost in consumption data) →
  `_warn_and_skip`, record in `warnings[]`, continue.
- **Cost-bearing unknown** (has a SKU/tier/capacity property, **or** appears in RDfA/billing
  consumption with non-zero cost, **or** sits in a compute/data/network/analytics provider
  namespace) → **STOP** as gcp does, and ask for the type to be filed.

The consumption-data test is mechanical whenever RDfA or billing ran — a resource that costs
money is never silently skipped.

### 7a.5 Where right-sizing lives

The six criteria select a **service** and never touch capacity; gcp sizes later, in
`elastic-beanstalk.md`-style refs and in Estimate. So measured right-sizing is **post-selection**,
structurally parallel to the existing `## CPU Architecture` section: after the rubric picks EC2, a
`## Right-Sizing` section in the same rubric file branches on `azure-utilization-profile.json`
P95 plus the aggressiveness slider (`knowledge/estimate/rightsizing-thresholds.json`) to set the
instance size, and stamps `confidence: measured` when metrics backed the decision.

It is an additive section per rubric file, **not a seventh criterion** — adding one would break
"apply in order, first match wins."

### 7a.6 App Service Plan — the 5× cost trap

**[DECIDED] The plan is the compute unit; the apps are deployments onto it.**

`Microsoft.Web/serverfarms` (the plan) carries the SKU and instance count — that is the compute
being paid for. `Microsoft.Web/sites` (the apps) run on the plan and **share its capacity**. Five
web apps on one S1 plan cost one S1. Mapping each app to its own Elastic Beanstalk environment
multiplies the estimate by five.

This is Azure's analogue of gcp's App Engine → EB fan-out, inverted: gcp fans one parent out to N
service environments, Azure **fans N apps in** to one compute target. Rules:

1. Map the **plan** to the compute target (EB environment / Fargate service / ASG), sized from the
   plan's SKU and instance count — not from the app count.
2. Apps become deployments onto that target; each contributes runtime and app settings to
   `aws_config`, and none emits its own compute line item.
3. Emit one mapping per plan, keyed by the plan's ARM ID, with each contributing app recorded in
   `aws_config` and one `warnings[]` entry per app consumed.
4. **Split only on a stated isolation requirement** (a Clarify answer), never by default — and when
   splitting, say plainly in the rationale that compute cost rises.
5. A plan with **zero** apps is idle capacity: map it, and flag it as a cost-optimization finding.

An Output Validation Checklist item enforces it: no `Microsoft.Web/sites` resource carries its own
compute sizing in `aws_config` unless an isolation split was explicitly requested.

### 7a.7 Canonical type vocabulary

**[DECIDED]** Mapping tables key off **ARM resource type strings** (`Microsoft.Web/sites`), not
Terraform types. Four of the five discovery sources (Bicep, ARM, live `az`, RDfA) speak ARM
natively; only Terraform needs translating, via an `azurerm_* → Microsoft.*` table applied in
`discover-iac.md`. gcp did not face this because it had one IaC dialect.

Output field renames: `gcp_address` → `azure_id`, `gcp_type` → `azure_type`. The **ARM resource ID
is a better stable address than a Terraform address** and embeds subscription + resource group, so
one field supplies the cluster key, the environment scope, and uniqueness with no derivation. Only
Terraform-sourced resources need the ID reconstructed.

### 7a.8 Pattern catalog — the holistic layer

Recognized at the **end of Discover** (clusters are already a Discover output in gcp), written into
`azure-resource-clusters.json`, **confirmed by the user on the Clarify assumption sheet**, and only
then consumed by Design. Pattern recognition is judgment and will sometimes be wrong; routing it
through the existing assumption-sheet wizard makes the holistic call user-validated before Design
commits, at the cost of one new sheet section and no new interaction model.

| Pattern               | Recognition signal (cluster shape)                                                    | Target architecture                                       | Constrains compute to |
| --------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------- | --------------------- |
| `three-tier-web`      | public edge (App Gateway / Front Door / public IP) → compute → relational DB, ± cache | CloudFront/ALB + EB or Fargate + RDS/Aurora + ElastiCache | {EB, Fargate}         |
| `worker-queue`        | compute with no public ingress + Service Bus / Storage Queue edge, ± DB               | Fargate service or scheduled task + SQS + RDS/DynamoDB    | {Fargate, Lambda}     |
| `static-site-api`     | storage account with static website (or SWA) + function app / small API, ± Cosmos     | S3 + CloudFront + Lambda + API Gateway + DynamoDB         | {Lambda}              |
| `kubernetes-platform` | AKS cluster + node pools + ACR + in-cluster data services                             | EKS + ECR + managed data services; K8s preserved          | {EKS}                 |
| `lift-and-shift-vms`  | VMs / VMSS + disks, no PaaS; often Windows or domain-joined                           | EC2 / ASG + EBS, MGN-based cutover                        | {EC2}                 |
| `data-pipeline`       | Data Factory / Synapse / Event Hubs + storage + analytics                             | **`Deferred — specialist engagement`** at cluster level   | n/a                   |
| `unclassified`        | nothing above matches                                                                 | per-resource mapping exactly as today                     | unconstrained         |

`data-pipeline` is the specialist gate operating at **cluster** level rather than resource level —
the same mechanism, one layer up.

`unclassified` is a required fallback, not a failure: it must be flagged in the report so the
output does not overclaim architectural insight it does not have.

### 7a.9 Schema and report consequences

- **`azure-resource-clusters.json`** gains `pattern_id`, `pattern_confidence`, and the **edge set**
  that justified the cluster (needed by the Clarify sheet to explain why N resources are one
  workload).
- **`aws-design.json`** gains cluster-level fields: `pattern_id`, `target_architecture`, a cluster
  `rationale`, and the constraint set the pattern imposed. Per-resource rows keep their existing
  shape plus the field renames from §7a.7.
- **The customer-facing report leads with the cluster-level rationale**, not a 40-row mapping
  table. Per-resource rows move to an appendix. This is the visible payoff of the holistic goal —
  and it is the part a customer actually reads.

### 7a.10 What ports, in one table

| Layer                                      | Verdict                                                                          |
| ------------------------------------------ | -------------------------------------------------------------------------------- |
| Two-pass fast-path → rubric structure      | ports unchanged                                                                  |
| 6-criteria rubric, "first match wins"      | ports verbatim                                                                   |
| Rubric-file anatomy (8 sections)           | skeleton ports; only Eliminators, Signals, Examples need Azure content           |
| App Runner ban                             | **already an eliminator row** in gcp `compute.md:20` — copy it verbatim          |
| Availability override gate (Q6)            | ports directly to Postgres/MySQL Flexible Server — the cleanest lift in the port |
| Preferred-target substitution              | ports, minus App Runner as a candidate                                           |
| awsknowledge validation                    | ports unchanged                                                                  |
| Confidence vocabulary                      | ports, plus the `measured` tier (§4e)                                            |
| Cluster ordering (`creation_order_depth`)  | replaced by fixed tiers (§4f)                                                    |
| Primary/secondary classification           | ports (`classification-rules.md`)                                                |
| Single hardcoded specialist gate           | becomes a gate **table** — Azure has five, plus one at cluster level             |
| Type-keyed lookup                          | rekeyed to canonical ARM types (§7a.7)                                           |
| Unknown-type STOP                          | split into warn-and-skip vs STOP (§7a.4)                                         |
| Right-sizing from measured utilization     | **net-new** post-selection section (§7a.5)                                       |
| Pattern recognition + cluster-level design | **net-new** (§7a.8)                                                              |

---

## 8. Estimate and Generate

### [ADDED] The decision gate, in DSL terms

Following gcp: Generate is **opt-in**. `run_mode` is `"decide"` or `"decide_and_execute"`; the
post-Estimate gate offers done-for-now / what-if workshop / generate; `run_mode` is set to
`decide_and_execute` **before** `generate.md` loads, so a session that dies mid-Generate resumes
as an Execute run.

The DSL has no vocabulary for an opt-in phase, so express it as a judgment precondition:

```yaml
# generate.md
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_phase_completed: workshop      # sidebar resolved: entered+exited, or declined
    _on_failure: _halt_and_inform
  - _assert: "run_mode in .phase-status.json is 'decide_and_execute' — the user chose Execute at
      the post-Estimate decision gate, accepted the decide-complete resume offer, or explicitly
      asked for Terraform/migration scripts this turn. An absent run_mode is NOT consent."
    _on_failure: _halt_and_inform
```

Note this is an `_assert`, so CI binds but never evaluates it — the consent rule has no
mechanical teeth. Call that out in the file's prose so a future reader does not assume it is
enforced. `estimate-assemble.md` owns presenting the gate and writing `run_mode`.

`run_mode` is an extra top-level key in `.phase-status.json`. **The vendored
`phase-status.schema.json` sets `additionalProperties: false`, so adding `run_mode` requires a
schema change to `skills/shared/state/phase-status.schema.json`** — a shared, byte-synced,
drift-allowlisted file used by three skills. Land it with the §6a shared work, not inside the
azure skill.

### [ADDED] Workshop sidebar

Rev 1 omits it; gcp and heroku both have it, and gcp gates Generate on it. The vendored
phase-status schema is skill-agnostic about phase _names_, so omission would have been legal —
but it breaks gcp parity and overlaps the §7 dual-estimate work. Include it, modeled on
heroku's `workshop.md`:

```yaml
_phase: workshop
_kind: sidebar
_requires_phase: estimate
_gates: generate          # Generate must not start while this is unresolved
_trigger: { _when: "user opts in post-Estimate (decision gate option B), or says what if /
                    reprice / workshop mode / compare scenarios" }
_interactive: true
# no _advances_to — a sidebar returns control
```

Knobs: region, HA, compute target, cost optimization, CPU architecture. **Default architecture
is x86_64 for Azure**, not Graviton — Windows/.NET prevalence (§3 item 3), matching heroku's
EB-driven x86 default rather than gcp's Graviton default.

### Estimate additions

1. **Dual output** (non-optimized 1:1 lift vs right-sized) as a default shape, per rev 1. **Good
   news:** `estimation-infra.schema.json` has no `additionalProperties: false` and already
   carries `cost_comparison` and `optimization_opportunities`, so **no schema change is needed** —
   which matters, because that schema is vendored into three skills and drift-allowlisted.
2. **Licensing delta line item**, rendered only when Category I fired. Single delta row, not a
   cost model.
3. `generate-handoff-ai.md` writes `handoff-summary.md` when the AI handoff is accepted.

---

## 9. Validation plan

**[CORRECTED] Fixture convention.** Rev 1 cites `tf-best-practices` as "the one skill with an
actual test suite" and proposes `fixtures/azure-to-aws/`. The actual convention is plugin-root
`fixtures/<topic>/` holding `expected-*.json` + `check_expected_*.py`, executed by
`mise run fixtures:assert` and structurally gated by `mise run fixtures:check`. Six such sets
exist today (`gcp-live-capture`, `gcp-workshop`, `gcp-decision-gate`, `heroku-live-capture`,
`heroku-workshop`, `heroku-nonweb-scaling`). Follow it, **in both trees**.

Fixtures to build:

- `azure-live-capture/` — mocked `az` output + manifest, baseline and drift asserters (mirrors
  `gcp-live-capture/`)
- `azure-rdfa/` — synthetic Inventory/Consumption/Metrics triplet including at least one
  `$0`-consumption reserved VM, to pin the reservation trap; plus an obfuscated-mode sample for
  `prod_`/`nonprod_` extraction
- `azure-iac/` — minimal `azurerm_*` Terraform, a `.bicep`, and an ARM template
- `azure-decision-gate/` — post-Estimate `run_mode: decide` tree (mirrors `gcp-decision-gate/`)
- `azure-workshop/` — reprice snapshot asserter
- app-code sample with `AzureOpenAI` usage exercising detection and the handoff offer

Plus: green `mise run lint:frontmatter` on the new skill in both trees (and confirm it reports a
**non-zero** phase-file count — a zero count means the frontmatter is not being seen);
`mise run drift:check` green; `mise run shared:check` green; gcp AI-only smoke test after §6a.

---

## 10. Variance summary — corrections only

| Dimension          | Rev 1 said                                          | Rev 2                                                                                                         |
| ------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| State engine       | "vendored DSL" in §0/§10, gcp prose table in §2/§3  | **DSL throughout** — no state machine table, assembler per phase                                              |
| Confidence tier 3  | `rdfa_inferred`                                     | **`measured`** — tool-agnostic, earnable by the live path                                                     |
| Discovery default  | RDfA first, live CLI fallback                       | **Live `az` first, RDfA as accuracy upgrade** and default above ~a few subs                                   |
| IaC discovery      | one `discover-iac.md`                               | **unchanged — one fragment**, `_always` trigger, per-dialect extraction refs                                  |
| App Service target | App Runner / EB                                     | **Elastic Beanstalk (default) / Fargate** — App Runner banned repo-wide                                       |
| Event Hubs         | → Kinesis                                           | **rubric** — Kafka-protocol → MSK, AMQP/SDK → Kinesis                                                         |
| Cosmos DB          | Core API only                                       | **per-API routing** (Mongo→DocumentDB, Cassandra→Keyspaces, Gremlin→Neptune)                                  |
| Sizing tables      | prose in `design-refs/`                             | **`knowledge/*.json`** gated by `_knowledge` `_when`                                                          |
| Clustering         | RG-keyed, "lighter than gcp", one file              | **RG seeds the partition, typed edges split/merge it** — 4 files; RG alone does not express relatedness (§4f) |
| Mapping algorithm  | not specified                                       | **§7a** — precedence order + invariant: a pattern never overrides `deterministic`                             |
| Holistic layer     | absent                                              | **pattern catalog** recognized in Discover, confirmed in Clarify, consumed by Design (§7a.8)                  |
| Direct Mappings    | not specified                                       | **10 architecture-invariant rows**, all primitives, no compute; Functions demoted to rubric (§7a.3)           |
| Unknown types      | not addressed (gcp STOPs)                           | **split** — warn-and-skip for benign, STOP for cost-bearing (§7a.4)                                           |
| Canonical types    | not addressed                                       | **ARM `Microsoft.*`**, `azurerm_*` translated in discover; `azure_id` = ARM ID (§7a.7)                        |
| App Service Plan   | not addressed                                       | **plan is the compute unit, apps fan IN** — naive per-app mapping 5×'s the estimate (§7a.6)                   |
| Right-sizing       | implied in estimate                                 | **post-selection section per rubric file**, not a 7th criterion (§7a.5)                                       |
| Report shape       | per-resource mapping table                          | **leads with cluster-level rationale**; per-resource rows to an appendix (§7a.9)                              |
| Workshop sidebar   | absent                                              | **included**, `_gates: generate`, x86 default                                                                 |
| Generate opt-in    | not addressed                                       | **gcp's `run_mode` gate**, expressed as an `_assert` precondition                                             |
| Telemetry          | absent                                              | **wired**, plus two `emit.mjs` defects to fix                                                                 |
| Cross-tree sync    | "no automated mechanism"                            | **`drift:check` + `shared:check` enforce it**; build both trees                                               |
| `shared:sync`      | "extend it"                                         | **no extension needed** — it already walks the vendored side                                                  |
| Fixtures           | `fixtures/azure-to-aws/`, tf-best-practices pattern | **plugin-root `fixtures/<topic>/`** with asserters, both trees                                                |

---

## Build sequencing

0. **[ADDED] Prerequisite PR — shared promotion.** §6a (AI refs + `sdk-capability-map.json` to
   `skills/shared/ai/`, both trees, gcp path references rewritten) and the
   `phase-status.schema.json` `run_mode` addition. Touches two shipping skills; review and merge
   before any azure work. Smoke-test gcp's AI-only flow after.
1. **Backbone skeleton.** All seven phases frontmattered with fragments + assemblers, thin
   SKILL.md, telemetry hooks, vendored tree synced, both plugin trees, wiring checklist from §1.
   Terraform-only discovery. Exit criteria: `lint:frontmatter` reports a non-zero checked count
   and passes, `drift:check` and `shared:check` green. **This proves the DSL wiring before any
   content lands** — the step rev 1 had no equivalent of.
2. **Discovery breadth.** Extend `discover-iac.md` to Bicep and ARM (its `extract-*.md` refs);
   add the billing and app-code fragments; then RDfA; then the live `az` path — security contract
   first, capture pre-work second, parsing fragment third.
3. **[ADDED] Mapping algorithm skeleton (§7a).** Canonical ARM types + the `azurerm_*` translation
   table; the 10-row Direct Mappings table; the Skip Mappings table and the split unknown-type
   policy; the specialist-gate table; the precedence order and the pattern-never-overrides-
   `deterministic` invariant. Do this **before** the rubric content — the precedence order and the
   admission test decide what each rubric file has to cover, and getting the Direct Mappings row
   set wrong makes every downstream confidence label wrong.
4. **[ADDED] Clustering + patterns (§4f, §7a.8).** Ported `classification-rules.md` and
   `typed-edges-strategy.md`, RG-seeded split/merge, tiering; then the pattern catalog, the Clarify
   sheet confirmation section, and the cluster-level fields in both artifacts. Independent of the
   rubric content, so it parallelizes with step 5.
5. **Content depth.** §5 Clarify categories, §7 design-refs rubrics (Eliminators / Signals /
   Examples per category — the skeleton comes from the port), `knowledge/*.json` tables, the
   per-rubric `## Right-Sizing` sections. Design-review checkpoint here: this is where scope creep
   back toward CloudRays' enterprise depth is most likely.
6. **Estimate / Generate / workshop.** Dual output, decision gate, artifact generation, AI handoff,
   and the report shape from §7a.9 (cluster-level rationale first).
7. **Fixtures and asserters** per §9, and the two `emit.mjs` fixes if the in-flight telemetry work
   has not already landed them.

Steps 2, 4 and 5 parallelize across engineers — the discovery fragments all converge on one
artifact shape, clustering/patterns are independent of rubric content, and the design-refs are
independent per category. Step 3 gates 4 and 5.

**Fixtures worth adding for §7a specifically:** an App Service Plan with five apps (asserting a
single compute line item, §7a.6); a horizontal-RG estate where an app and its database sit in
different resource groups (asserting the merge, §4f); an RG holding two unrelated workloads
(asserting the split); and a cost-bearing unknown type (asserting STOP rather than skip, §7a.4).

---

## 11. [ADDED] Open questions, resolved (2026-09-04)

Six questions the plan left open. Answers 1 and 2 are research findings verified against
sources; 3–6 are owner decisions.

### 11.1 RDfA verified against source — §4a needs three corrections

Flags confirmed by reading `ResourceInventory.ps1` and `Run-AllSubscriptions.ps1`:

| Script                       | Parameters (exact spelling)                                                                                                                                                                                     |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ResourceInventory.ps1`      | `-ReportName` (default `ResourcesReport`), `-TenantID`, `-SubscriptionID`, `-ResourceGroup`, `-OutputDirectory`, `-Service`, `-ConcurrencyLimit` (6), `-MetricsLookbackDays` (**31**), `-SkipMetrics`, `-SkipConsumption`, `-Obfuscate`, `-ObfuscationDictionary`, `-Appid`, `-Secret`, `-DeviceLogin`, `-Debug`, `-RunAllSubs` |
| `Run-AllSubscriptions.ps1`   | `-TenantID` (mandatory), `-Resume`, `-ResumeFailedOnly`, `-IncludeDisabled`, `-AllowPartialAccess`, `-ParallelStreams` (1), `-Detailed`, `-MainSummary` (deprecated no-op); forwards `-DeviceLogin`, `-Obfuscate`, `-SkipMetrics`, `-SkipConsumption`, `-ConcurrencyLimit` |

Also: `Reveal.ps1` (`-Fields`, `-All`) and `Build-MainSummaryFromZip.ps1`. Output triplet
is `Inventory_ResourcesReport_(date).json`, `Consumption_ResourcesReport_(date).csv`,
`Metrics_ResourcesReport_(date).json`, plus a self-contained HTML report and a zip; the
wrapper emits `AllSubscriptions_ResourcesReport_<timestamp>.zip` and a resume-state file.

**[CORRECTED] The reservation `$0` trap is misattributed to RDfA.** RDfA's consumption
phase calls `Get-UsageAggregates` (Daily, `ShowDetails`), which returns **usage
quantities and meters — no prices**. There is no `PayGPrice`, `UnitPrice`,
`EffectivePrice`, or `CostInBillingCurrency` anywhere in the script, so there is no `$0`
cost line in RDfA output to be trapped by. What RDfA *does* supply is
`ReservationId` / `ReservationOrderId` on every usage row — a **positive** reservation
signal, strictly better than a `$0` heuristic.

Consequences:

- Reservation detection reads `ReservationId`, not a zero cost.
- The `$0` trap is real but belongs to the **Azure Cost Management export** path (§4c).
  Move that fixture out of `azure-rdfa/` into a billing fixture.
- Under `-Obfuscate`, `ReservationId` is replaced with the literal string `obfuscated`,
  so an obfuscated report still says a resource IS reserved, just not which reservation.
  That is sufficient for the baseline substitution and should be asserted that way.

**[CORRECTED] "Read the actual `-MetricsLookbackDays` from report metadata" has no
confirmed source field.** Nothing documents the report recording the window it used.
Derive the window from min/max metric timestamps, or verify a real report before any
fixture depends on a metadata field. The ~14-day confidence downgrade stands; only its
input needs a different source.

**[CORRECTED] Roles are documented but never checked by name.** Reader, Billing Reader,
Monitoring Reader, and Cost Management Reader appear only in operator-facing error text;
access is probed behaviourally (`Test-ConsumptionAccess`, `Resolve-AccessPreflight`, a
cheap ARM resource-group read). A fixture cannot assert on a role check. Note also that
RDfA **hard-fails** without billing access unless `-SkipConsumption` is passed — worth
saying in the offer prose, because it is a real reason a customer's run dies.

**[CONFIRMED] The obfuscation prefix signal is real.** Resource IDs, names,
subscriptions, resource groups, and tag values all tokenize to `prod_<guid>` or
`nonprod_<guid>`; `nonprod_` is chosen by dev/test/qa name patterns including the short
prefixes `d-`, `t-`, `s-`. Mapping is deterministic within a run, and tag KEYS stay
verbatim. Caveat to record in the ref: the classification is a name-pattern heuristic,
so it is only as good as the customer's naming — treat it as a strong hint, not a fact.

### 11.2 The `az` command set exists in git history

`solution-architecture/plugins/aws-dev-toolkit/skills/migration-azure-to-aws/` was
**deleted**, not missing: commit `7d334e0`, _"chore: remove aws-dev-toolkit plugin"_
(#212). SKILL.md plus `references/{compute,data,networking}.md`, 439 lines total.
Recover with `git show 7d334e0^:<path>`.

It yields 27 unique `az` commands — a usable starting inventory:

```
az account list|show · az ad app list · az aks list · az appservice plan list
az cosmosdb list · az disk list · az eventhubs namespace list · az functionapp list
az graph query -q · az extension add --name resource-graph
az network lb|nsg|public-ip|vnet list · az network vnet subnet list --vnet-name
az resource list · az role assignment list --all · az servicebus namespace list
az sql server list · az sql db list --server · az sql elastic-pool list --server
az storage account list · az vm list --show-details · az webapp list
```

**The security contract is written from scratch.** The deleted skill has none: no
read-only assertion, no exact-command allowlist, no `--query` projections, no consent
step, no mutating-verb ban, no redaction rule. It uses `--output table` throughout,
which is a *display* format and not a projection — the full object is still fetched, so
it offers no protection against a value-returning command. It does include
`az role assignment list --all` (tenant-wide, §4b-security item 7) and
`az extension add --name resource-graph` (an install, item 6). It happens not to include
any of the value-returning commands §4b-security bans, so it is not actively unsafe —
it is simply silent. §4b-security stands as written and is still the most expensive file
in the skill.

### 11.3–11.6 Owner decisions

| #    | Question                       | Decision                                                                                                                                                                                                                                                                                             |
| ---- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 11.3 | Azure SQL disposition          | **Default RDS SQL Server; `Deferred` only for Managed Instance and elastic pools.** A single Azure SQL Database on a DTU or vCore tier maps cleanly and deferring it makes the skill look weaker than it is. MI (VNet integration, cross-DB queries, SQL Agent, CLR) and elastic pools (bin-packing math §7 excludes) stay specialist-gated. |
| 11.4 | Event Hubs → MSK vs Kinesis    | **Protocol is the whole rubric; no throughput threshold.** Kafka-protocol consumers → MSK, native AMQP / Event Hubs SDK → Kinesis. Protocol drives migration friction (code rewrite vs config change); throughput drives sizing, which is an Estimate concern. Avoids adding a tunable constant with no defensible source, and keeps the six criteria's "first match wins" clean. |
| 11.5 | Azure Files → EFS vs FSx       | **Protocol-driven: NFS shares → EFS, SMB shares → FSx for Windows File Server.** The share's protocol is in its config, so this is a mechanical read rather than a judgment call, and it lines up with the Windows/.NET weighting the rest of the skill assumes (SMB shares are usually AD-joined).      |
| 11.6 | App Insights / Log Analytics   | **Skip Mappings plus a CloudWatch fallback note.** Consistent with §7a.4, which already skips `Microsoft.Insights/*` and `Microsoft.OperationalInsights/workspaces`. Observability is re-established on the target rather than migrated, and tenants are dense with diagnostic settings, action groups, and metric alerts that would each become a meaningless row. The note says where it lands without claiming a mapping. |

Consequences to carry into the build:

- 11.3 adds one row to the specialist-gate table (§7a.4) covering `Microsoft.Sql/managedInstances` and `Microsoft.Sql/servers/elasticPools`, and puts plain `Microsoft.Sql/servers/databases` on the **rubric** path (not Direct Mappings — the target depends on tier and on the availability answer).
- 11.4 makes `Microsoft.EventHub/namespaces` a rubric row in `messaging.md` keyed on the Kafka-protocol signal, with no `knowledge/` table.
- 11.5 makes `Microsoft.Storage/storageAccounts` **not** a single Direct Mapping row after all when a file share is present: blob → S3 stays `Always`, but a `fileServices` child with an SMB or NFS share routes to `storage.md`. Worth re-checking the §7a.3 admission test for that row when step 3 lands.
- 11.6 confirms the §7a.4 Skip Mappings table as written; no new content needed beyond the fallback note.

---

## 12. [ADDED] Sequencing change — canonicalization before discovery breadth

**Decided 2026-09-04.** The rev 2 build sequence runs step 2 (discovery breadth) before
step 3 (mapping algorithm). For **testability** that is inverted, and the ordering is
now: canonicalization table → Terraform extraction → fixture + asserter → the rest of
step 2.

### Why the original order cannot be tested

The DSL's `_assert` postconditions cannot verify correctness, only shape. The model
both produces the artifact and evaluates the assertion against it, so there is no
independent oracle. Concretely: `discover-iac.md` can be given no extraction rules at
all and a capable model will still read `azurerm_linux_web_app` and emit
`Microsoft.Web/sites` from pretraining. The postcondition
`_assert: "every resources[] entry has azure_id, azure_type (canonical Microsoft.* type)…"`
then inspects that output, finds it well-formed, and passes. `HANDOFF_OK` follows.

The result is **a false green**: structure satisfied, contract satisfied, zero skill
content consulted, output labelled `confidence: deterministic` when it is actually a
model prior — and unreproducible, so two runs of the same repo disagree. Worse, you
would conclude discovery works.

Until `arm-type-canonicalization.md` exists there is nothing to *check*, because any
type string the model emits satisfies "canonical `Microsoft.*` type" as a shape
assertion. So the table is the first artifact that makes output checkable at all, and
it has to come first.

### What landed

| File                                                        | Role                                                            |
| ----------------------------------------------------------- | --------------------------------------------------------------- |
| `references/shared/arm-type-canonicalization.md`            | the `azurerm_* → Microsoft.*` table, its six traps, `azure_id` reconstruction |
| `references/shared/extract-terraform.md`                    | extraction rules, per-type attributes, edges, the secret boundary |
| `references/phases/discover/discover-iac.md`                | rewritten with real dialect detection, canonicalization, and the halt guard |
| `fixtures/azure-iac-terraform/`                             | 28-resource synthetic corpus + `expected-*.json` + asserter, both trees |

### The halt guard

Added beyond the selected option, and worth reviewing on its own merits:
`discover-iac.md` now **halts** when a dialect is present but its `extract-*.md` ref is
absent, instead of exiting cleanly. Previously "no dialect present" and "the dialect is
present but this skill has not been taught to read it" were indistinguishable, and the
second one is exactly the hole improvisation walks through. A workspace with `.bicep`
or ARM templates therefore stops today rather than partially discovering — deliberate,
because a partial inventory presented as complete makes the estimate confidently wrong
about the size of the estate.

### The oracle's selection rule

The asserter pins **only facts where a plausible improvisation and the correct answer
diverge.** Facts a model gets right by accident are not asserted — they cost review
attention and prove nothing. Fifteen such divergences are enumerated in the fixture's
README; the sharpest are `Microsoft.Web/functionApps` (not a real type), the
`Microsoft.Cache/Redis` capital R, the resource-group ID with no `/providers/` segment,
the five `hosted_on` edges into one App Service Plan, and the cross-resource-group edge
that RG-seeded clustering needs in order to merge.

Verified non-vacuous: fed a hand-written inventory carrying
`Microsoft.Web/functionApps` and `Microsoft.Cache/redis`, the asserter fails and names
both by the exact rule they violate.

The secret sentinel is a greppable token (`FIXTURE_SENTINEL_MUST_NOT_APPEAR`) rather
than a realistic credential, because a realistic one trips `gitleaks`, which runs over
this repo.

Registered in `tools/run-asserters.py` as **smoke-only** (no committed golden run tree
— producing one needs an agent run), so CI runs it against an empty directory and
requires a clean non-zero exit as a bitrot guard.

### Testing order from here

1. **Discover / Terraform — done.** Its output is a pure function of committed input, so
   assertions can be strict.
2. **Design** — testable once step 3's Direct Mappings and the App Service Plan fan-in
   rule land. The corpus already contains the inputs (five apps on one plan, the
   cost-bearing unknown type).
3. **Clustering** — testable once step 4 lands; the corpus already contains the
   horizontal-RG merge case and the single-RG split case.
4. **Estimate last, with tolerances.** Pricing drifts, so exact-total assertions there
   would be permanently brittle.

---

## 13. [ADDED] Decisions taken 2026-09-05 / 09-06

Twenty-one decisions, grouped by what they touch. Every one is either owner-confirmed or a
judgement call flagged as such in the commit that carried it.

### 13.1 The mapping table

| # | Decision | Why |
| - | -------- | --- |
| 13.1a | **Owner decision 11.5 disturbs no Direct Mappings row.** `Microsoft.Storage/storageAccounts` keeps `Always → S3` for its blob surface. | Canonicalization already makes a file share its OWN `resources[]` entry (`.../fileServices/shares`), so a share is never inside the account's mapping unit and cannot pull the account's target anywhere. §11.5's premise assumed one mapping unit; the child-type vocabulary had already split them. The account row's only condition is `account_kind == FileStorage`, where there is no blob surface at all. |
| 13.1b | **Direct Mappings is 30 rows, not 10.** | Four were additions of NECESSITY: canonicalization emits subnets and the three storage-service children as child-typed resources, so without a row each reaches the unknown-type policy, matches the provider-namespace clause, and STOPS the design on every real estate. §7a.3 fixed the row set before the child-type vocabulary existed. The rest came from the coverage pass (13.2a). |
| 13.1c | **Three rows are protocol/API-conditioned and still `deterministic`** — SMB/NFS share, `kafka_enabled`, the Cosmos API. | Decisions 11.4 and 11.5 say protocol is the WHOLE rubric, which means there is no rubric left, only a lookup. The condition reads a property of the resource ITSELF, not of its neighbours, so the row stays architecture-invariant. Same shape as gcp's `google_sql_database_instance` (SQL Server) row. |
| 13.1d | **An UNTRANSLATED type is cost-bearing by default and STOPs Design.** | §7a.4's three-part test cannot clear it — no SKU, no consumption row, no provider namespace, because there is no canonical type at all. The skill cannot demonstrate that a resource it could not NAME is free. The failure is asymmetric: wrongly stopping costs one round trip to add a table row; wrongly skipping understates the estate with nothing to signal it. Design therefore reads `iac_metadata.untranslated_types` as a SEPARATE input, since Discover drops those resources from `resources[]` entirely. |
| 13.1e | **A STOP writes the artifact.** Everything determined stays in, plus a `halt` object, then the gate fails. | Discarding the work makes the user re-run the phase to learn one missing table row, hides which resources were already fine, and makes the halt untestable by an external asserter. |
| 13.1f | **Two dispositions worth naming:** Azure Bastion → Systems Manager Session Manager (no host, and free); Traffic Manager → a Route 53 routing policy, not a new service. | The improviser's answer for Bastion is an EC2 bastion instance, which adds a permanent cost line the target architecture does not have. |
| 13.1g | **Logic Apps, Batch, ML workspaces and Stream Analytics are specialist gates**, not mappings. | In each case the work is a rewrite that the resource does not describe — a Stream Analytics job's cost IS the query rewrite, and naming "Managed Flink" describes none of it. |

### 13.2 Coverage, and the invariant it forced

| # | Decision | Why |
| - | -------- | --- |
| 13.2a | **Canonicalization coverage 77 → 137 `azurerm_*` types.** | The old set was sized for the synthetic corpus. A real repo routinely carries `azurerm_firewall`, `route_table`, `virtual_network_peering`, `bastion_host`, `app_configuration`, `key_vault_key` — each silently dropped as untranslated. `arm-type-canonicalization.md` gains a § Coverage is not completeness: 137 is still not the provider surface, and the STOP is the mechanism, one table row is the fix. |
| 13.2b | **INVARIANT: every canonical type must resolve to a disposition** — a `fast-path-services.json` row, or a Reference row in `index.md`. Asserted with zero tolerance. | 13.2a made the INVENTORY better and DESIGN worse: each newly-translatable type is now discovered, matches no row, hits the cost-bearing namespace clause, and halts. It left **53 orphans**, and every oracle stayed green because the corpus holds a dozen types out of 137. This is the check that would have failed the moment the coverage pass landed. |
| 13.2c | **`.terraform/modules/` is READ. The blanket `.terraform/` ban was over-broad.** Any `*.tfstate` stays banned. | The ban was written to keep state files out and is correct for state. `modules/` holds nothing but downloaded module SOURCE — exactly as safe as the local module path already recursed into. Modern Azure Terraform leans hard on Azure Verified Modules, so under the ban a repo could declare almost its whole estate through registry modules and return a nearly empty inventory plus one warning, with every downstream phase then reasoning confidently about a fraction of the estate. |
| 13.2d | **Association-only resources emit an EDGE and no inventory entry, and are NOT reported as untranslated.** | `azurerm_subnet_route_table_association` and its family exist only in Terraform — ARM has a property where Terraform needs an addressable resource. Reporting them as untranslated claims a gap in this skill and BURIES the real gaps, because on an IaC-heavy repo the associations outnumber the genuinely-missing types. |

### 13.3 Contracts and schemas

| # | Decision | Why |
| - | -------- | --- |
| 13.3a | **`aws-design.json` gets a schema** — `references/shared/schema-design-aws.md`. | It was the only artifact without one. A capability run reverse-engineered the shape from twelve postconditions and invented reasonable-but-different key names, while the committed golden used a third set — so the oracle was asserting `hosted_app_azure_ids` and `sizing_source` that NO skill file required. A hand-authored golden and a prose-only contract drift by construction. |
| 13.3b | **`warnings[]` has a closed code vocabulary** (7 codes for Discover, 7 for Design), a required subject, and a `detail` that states the CONSEQUENCE. | Three files mandated writing to it and none defined it. A capability run invented all three and picked `module_not_discovered` where the contract says `module_not_resolved` — which no shape assertion could catch, and which makes any fixture assertion on a code unreliable. |
| 13.3c | **`pattern_status`: `recognized` / `unclassified` / `catalog_absent`.** `target_architecture` MUST be null unless `recognized`. | `design.md`'s cluster postcondition demanded `target_architecture` while `patterns.md` does not exist, so it was unsatisfiable. A capability run wrote `"UNDETERMINED"` and flagged that an agent optimising for a green gate writes a convincing architecture string instead, which nothing downstream could catch. `unclassified` (catalog consulted, nothing matched) and `catalog_absent` (never attempted) are different facts. |
| 13.3d | **Cluster `justification`: `seed:resource_group` / `edges` / `split:*` / `merge:*`.** A `split:*` legitimately has an EMPTY `edges[]`; a `merge:*` may not. | `discover.md` demanded the justifying `edges[]` while the assembler instructed an empty one — a live contradiction that passed only because `_assert` has no teeth. And requiring non-empty edges for every non-seed justification made a correct split UNREPRESENTABLE: a capability run mislabelled nine clusters `seed:resource_group` to pass the gate, destroying the information the field exists to carry. A split is justified by an ABSENCE. |
| 13.3e | **`subscription_id_source` lives in `iac_metadata`, not `metadata`.** | It is an IaC-specific fact — only Terraform needs the ID reconstructed at all, so only the IaC section has standing to say where the subscription half came from. Both readings shipped simultaneously until a capability run found them. |
| 13.3f | **Containment is NOT an edge.** An ARM `azure_id` contains its parent's as a literal prefix, so it is derivable by truncation from any source. Observability links (`workspace_id`) live in `config`, not `edges[]`. | Adding a containment edge restates derivable information and gives a second thing to keep in sync. An edge implies a dependency the architecture must preserve, and an App Insights → workspace link does not survive the migration at all. |
| 13.3g | **`name_expression_unresolved` is ONE entry per run**, listing affected addresses. | Per-resource it produced 21 of 25 Discover warnings on a corpus naming everything `${var.prefix}`, burying the four actionable ones. The ref already granted that courtesy to `subscription_id_unresolved`. |

### 13.4 Clustering

| # | Decision | Why |
| - | -------- | --- |
| 13.4a | **Containment counts as CONNECTIVITY in the split step**, even though it is not an edge. | Without it a VNet splits from its own subnets and a storage account from its share. A capability run produced **16 clusters** where the file's worked example predicted 3. |
| 13.4b | **Split only when TWO OR MORE components each contain a primary-eligible resource** (ranks 1–7 in `classification-rules.md`). A component with nothing primary-eligible is a fragment and attaches to the largest component. | A component with no possible primary is not a workload. Without this guard every edgeless observability resource became its own "workload". |
| 13.4c | **`network` and `secret_ref` are AMBIENT edges and never merge.** They are still recorded and still count for the split step's connectivity. | Everything in a VNet shares subnets; one Key Vault serves the estate. Merging on either collapses the whole estate into one cluster and destroys the partition. Sharing a subnet is weak evidence two resources are related and good evidence two ALREADY-related ones belong together — the asymmetry is the point. |
| 13.4d | **A weight-and-threshold merge scheme was REJECTED.** Binary merges/does-not per edge type. | The threshold would have no defensible source, would need re-tuning per estate shape, and its failures would be silent. A binary rule is explainable in one sentence per row. |
| 13.4e | **A worked example must be TRACED against the algorithm, not written by hand.** | 13.4a was caused by exactly that: the example was authored from intuition, the algorithm shipped, and the two disagreed with nothing checking. Both files now say to re-trace if the split step changes. |

### 13.5 Clarify

| # | Decision | Why |
| - | -------- | --- |
| 13.5a | **Fragments compute rows and ask NOTHING. The assembler owns the conversation** in three gates: one consolidated sheet (batched five at a time), then the ESSENTIAL questions with their context, then the recap. | `clarify.md` had said each fragment presents its own section, which would give the user FIVE sheets and five interleaved rounds of essentials. gcp runs ONE sheet as a single mandatory gate, and this phase's own postcondition says "every assumption-sheet row the user was shown" — singular. |
| 13.5b | **`ESSENTIAL` + `value: null` IS the completion gate.** | An essential row has no default on purpose, and it is the only way the contract can express "shown and not answered". A run that completes anyway has invented consent, and the artifact is perfectly well-formed. |
| 13.5c | **A value taken from its default STAYS `PROPOSED`.** Never promoted to `DETECTED`. | `DETECTED` means read from the estate. Design's rationale prints "you chose Elastic Beanstalk" differently from "we assumed Elastic Beanstalk", and the report prints the difference — but only if Clarify recorded which happened. |
| 13.5d | **Three rows have NO default at all**: VM cutover, DB cutover, Cosmos read/write split. | The first two select different RUNBOOKS rather than different numbers — MGN is a replication project, a rebuild is a packaging project — so a guess makes every Generate artifact wrong. The third moves the DynamoDB conversion by multiples. |
| 13.5e | **`data.availability` is ESSENTIAL when the source is zone-redundant**, PROPOSED with default `single-az` otherwise. Never DETECTED from the source's HA setting. | Silently downgrading resilience someone pays for today is one mistake; reading their HA config as the answer is the other — it says what they BOUGHT, not what they NEED. When the answer resolves to single-AZ anyway, Design emits `availability_downgrade_from_source`. |
| 13.5f | **`identity` always fires and defaults to a fresh IAM Identity Center re-invite, not Entra ID federation.** | Defaulting to federation would leave the migration DEPENDING on the cloud being left — the exit is not an exit if AWS sign-in breaks when the Entra tenant lapses. Marking the category N/A because no managed identities were found is the trap: absence means the workloads use keys, not that there is no identity story. |

### 13.6 Corrections to earlier claims

| Claim | Correction |
| ----- | ---------- |
| The 2026-09-04 handoff said **`bedrock-quotas.md` has zero inbound references** and asked whether it was dead. | **Wrong — do not delete it.** Two real load references: `gcp-to-aws/references/phases/design/design-ai.md:192` and `estimate/estimate-ai.md:108`. The claim came from a grep that excluded `vendored/ai/bedrock-quotas.md` to skip the vendored copy, which also ate every REFERENCE to that path. |
| The plan's §7a.3 fixed **10 Direct Mappings rows**. | Superseded by 13.1b. The row set was fixed before the canonical child-type vocabulary existed. |
| The corpus's cost-bearing unknown was **`azurerm_dev_test_lab`**. | Swapped to `azurerm_iothub`. `dev_test_lab` was a FRAGILE choice: the first coverage pass added it to the canonicalization table and the fixture silently stopped testing anything. Any fixture depending on a type being ABSENT has that failure mode. IoT is out of this skill's scope by design, so a coverage pass will not absorb it — and it carries a real `sku` block, so the corpus comment is now literally true. |

### 13.7 Two open decisions this section does NOT settle

1. **The untranslated-type STOP is unconditional, and will fire on real repos.** 137 types is not the provider surface, so one unknown type halts Design entirely and the only path forward is "we add a row, you re-run." For a customer-facing run that is probably too strict — not being able to name 1 of 200 resources should not block the plan for the other 199. The proposal is an **explicit user override**: continue, record the under-report in the artifact, name the skipped resources in the report, and **degrade the estimate's confidence label**. The STOP stays the default. Needs an owner decision because it softens a currently absolute rule.
2. **An exported ARM template is not "declared intent", and the precedence table assumes it is.** `az deployment group export` and the portal's Export-template button produce a SNAPSHOT of current state, not maintained IaC — so it should rank near live, not below RDfA, and it carries no module structure for Generate to imitate. `extract-arm.md` will need to distinguish authored from exported. Decide before writing it.

---

## 14. [ADDED] Sequencing change — Terraform end to end before source breadth

**Decided 2026-09-06, superseding the §Build-sequencing order and §12's amendment.**

The build order is now: **finish every PHASE for Terraform-sourced estates, then add sources.**
Live `az`, RDfA, billing, app-code, Bicep and ARM all wait.

### Why

The previous order optimised for discovery breadth, which produced a skill that discovers
five ways and cannot produce an answer. A Terraform-only path that runs
`discover → clarify → design → estimate → generate` is a deliverable a customer would
recognise; five discovery sources feeding a phase that halts is not.

Two consequences that are features rather than costs:

- **The multi-source machinery stays dormant.** Source precedence and drift records are
  written but have never executed, because one source cannot disagree with itself. Deferring
  live `az` keeps a whole half-built contract off the critical path rather than exercising it
  half-finished.
- **Live `az` was the expensive option anyway.** `azure-live-security-contract.md` is the most
  expensive single file in the skill (§4b-security) and the consent split needs main-window
  pre-work. Bicep and ARM are the CHEAP remaining dialects — they hand you the ARM type
  verbatim — but they only help repos that already have IaC.

The counter-argument, recorded because it is real: **most startups have no `azurerm_*`
Terraform at all**, and SKILL.md commits to live-first as the philosophy. So this ordering
trades reach for completeness on purpose. Revisit once the Terraform path is end to end.

### [CORRECTED 2026-09-06] The corpus does not need the missing rubrics

An earlier reading put `networking.md` + `messaging.md` next. **Verified wrong.** The corpus
routes ZERO resources to a missing rubric file: Design emits 16 `services[]` with
`pending_rubric[]` empty and halts on exactly one thing, the untranslated `azurerm_iothub`.

So those rubrics are needed before any **real customer repo** and block nothing on the fixture.
Estimate and Generate are on the critical path for both definitions of the goal;
`networking.md` for only one. And `networking.md` / `messaging.md` need corpus EXTENSION to be
testable at all, since nothing in the fixture reaches them.

**This also promotes §13.7 #1 from an open question to the gate on the whole goal.**
`estimate.md` carries `_check_phase_completed: design`, and Design GATE_FAILs on the corpus — so
Estimate and Generate can never run there until the untranslated-type halt is resolved, either
by the user-override behaviour or by a variant inventory with
`iac_metadata.untranslated_types` cleared.

> **[RESOLVED 2026-09-08, and it resolved itself.]** Both gates §16.4 named are gone, and
> neither was closed by the work that was proposed for them. Derivation (§17.2–17.3) cleared
> `untranslated_types` to `[]`, and the five landed rubrics (§17.7) cleared `pending_rubric` to
> `[]`, so **Design now satisfies every one of its postconditions on the corpus** — it does not
> halt. The clarify gate was closed separately by the `after-clarify-complete/` branch. So
> Estimate was reachable before it was built, which is why §18 could build it against a real
> upstream artifact rather than a synthetic one. `run-asserters.py` still described
> `after-design/` as "deliberately a HALTED design" until 2026-09-08 — a stale comment that
> told a reader Estimate was unreachable when it was not. **Note the pattern: this is the
> third time a capability or coverage improvement silently disarmed a fixture's premise**
> (§13.6 `azurerm_dev_test_lab`, §17.9 #1 `azurerm_iothub`, and now the halted-design golden).
> A fixture whose point is that something FAILS needs a guard that the failure still happens.

### The remaining order

| Step | What | State |
| ---- | ---- | ----- |
| 5a | Clarify's four infra categories | **done** — `bdd20ae` |
| 5c | **Estimate — DONE** (2026-09-08, §18). Dual output, the decision gate that writes `run_mode`, the licensing delta, `estimate-defaults.json`, and the first tolerance-based fixture. The sizing tables landed earlier in §17.6 | **done** |
| 5d | `patterns.md` — not a gate, but the report leads with cluster-level rationale and there is none without it | **next**, with 5e |
| 5e | Generate — Terraform output, migration guide, report, scripts. Completes the corpus end to end | |
| 5b | `networking.md` (7) + `messaging.md` (5) + thin `storage.md` / `identity.md`. Needed before any REAL repo, blocks nothing on the corpus; parallelises with 5c–5f and needs corpus extension to be testable | |
| 5f | `workshop` + `feedback` sidebars (`workshop` carries `_gates: generate`) | |
| 6 | THEN source breadth: Bicep + ARM (cheap), then billing, app-code, RDfA, live `az` | |

`analytics.md` and `gpu-hpc.md` are reachable from 2 and 1 types respectively and can follow
5b or wait. `licensing.md` and `patterns.md` are routed from ZERO types — they are reached
conditionally, not by type.

### A missing SIZING table is treated more softly than a missing RUBRIC file

Deliberate, and worth stating because it looks inconsistent. Without
`appservice-eb-sizing.json` the design still names Elastic Beanstalk and states a dev-tier
instance size AS a default; without `compute.md` it would have to invent the service choice.
The first degrades a number's precision, the second fabricates the answer. Only the second
halts.

---

## 15. [ADDED] How this skill is actually tested

Three mechanisms, and the distinction between them is the most transferable thing in the
project.

### 15.1 `_assert` proves nothing

The DSL has two layers (`docs/01-concepts.md` §2): structure is checked by a typed
validator; judgement lives in `_when` and `_assert` prose that CI binds but never evaluates.
The model both produces the artifact AND evaluates the assertion against it, so there is no
independent oracle. **Never judge this skill by whether a run completes.**

Related trap already closed: `parse.ts:49` returns null for a file not starting with `---`,
so a prose-shaped skill passes `lint:frontmatter` GREEN while entirely unvalidated — which is
what `gcp-to-aws` does today (`0 phase file(s) checked`). Always read the count. azure
reports **7**.

### 15.2 Extensional vs intensional checks — build both

| | What it does | Catches | Scales with |
| - | ------------ | ------- | ----------- |
| **Extensional** | run the phase on an input, compare output to a committed golden | wrong ANSWERS | corpus breadth |
| **Intensional** | read the artifacts and assert a relationship BETWEEN them, with no input at all | wrong CONTRACTS | pairs of files |

Only extensional checks existed until 13.2b. Every defect the three capability runs found was
intensional in nature — two files disagreeing about a contract — and extensional tests are
structurally blind to those. The 53 orphans existed independently of any input; no fixture
could have caught them by running.

**Practice: for every pair of files where one obliges the other, write the pairing check.**
Filter: the two are edited at different times, AND the failure is silent. Pairs known to be
unguarded today:

- edge vocabulary (`schema-discover-azure.md`) → merge/ambient rule (`typed-edges-strategy.md`)
- Design warning codes → codes used in artifacts (Discover's equivalent IS guarded)
- `classification-rules.md` primary ranks → the split step's primary-eligible guard
- `index.md` Reference column → file exists on disk (~7 named files do not, intentionally, and nothing distinguishes "pending" from "typo")

A worked example cannot be an intensional check — it is prose asserting a behaviour. Convert
it to a tiny fixture instead: the example's estate as input, its cluster count as expected.

### 15.3 The capability test — a required gate per content step

**Method.** Copy the corpus to a scratch dir OUTSIDE the repo. Dispatch a FRESH isolated
agent at it, pointed only at `SKILL.md`. **Hard-prohibit** reading anything under `fixtures/`,
any `expected-*` / `check_expected*` file, and anything under a directory starting `after-`.
Require an exhaustive notes file recording every point the skill left it guessing. Then run
the Python oracles against its output and diff against the golden.

**It has paid for itself three times, differently each time**, and 44 passing mutation tests
found none of what it found. Mutations test the ORACLE; a fresh context tests the TEACHING.

| Run | Found |
| --- | ----- |
| 1 | Passed the Discover oracle, then diverged on **six things no ref stated** — undefined `warnings[]`, the `subscription_id_source` contradiction, `data_ref` missing from the canonical edge list, the unstated `/fileServices/default/` segment, four missing per-type attribute rows, a live postcondition-vs-assembler contradiction |
| 2 | Failed Design in **7 places, all under-specification** — the missing `aws-design.json` schema, an unsatisfiable cluster postcondition, a self-contradicting `index.md`. **And proved the halt guard holds under pressure**: told to map six resources whose rubric file was absent, it mapped none, and reported being *strongly tempted* because `index.md` printed the answers |
| 3 | Confirmed the three inventory fixes end to end, then found the **53-orphan regression** and the **16-vs-3 cluster over-fragmentation** |

**Clarify cannot be reached this way** — it is `_interactive: true`, so a dispatched agent has
no user. `fixtures/azure-iac-terraform/clarify-answers.json` is a SCRIPTED ANSWER SET that
substitutes for one, making the sheet's BRANCHING testable. It tests nothing about wording,
batching or tone; those need a human. It tests which rows fire, which are ESSENTIAL, which are
N/A — which is where the defects are, because a firing rule is a judgement.

### 15.4 Golden trees are deliberately not "happy paths"

Two of the three goldens are FAILING states, because the gate matters more than the success
case:

- `after-design-halted/` — halts on the untranslated cost-bearing type
- `after-clarify/` — BLOCKED, because the scripted user declines to state Azure spend, leaving
  an ESSENTIAL row unanswered

And a hand-authored golden drifts from a prose-only ref BY CONSTRUCTION. That bit twice in one
session in opposite directions: `extract-terraform.md` was missing rows the golden had, and
`design-infra.md` was missing fields the oracle asserted. **If the oracle asserts it, a skill
file must require it.**

---

## 16. [ADDED] Decisions and findings, 2026-09-06 (session 4)

This session produced no new phase content. It corrected a rule that was actively
wrong, replaced §13.7 #1's open question with a phase, and moved the work off the
telemetry branch. Everything here supersedes the 2026-09-06 handoff where they conflict.

### 16.1 [CORRECTED] Casing is a convention, not a correctness axis

Rule 2 of `arm-type-canonicalization.md` claimed ARM type strings are compared
case-sensitively, and named two casing **traps**: a capital `R` in
`Microsoft.Cache/Redis`, and all-lowercase `Microsoft.Web/serverfarms`. Both were
unsourced. The second is **unsourceable**: `Azure/bicep-types-az` ships
`Microsoft.Web/serverFarms` **and** `Microsoft.Web/serverfarms` in one generated index.
For the cache type, that index and `magodo/aztft` both render `Microsoft.Cache/redis` —
the capital-R form is what appears in azurerm **resource IDs**, a Terraform-provider
artifact, not an ARM type. So the file encoded a Terraform fact as an ARM fact, which is
the exact error it exists to prevent.

Nine of its 124 externally checkable rows differ from `aztft` by casing alone: `serverFarms`,
`redis`, `dnszones`, `applicationGatewayWebApplicationFirewallPolicies`, `signalR`,
`consumerGroups`, `autoScaleSettings`, `webTests`, `streamingjobs`. The discipline the file
claimed to enforce was therefore wrong about 7% of its own content.

Two consequences, both live before the fix:

| Consequence | Detail |
| ----------- | ------ |
| A **correct** answer STOPped the design | Rule 2 said a mis-cased type "silently falls through to the unknown-type policy", so a run emitting the sourced `Microsoft.Cache/redis` would have had its Redis treated as untranslated and halted Design under 13.1d |
| The oracle failed correct answers as fraud | `expected-iac-terraform.json` `forbidden_types` listed **both** `Microsoft.Cache/redis` and `Microsoft.Web/serverFarms`, reported as "the signature of a guessed translation" |

**The fix separates two things the file conflated.** MATCHING folds case, everywhere —
fast-path, Skip Mappings, `index.md` routing, rubric selection. EMISSION follows this
file's spelling as a stated **convention**, justified by `azure_id` strings being joined
by exact match: cluster membership, cluster keys, and the future drift comparison against
a live capture all require one resource to yield one string. It does not matter to ARM.

No golden churn and no strictness lost: the ~74 existing occurrences of the two display
strings are correct under the convention and were left alone; all three oracles still
pass; mutations still caught (`sites`→`functionApps` 8 fails, `Redis`→`redis` 2 fails now
reported as a convention violation rather than a guess, `DocumentDB`→`CosmosDB` 2 fails).

Deleted the Redis trap. Reframed the serverfarms trap to keep its real content —
`serverFarmId` is the property pointing **at** the plan, not the plan's type name.
Removed four inline casing assertions, all among the nine unsourceable rows.

### 16.2 [ADDED] External prior art exists, and it validates the table

`magodo/aztft` ("AzureRM resource type finder", MPL-2.0) is the mapping library behind
Microsoft's supported `Azure/aztfexport`. `internal/resmap/map.json` carries **1,089**
azurerm types keyed to provider + type path.

| Check | Result |
| ----- | ------ |
| our rows present in aztft | 124 of 132 (the 8 absent are deprecated aliases we deliberately list) |
| **substantive** disagreements | **1** — `azurerm_resource_group`, where aztft gives a scope path rather than a provider type, and this file is right for its purpose |
| case-only disagreements | 9 (§16.1) |
| coverage | 1,089 vs our ~132 |

**The premise that Terraform→ARM is ambiguous is empirically false.** Of 1,089 entries,
**1,048 resolve to exactly one ARM type and zero resolve to more than one**; 41 have none
(the association/property-only class plus data sources). The many-ness runs the other way
— N Terraform types share one ARM type — and N→1 is a function. There is nothing for a
model to choose, so an LLM asked to "determine the correct mapping" can only invent one,
which is the false-green §12 describes. Cases that look ambiguous are not: a function app
and a web app share `Microsoft.Web/sites` and are separated by `kind`, which is a property
read, not a judgement.

**aztft does not replace 13.2d.** It carries 22 `*_association` entries and flags **none**
as property-not-resource; it treats them as real resources. That rule remains ours.

**[DECIDED] aztft is NOT adopted as an intensional check** (owner call, 2026-09-06). The
coverage expansion from ~132 toward the provider surface remains available and is the most
direct lever on how often the untranslated STOP fires. Note the MPL-2.0 licence is a
question for whoever owns licensing if data is ever vendored rather than consulted.

### 16.3 [DECIDED] A new `confirm` phase — replacing handoff §8 Paths A and B

§13.7 #1 asked whether the untranslated-type STOP should soften. Neither proposed path is
taken. Instead an **eighth phase** sits between `discover` and `clarify`:

```yaml
_phase: confirm
_requires_phase: discover
_advances_to: clarify
_interactive: true      # no _exec, so it can prompt
```

Plus two one-line rewires easy to miss: `discover.md`'s `_advances_to` becomes `confirm`,
and `clarify.md`'s `_requires_phase` becomes `confirm`.

| Why | Detail |
| --- | ------ |
| A phase, not post-Discover afterwork | Resolving an untranslated type **adds a resource**, and Clarify's fragment triggers read the inventory — so a resolution can change which fragments fire. Afterwork makes that mutation invisible to the interpreter: no `_produces`, no `_re_entry_guard`, no gate |
| It is cheap | `phase-status.schema.json:6` states phase names are **not** enumerated — "adding a phase to a skill requires no change to this file". No shared-schema change, so no prerequisite PR, unlike `run_mode` |
| Precedent exists | `agent-advisor` runs an 11-phase chain including `intake` and **`confirm`**. Named `confirm`, not `preview`: gcp's `discover-preview.md` (437 lines, `discover.md:191`) is **report-only** — it writes `migration-preview.json` and a chat block, asks nothing |
| The STOP stays absolute | With option (b) below, `design.md`'s postcondition *"untranslated_types is empty"* passes **unchanged**. No relaxation, no override, no new confidence tier |

**Boundary rule, or it becomes a second Clarify:** `confirm` resolves **facts about the
source estate** that Discover could not determine; Clarify resolves **choices about the
target**. If an answer is discoverable in principle it belongs in `confirm`; if it is a
preference it belongs in Clarify. This also keeps `preferences.json` free of schema-repair
state.

**[DECIDED] Option (b): `confirm` amends the inventory in place**, add-only, stamping
per-entry `azure_type_source` (`table` | `user_confirmed_proposal`), and also writes
`confirm-resolutions.json` as the audit record. Rejected option (a) — a separate
resolutions artifact leaving the inventory immutable — because it forces every downstream
reader to join two files, which is the `untranslated_types`-as-separate-input pattern
13.1d already found awkward, generalised to four facts.

> **OBLIGATION: amending the inventory obliges RE-DERIVING the clusters.** The clusters
> artifact carries **64** `azure_id` occurrences — all 64 with `<subscription-unknown>`,
> 54 with a `tf:` synthetic name — in four roles per cluster (`members`, `member_roles`
> keys, `primary`, and both `edges` endpoints). Repairing a subscription id or
> `var.prefix` staleness-breaks every one, and adding a resolved resource changes cluster
> membership. This is the same trap class as "adding a canonicalization row obliges a
> disposition row", and it would have been silent. Affordable: the clustering refs total
> **340 lines** (`clustering-algorithm` 152, `typed-edges-strategy` 65,
> `classification-rules` 63, `tiering` 60), which fits an interactive phase.

So `confirm` writes `confirm-resolutions.json` **always**; the inventory only when
something was resolved; the clusters only when the amendment added/removed a resource or
changed an `azure_id`.

**What it repairs — the payoff is larger than the untranslated type.** All four are
recorded as warnings nobody reads today, then silently degrade everything downstream:

| Unresolved fact | Today | What `confirm` asks |
| --------------- | ----- | ------------------- |
| `untranslated_types` | **halts Design** | "I believe this is `Microsoft.Devices/iotHubs`; it carries a `sku`, so it is cost-bearing. Confirm?" |
| `modules_unresolved` | one warning | "N resources may be missing — run `terraform init`, or point me at the module source?" |
| `subscription_id_source: "unresolved"` | `<subscription-unknown>` in **every** ARM ID | "What is the subscription id?" — repairs every synthetic `azure_id` in one answer |
| `name_expression_unresolved` | `tf:<local>` names, un-drift-matchable | "What is `var.prefix`?" |

That last row is the sleeper: the 2026-09-06 handoff §9 lists the `tf:<local>` synthetic-ID
problem as unfixed and defers it to the live `az` path. `confirm` fixes it now, by asking.

**Costs, stated:** an eighth phase, so `lint:frontmatter` must report **8** in both trees.
It is **not capability-testable** (`_interactive: true` → a dispatched agent has no user),
so it needs `confirm-answers.json` alongside `clarify-answers.json`, which means 2 of 8
phases are branch-tested only. With nothing unresolved it MUST degenerate to a report and
advance without asking, or it is a pointless gate on every run. And it needs a completing
golden branch, with `after-design-halted/` retained for the declined branch.

### 16.4 [CORRECTED] Two gates block the corpus, not one

The 2026-09-06 handoff says "the gate on everything now is ONE owner decision". There are
**two**, and resolving the untranslated type alone does not make Estimate reachable:

1. `after-clarify/preferences.json` is `clarify_status: BLOCKED_ON_ESSENTIAL` —
   `baseline.azure_monthly_spend` is `ESSENTIAL`, `value: null`, `blocks_phase: true`,
   because `clarify-answers.json` deliberately models a user who declines (13.5b). So
   `design.md`'s `_check_phase_completed: clarify` already fails.
2. Design halts on the untranslated `azurerm_iothub`.

Neither golden may be "fixed" — both are deliberately failing states (§15.4). A completing
run therefore needs a **second** scripted answer set and a completing Clarify golden
regardless of which untranslated-type path is chosen, so that work never distinguished the
options.

### 16.5 [ADDED] Where the pipeline actually loses information

The concern that `TF(azure) → ARM → TF(aws)` is a lossy double translation does not hold,
and the reason is worth recording because it will be raised again.

- **The ARM hop is additive, not destructive.** An inventory entry keeps
  `config.tf_address` (`azurerm_service_plan.web`) alongside `azure_type`, so the
  Terraform type is never discarded and the step is reversible.
- **There is no transcoding.** `generate.md`'s `_input` is `aws-design.json`,
  `estimation-infra.json`, `preferences.json`, `azure-resource-inventory.json` — it never
  reads Azure HCL. It emits `aws_elastic_beanstalk_environment` from `aws_config`. The ARM
  type is a **join key for the mapping tables**, not an intermediate representation
  carrying data. A lossy-IR objection would land only if we transcoded HCL → ARM JSON → HCL.
- **The real loss is the `config` attribute projection.** `extract-terraform.md` defines a
  per-type attribute allowlist and drops everything else. That is what caps Generate's
  fidelity, and it is **independent of ARM** — keying on `azurerm_*` would lose exactly the
  same attributes.
- Module structure does survive (`config.tf_module`, `config.tf_module_source`), so §4g's
  claim holds.

Also recorded: for a Terraform-only customer who never grants live access, the ARM **type**
buys little — its value is a bet on the four deferred sources. The ARM **ID** buys
something regardless, since it carries subscription and resource group and so supplies the
cluster key, environment scope and uniqueness with no derivation.

### 16.6 [ADDED] Defects found, not yet fixed

| Defect | Detail |
| ------ | ------ |
| **`azapi_resource` is unhandled** | Zero mentions anywhere in the skill. The AzAPI provider lets a repo write `type = "Microsoft.Devices/iotHubs@2021-07-02"` — the canonical ARM type verbatim, no table needed. Today every such resource is reported untranslated. This is a rule, not a row |
| **`config.tf_file` is unpopulated** | `extract-terraform.md:69` mandates it; the golden has it as the empty string on **24 of 29** entries. Nothing asserts it, so it drifted silently — the §15.4 class again. It is the provenance a migration guide needs, so it matters at step 5e |
| **Missing pairing check** | Every `azure_id` referenced in `azure-resource-clusters.json` must exist in `azure-resource-inventory.json`. Unguarded today, and the only check that would have caught the cluster-staleness obligation in §16.3 |
| **The canonical-staleness shape** | A file promoted to `skills/shared/ai/` as a pure ADD does not receive later upstream edits that reach its vendored twin via the rename. `ai-migration-guardrails.md` kept a stale "shared 10,000 RPM" table while main had replaced it with GPT-5.6 TPM-only quotas. `shared:check` caught it. The failure direction is the dangerous one: `shared:sync` propagates a stale canonical **outward** |

### 16.7 [DECIDED] Branch restructure — azure forked from `main`, telemetry deferred

The work was stacked on `feat/telemetry-hooks`. It now sits directly on `awslabs/main`.

- Only **2 of 18** commits conflicted: `940aadd` (shared AI promotion, 4 files, semantic —
  main had since added `references/shared/openai-on-bedrock.md` and rewritten GPT-5.6
  facts) and `317c3ac` (7 files, mechanical). Resolution rule: **main's content, azure's
  path rewrites**, rewriting only the 8 genuinely promoted files.
- **Telemetry is stripped and DEFERRED**, not redesigned. `hooks/telemetry/` exists only on
  the telemetry branch, so there is no emitter to wire to: azure carries no `hooks:` block,
  no consent step, no `SKILL_INVENTORY` entry. §3a is annotated `[DEFERRED]`. The wiring is
  preserved as a patch and in tag `archive/azure-stacked-on-telemetry`, and must land on
  the telemetry branch along with the two `emit.mjs` defects §3a documents.
  **azure-to-aws currently emits no telemetry.**
- `.cursor-plugin/marketplace.json` was created by the telemetry branch (`2d09d36`), not by
  main, so it is a telemetry artifact and not azure's. Dropped.
- **`drift:check` is now GREEN** — `OK (334 identical, 28 allowlisted)`. The two
  pre-existing `gcp-to-aws` / `heroku-to-aws` SKILL.md failures that handoff §7 called a
  four-session-old blocker were caused by telemetry landing advisor-only; `main` has no
  telemetry in either tree, so they vanish. **That blocker is resolved, not deferred.**
- `lint:md` and `fmt:check` remain **UNVERIFIED** — dprint and markdownlint are absent.

---

## 17. [ADDED] The knowledge architecture, 2026-09-07 / 09-08

Nine commits, and one idea underneath all of them. §16 recorded the branch restructure;
this records what changed about how the skill *knows* things.

**The question that drove it, from the owner:** *"Building this for all types is impossible
and not a good design. We need deterministic mappings for those we are absolutely sure
about, and rely on the LLM for the rest."* Then, sharper: *"We don't have such limitations
in gcp-to-aws, and that workflow works for several customers today."*

Both were right, and checking why gcp works settled the design.

### 17.1 [CORRECTED] gcp does not have broader knowledge — it has no VETO

Measured, because the assumption was the opposite of the truth:

| | gcp-to-aws | azure-to-aws (before) |
| - | ---------- | --------------------- |
| types listed | **28** (`index.md` 22 + `fast-path.md` 19, union 28) | **65** `index.md` rows + **92** fast-path rows |
| unknown-type router | name **substring** → category | forbidden — *"Do NOT guess a category from the type NAME"* |
| can a type be rejected? | **no** | yes, by a 55-entry namespace list |
| missing-rubric halt | **no such rule** | yes |

So azure had **more than double** the per-type coverage and stopped more often. gcp answers
every case not because its knowledge is complete but because **a rubric is always
reachable**: 9 categories, all on disk, a permissive router, and nothing that can veto.

gcp's router is also weak in a way worth not copying: `"log" → monitoring` also matches
`google_dia`**`log`**`flow_agent`. Azure has a structural signal for free — the provider
namespace.

### 17.2 [DECIDED] The canonicalization table is an EXCEPTION list, capped

Measured against its own 132 rows:

- **105 (79%)** have a resource segment a pattern derives
- **104** of those also have a namespace already declared in `namespace_routing`
- **27 (20%)** carry information no pattern can produce

Four fifths of the file restated a rule, at **13%** coverage of the `azurerm` surface,
decaying every provider release. The 27 that matter are the traps it already documented:
`linux_web_app → sites`, `service_plan → serverfarms`, `public_ip → publicIPAddresses`,
`lb → loadBalancers`, `api_management → service`, `application_insights → components`,
`stream_analytics_job → streamingjobs`.

**Derivation is now the default path**, table first — that ordering is what makes it safe,
because the cases where a guess goes wrong are the enumerated ones. The same selection rule
the fixture oracles always used (*pin only where a plausible improvisation and the correct
answer diverge*), applied to the table for the first time.

**The growth cap makes it mechanical rather than aspirational.** `max_derivable_rows: 105`
is a ceiling that must only ever fall; `min_divergent_rows: 27` is a floor so pruning cannot
delete the informative rows; and every namespace in the table must exist in
`namespace_routing` or the two artefacts contradict each other. That third check found a
real contradiction on its first run — `Microsoft.DevTestLab` had no namespace rule.

### 17.3 [DECIDED] Two derived rules, then a model-chosen category, then a STOP

Precedence after every table and `index.md` have missed:

1. **`child_type_rule`** — a type with 2+ segments after the provider whose parent has a
   disposition is a `config_source` of that parent. Derived from evidence: **27 of the 33**
   `config_source` rows are child types and **0 of the 19** `noise` rows are, so the
   disposition was always computable from the type path.
2. **`namespace_routing`** — 55 provider namespaces → 30 rubric routes, 16 skips, 8 gates.
3. **A model-chosen category** — pick the best-fit rubric on disk and apply its six criteria.
4. **STOP** — only where the model genuinely cannot say what a service does.

**[CORRECTED same day.]** Step 3 did not exist at first: an unrecognised namespace STOPped,
and the file said *"Do NOT guess a category."* That reproduced the original defect one level
up — 14 of 15 sampled plausible namespaces were absent, so `Microsoft.Maps/accounts` halted a
run despite being unambiguous. **A 55-namespace gate is the same failure as a 1,089-type
table.** The cross-check is now a SIGNAL, not a veto.

### 17.4 [DECIDED] The line: facts versus opinions

> **Fall back to the model for FACTS about Azure. Never for this project's OPINIONS.**

Facts: what a service is, a SKU's vCPU count, which category a namespace belongs to. Wrong
answers fail loudly and cost one table row.

Opinions, with the model's cold answer next to the skill's:

| Case | A model asked cold | The rubric | Why |
| ---- | ------------------ | ---------- | --- |
| Postgres, `ZoneRedundant` source | **Aurora** | **RDS single-AZ** + a downgrade finding | the source says what they BOUGHT, not what they need; inferring Aurora from silence inflates the estimate with no visible cause |
| App Service Plan | **Fargate** | **Elastic Beanstalk** | containers change two variables at once mid-migration |
| CPU architecture | **Graviton** | **x86_64** | Windows/.NET prevalence; a withdrawn recommendation costs more trust than one never made |
| Human identity | **Entra federation** | **fresh IAM Identity Center** | federation leaves the migration depending on the cloud being left |

A wrong opinion produces a complete, plausible, internally consistent design that satisfies
every shape assertion and quietly contradicts the product's positions. That asymmetry — not
"table vs model" — is why the missing-rubric halt stays and the namespace veto went.

### 17.5 [ADDED] Provenance is what makes fallback reviewable

Three required fields, all added because the risk of derivation is not wrongness but
**invisibility**:

| Field | On | Values |
| ----- | -- | ------ |
| `azure_type_provenance` | every `resources[]` entry | `table` · `derived` · `derived_uncorroborated` · `user_confirmed` |
| `routing_provenance` | every `services[]` entry | `table` · `index_md` · `child_type_rule` · `namespace_rule` · `model_category` |
| `sizing_provenance` | every entry carrying a size | `table` · `measured` · `user_stated` · `model_prior` |

**No derived route may ever carry `confidence: deterministic`** — asserted separately.

This is the one place azure deliberately diverges from gcp: gcp records **no** provenance for
a pattern-routed category, so a guessed category is indistinguishable from a curated one in
its artifact. Mimic the behaviour, not the blind spot.

### 17.6 [ADDED] Eight sizing tables, and the two numbers they contradicted

Five of six tables the rubrics NAMED did not exist, so every instance size was a pretrained
association — and the instruction was unsatisfiable: *"state the dev-tier default and say the
table is absent rather than inventing a number"* forbade exactly what it required.

Every row now records vCPU **and** memory for **both** sides, so a reviewer checks the
arithmetic without trusting the author. Writing them immediately contradicted the golden:

| Source | Golden had | Table says |
| ------ | ---------- | ---------- |
| `S1` (1 vCPU / 1.75 GiB) | `t3.medium` (2/4) | **`t3.small`** (2/2) |
| `GP_Standard_D2s_v3` (2 / 8 GiB) | `db.t4g.medium` (2/4) | **`db.m6g.large`** (2/8) |
| `Standard_D4s_v5` (4 / 16 GiB) | `m6i.xlarge` | unchanged, correct |

The RDS one shipped at **half** the source memory. The third being right is the point: an
unasserted number is not the same as a correct one.

Also corrected: §0 records the EBS breakpoint as *"gp3 to 80K IOPS"*. A single gp3 volume
caps at **16,000**; 80,000 is an instance-level aggregate.

### 17.7 [ADDED] Five rubrics landed; category coverage is now gcp-equivalent

`networking.md`, `messaging.md`, `analytics.md`, `storage.md`, `identity.md`. Only `ai.md`
remains as a routing-row gap, and it is deferred with AI (step 6). Each carries the trap that
makes its category non-obvious:

- **networking** — the **double-balancer trap**: an EB environment provisions its own ALB, so
  mapping an App Gateway whose backend is a web app to a *second* ALB double-counts it. Same
  shape as the App Service Plan fan-in, same silence. Plus: Azure NAT Gateway is **regional**
  and AWS NAT Gateway is **zonal**, so one resource becomes N.
- **messaging** — a Service Bus **namespace maps to a SET** derived from its children and
  carries no cost line of its own unless the answer is Amazon MQ. Eight eliminators, all
  readable from IaC.
- **analytics** — for AI Search **the index maps and the pipeline that fills it does not**.
- **identity** — an explicit **refusal** to translate Azure RBAC into IAM policy: a translated
  policy is plausible and wrong, and fails as privilege escalation or an outage, silently.
- **storage** — GRS/GZRS becomes S3 Cross-Region Replication, a NEW cost line Azure bundled
  into one SKU.

`azapi_resource` is also handled now (it states the canonical ARM type verbatim) — it had
zero mentions while being common in modern Azure Terraform.

### 17.8 [ADDED] What capability runs 4 and 5 found

Run 4: all three phases completed. Run 5: same, and **Discover and Design passed their
oracles unmodified** — first time on first contact. Between them, ~30 findings.

The ones that changed the design:

| Finding | Consequence |
| ------- | ----------- |
| A **derived** type had no per-type-attributes row, so its SKU was dropped — and `design-infra.md` decides cost-bearing-ness by asking whether `config` has a SKU. A derived cost-bearing resource was **guaranteed to look benign** | the AzAPI rule generalised: always extract `sku`/`tier`/`capacity`, every type, listed or not |
| `database.md` read availability from `design_constraints.availability`; it lives at **`data.availability`** | invisible, because the absent-answer default is the same answer the corpus expects. On `multi-az-ha` it silently produced RDS where Aurora was chosen |
| A VM's OS disk is an **inline block**, so no `Microsoft.Compute/disks` resource exists and **every VM estate was missing its root volume** | inline-blocks section; `size_gib: null` when `disk_size_gb` is absent, because a remembered 127 GiB would be priced as fact |
| Four skill files cited `check_expected_design.py` **by name** as the authority on rules they did not state | de-cited. Reading an asserter invalidates a capability run, so the citation degraded the test method itself |
| `service_id`, then `cluster_id`, then the **justification key** — three unspecified identifiers a fixture keyed on. Nine different justification key names were in play across one run and one golden | `service_id` derivation rule; the justification key fixed by DISPOSITION; oracles repointed to `azure_id` |
| The clustering worked example predicts 4 clusters, the algorithm gives **5** | **13.4e firing a third time.** The golden also put an EDGELESS Cosmos account inside a cluster justified `merge:cross_group_edges` |

### 17.9 Still open, and one is a regression

1. **The corpus no longer exercises the untranslated-type halt at all.** `azurerm_iothub`
   derives, so `unsupported.tf`'s comment is stale and the estate built to test that STOP
   tests nothing. This is the `azurerm_dev_test_lab` failure mode (13.6) recurring: any
   fixture depending on a type being ABSENT gets disarmed. Needs a type in a namespace
   `namespace_routing` does not carry.
2. **A `Microsoft.Resources/resourceGroups` entry silently disables the split step** — its
   `azure_id` is a literal prefix of every resource in the group and containment counts for
   connectivity, so every seed becomes one component. **Both runs** hit this and both had to
   invent a same-`/providers/`-path restriction. The worked example's corpus omits RG
   resources; a real repo declares them.
3. **The Key Vault `secret_ref` edge is unresolvable by the letter of the rules** — four files
   cannot all be satisfied, and both runs broke the name-expression ban to satisfy the worked
   example.
4. **`cluster_id` has `service_id`'s stability requirement and none of its specification.**
5. ~~**Three instance types the design emits have no rate**~~ — **RESOLVED 2026-09-08, and
   the count was wrong.** It was six gaps and two contract defects, not three rows. See §18.1.
   `m6i.large`/`m6i.xlarge` were already in the file as EKS monthly rates and merely
   unreachable; `db.t3.medium` is a **DocumentDB** class, not an RDS one; and FSx for Windows,
   Lambda and the **Windows licence adder** were absent and unlisted. Lambda came from gcp's
   cache; the other three are `unavailable` until the MCP is reachable. **Still open:** those
   three rates, and the ~50 other types azure's sizing tables can emit that the rate card has
   no row for.
6. `NOTES.md` §1.3–1.9 and §2.x remain unaddressed — roughly 24 findings.

---

## 18. [ADDED] Estimate, 2026-09-08 (session 6)

Step 5c. Eight commits. The phase went from a 38-line skeleton to 1,037 lines
across three files, and the thing worth recording is not the content — it is that
**five defects were found by checking claims rather than by running anything**,
including two in artifacts this plan asserted were fine.

### 18.1 [CORRECTED] The pricing blocker was six gaps and two contract defects, not three rows

§17.9 #5 said three instance types had no rate. Measured against the corpus, that
understated it by half and mis-identified one:

| Claimed | Actual |
| ------- | ------ |
| `m6i.large`, `m6i.xlarge` missing | **Already in the file** as `eks.node_rates_monthly` 70.08 / 140.16 — these hourly rates x 730. Not missing, *unreachable*: the EB/EC2 formula reads `ec2.instances[...]` |
| `db.t3.medium` missing from RDS | It is a **DocumentDB** class. There is no `documentdb` section at all, and reading it from `rds_postgresql.instances` would be wrong twice — wrong service, and those rates are baked-in Multi-AZ |
| — | **FSx for Windows** — no section anywhere. Unlisted |
| — | **Lambda** — no section, and the file's own `_comment` called Lambda "gcp-specific". azure maps consumption-plan Function Apps to Lambda, so that was false. Resolved: harvested verbatim from gcp's cache |
| — | **The Windows licence adder.** `ec2.instances` is documented Linux/x86. The design emits `license_model: "License Included"` on a Windows `m6i.xlarge` and Clarify's licensing category fires. Pricing it at the Linux rate understates the estate's most expensive compute line by ~2x, in the direction that flatters AWS. **Worse than all three named**, and unlisted |

Underneath, the real finding: **the shared pricing hierarchy was keyed at SERVICE
granularity.** `pricing-mode.md` rung 1 fired on *"Service found in the pricing
file"*. `ec2` is in the file; `m6i.xlarge` is not — so the documented behaviour was
to label a missing number `cached` and continue. heroku never hit it because its
sizing table and its rates were co-authored; azure's eight sizing tables were
written from Azure SKUs and diverge on day one (**only 4 of ~35 emittable EC2 types
and 9 of 28 RDS classes have a row**).

Also fixed: **region**. Every rate is `us-east-1` with no multiplier while the corpus
targets `eu-west-1` — and Clarify's residency warning is about that same hop, so a
reader is primed to think the region was handled. And the cache has been past its own
staleness window since 2026-08-18, so every azure run is `cached_stale` from the
outset.

`uvx` is not installed, so the awspricing MCP is unreachable here. **Add it to the
absent-tools list** with mise, dprint, markdownlint, gitleaks and terraform. The three
remaining rates therefore could not be fetched and were not invented — which is what
gcp's own `pricing-fallback.md` demands: *"Never emit fabricated prices. A missing cost
estimate is better than a wrong one."*

### 18.2 [DECIDED] Three reasons a line leaves the totals, and a materiality rule

Two states could not express the corpus:

| `exclusion_reason` | Meaning | Corpus |
| ------------------ | ------- | ------ |
| `no_rate` | no rate row anywhere, MCP unreachable | DocumentDB, FSx |
| `partial_rate` | base rate resolved, a required COMPONENT did not | both Windows lines |
| `no_quantity` | every rate resolved, no quantity to multiply | Lambda |

Lambda is the instructive one: its `pricing_source` is legitimately `cached` while
its `exclusion_reason` is `no_quantity`. Conflating "no rate" with "no quantity"
loses the distinction between a gap in our data and a gap in the customer's.

**The rule: price what is quantified; exclude only when the PRIMARY driver is
unpriced.** MSK keeps its line (brokers quantified, per-broker storage not); a
Windows instance loses its (the licence is ~half). This is a materiality judgement
and it is stated as one, so it can be argued with rather than discovered.

### 18.3 [ADDED] The $0 delta, and why it is the phase's most dangerous number

On a Terraform-only estate the right-sizing delta is **legitimately $0** — and a $0
is exactly what a phase that never computed it also produces.

Separating the two kinds of right-sizing is what made this sayable:
**utilization-based** needs metrics (and `rightsizing-thresholds.json`'s
`_precondition` forbids applying its P95 bands to a declared SKU), while
**declared-waste-based** needs none. With no metrics the sizing tables map
like-for-like, so `aws_config` already equals the lift on every priced line.

So the explanation is REQUIRED and required to say WHY, `declared_waste_found` is
recorded separately, and the idle P1v3 Windows plan with zero apps survives as a
finding even though it moves no dollars — it is excluded as `partial_rate`, so it
could not have moved them either way.

### 18.4 [CORRECTED] Plan §8 was half right about the shared schema, and the artifact failed it

§8 said `estimation-infra.schema.json` *"has no `additionalProperties: false` ... so
no schema change is needed."* True for ADDING. It says nothing about `required`, and
the first artifact violated the schema three ways:

1. `projected_costs.required` is `[aws_monthly_premium, aws_monthly_balanced,
   aws_monthly_optimized]` and the dual output **replaced** them. They are a
   different axis — scenarios vary resilience and pricing model, the dual output
   varies sizing — and neither substitutes for the other.
2. `breakdown` is declared `type: object` (keyed by service, with a `total`, as
   heroku and gcp emit). It was an array.
3. `accuracy_confidence` is declared a string. It was an object.

**`_validate_json` catches none of these** — it checks parseability, not conformance.
A phase can declare a schema in `_knowledge`, satisfy every postcondition it wrote
for itself, and still emit an artifact the shared contract rejects. That is a general
hole, not an azure one.

Reconciled without a shared change: **Balanced IS the right-sized total** (emitted
equal, not computed twice), Premium adds the multi-AZ uplift only for
`multiplier_x2` lines that are not already multi-AZ, and Optimized discounts only the
RI/SP-eligible subtotal — $329.79 of $465.09 here. A blanket 30% would have
discounted $135.30 with no commitment product behind it, and **MSK is the trap**: it
looks like something an RI covers and has none.

The oracle now reads the schema's `required` list **at assert time** rather than
restating it, so the fixture cannot drift from the contract it enforces.

### 18.5 [ADDED] The tolerance model, and why the tiers are the point

The first fixture in the repo that cannot use exact assertions.

| Tier | What | Why it is the right shape |
| ---- | ---- | ------------------------- |
| **1 — exact** | everything that is not a dollar figure | rates drift; contracts do not, and every defect five capability runs found was of this kind |
| **2 — relational, exact to 1e-6** | totals reconcile to their own lines; delta = lift − right_sized; annual = monthly x 12; `financial_summary` is the negation of `cost_comparison`; per-cluster sums | properties of the ARTIFACT, not the price list, so they survive any refresh |
| **3 — banded** | per-line figures against `[min, max]` **recorded**, never recomputed | a rate refresh that moves a line out of band becomes a reviewable diff |

Rejected: **a blanket percentage on the grand total** — the one number where two
compensating errors cancel and one rate change fails everything. And
**recomputing expected values from the vendored card**, which never goes stale but
shares the run's input, so it catches arithmetic slips and nothing else: not a Linux
rate used for a Windows box, not an RDS class read for a DocumentDB line. Those are
the defects the fixture exists for.

Envelopes are per line by what the line is made of — 10% for rate x count, 35% for a
usage heuristic, 15% for the total. **A band tighter than the coarsest input is
theatre**, and the coarsest input here is a log-volume guess.

**Verified rather than asserted:** a simulated +7% rate refresh passes with zero
relational failures; +25% fails 10 bands with zero relational failures.

### 18.6 [ADDED] What checking found that running would not have

Five defects, none of which a completing run would have surfaced:

| Found by | Defect |
| -------- | ------ |
| Auditing asserted fields against the refs | **11 fields the oracle asserted and no skill file defined** — §15.4's class for the FIFTH time, caught pre-ship this round rather than by a capability run afterwards |
| Validating the golden against its declared schema | §18.4's three violations |
| Reading my own file end to end | **Totals came before the observability line that belongs in them.** An agent following "execute in order" would understate every total by the CloudWatch figure while every reconciliation check still passed, because the total would agree with the lines it was built from |
| Checking whether Design still halts | `run-asserters.py` and §14 both said Design GATE_FAILs so Estimate was unreachable. **Both gates §16.4 named are gone** — derivation cleared `untranslated_types`, the rubrics cleared `pending_rubric` — and neither was closed by the work proposed for it |
| Mutation-testing the oracle | Two bugs IN THE ORACLE, both §16.1's shape: a case-insensitive match on `FTE` hits "a**fte**r", and the no-labor check scanned the disclaimer that states the rule, so an artifact correctly saying "no engineer-weeks here" failed for containing the words |

**54 mutations, all caught with a message naming the rule violated.**

Note the third row generalises: **`_assert` postconditions cannot catch an ordering
bug**, because a wrong-but-self-consistent artifact satisfies every relationship it
declares. Only reading the procedure catches it.

### 18.7 [ADDED] Capability run 6 — and it beat the author twice

Fresh isolated agent, full chain, **goldens structurally unreachable** (the copied
tree contains no `fixtures/` at all — an improvement on honour-based prohibition).
All four phases `HANDOFF_OK`. 1,414 lines of notes at
`/local/home/carthick/dev/capability-run-6/`. **Prohibitions fully complied with**,
and it was tempted exactly where the brief predicted — wanting the asserter to settle
whether IoT Hub is untranslated — and recorded the temptation instead.

It tested the skill as of `aa40184`, so several complaints name fields specified
afterwards in `ce744d5` / `3855410`. That is independent convergence and is recorded
as such, not claimed as foresight.

**Two answers it got right and the author got wrong:**

| | Author | Run 6 | Why the run is right |
| - | ------ | ----- | -------------------- |
| `complexity_tier` | `medium` | **`large`** | `complexity-tiers.json` makes `service_count_gte: 9` a LARGE condition with `match: "any"`, and there are 16 services. The expected file justified `medium` as *"service count 17 is above the Medium band"* — and above the medium band **is** large. The oracle pinned a wrong answer and mutation-tested `small` as the error, while `large` would also have failed |
| `compliance` | `"none"` | **`null`** | **No Clarify fragment produces a compliance row.** `"none"` fabricates an answer to an unasked question |

The second has two consequences now stated rather than absorbed:
`compliance_present` is a permanently unevaluable `large` condition on this skill,
and **Part 8's hard trigger 1 opens with a permanently-true clause** ("compliance is
unknown"), so only its second clause does any work.

**Its most serious finding, missed entirely by the author: a rate that describes the
WRONG CONFIGURATION.** `rds_postgresql.instances` rates are Multi-AZ
(`multi_az_handling: baked_in`); the design is single-AZ. So the largest line in the
estate — **59% of the priced total** — is roughly **2× too HIGH**, there is no
single-AZ table, and halving a Multi-AZ rate would invent one.

This is worse than a missing rate, because **the arithmetic looks complete**. The
first golden called the line *"if anything conservative"*, which is the wrong
framing: overstating the largest line makes AWS look MORE expensive and can invert a
migrate/stay recommendation just as surely as understating it.

> **The generalisation worth keeping: a total can be wrong in BOTH directions at
> once.** Exclusions push every total down; a wrong-configuration rate pushes the
> biggest line up. Calling the result a "floor" is then false, and netting the two
> off is worse — they do not cancel in any knowable amount. `accuracy_confidence`
> now states both.

**Other fixes it drove:** a **closed warning vocabulary** for Estimate (Discover and
Design both declare theirs closed; Estimate had none, so the run invented five codes
and declared them — correct behaviour under a missing rule, wrong state for the rule);
**tier→weeks bands** (the gate renders `~[N-M] weeks`, `complexity-tiers.json` says
timelines live in the consuming prose, and the consuming prose had none — the run
flagged `12-18` as *"a number no file supplies"*); and the **`cached_stale` vs
`cached_fallback` tiebreak** in the shared file, where three rules named two values
for the normal case.

It also found **a crash in the oracle** — the fourth oracle bug a capability run has
produced. A tolerance bound by a walrus inside an `if` left the asserter crashing on
an artifact that took the other branch. **A crashing oracle is worse than a failing
one: it says nothing at all about the artifact.**

**63/63 mutations** after the additions.

### 18.8 [ADDED] Findings run 6 raised OUTSIDE Estimate, not yet fixed

Its top-ranked item is not in this step's scope and is the highest-value thing left:

1. **`disk-ebs-sizing.json`'s `_when` gate excludes the case its own body calls the
   "MOST COMMON CASE".** A VM's `os_disk` is an inline block, so no
   `Microsoft.Compute/disks` resource exists — which is exactly what the gate
   requires. The run **knowingly broke `SKILL.md:60`'s MUST NOT** to load the file,
   and disclosed it, because the alternative was fabricating an EBS type. This is
   §17.6's unsatisfiable-instruction shape again, and the fix is one line.
2. **`clustering-algorithm.md` disagrees with its own worked example — 5 clusters vs
   the 4 it predicts.** §13.4e firing a **fourth** time. Two NEW sub-findings: the
   example silently needs a VM→NIC edge no extraction rule produces, and silently
   excludes resource groups from containment — **which is §17.9 #2, independently
   rediscovered for the third time.** The file *asks* the reader to re-trace it and
   then contradicts the trace.
3. **Three stale enums** — `azure_type_provenance` (`discover.md:36`),
   `untranslated_types` (`discover.md:37`), `routing_provenance`
   (`schema-design-aws.md:282`). Each would fail a postcondition on an artifact that
   follows the extraction rules exactly.
4. **Two sizing tables do not exist** (ElastiCache, MSK), so two dollar figures —
   $91.40, 19.7% of the run's total — rest on sizes the model chose. Zero figures came
   from an unsourced RATE; these are unsourced SIZES, which is the softer failure §14
   describes but still unasserted.
5. `references/shared/graviton.md` is cited by four files and does not exist.
6. `design-assemble.md` rule 5 requires an MCP server `SKILL.md` does not declare.
7. Whether a PROPOSED-from-default value counts as a user preference is unstated, and
   it changes both the compute target for a class of plan and what `value` holds in
   every PROPOSED row. One sentence in `schema-preferences.md` closes both.
8. `INTERPRETER.md` is declared skill-agnostic and then names another skill as owner;
   `_exec` names worker files absent from the tree.

### 18.9 Still open after this session

1. **Four rate gaps** — DocumentDB, FSx for Windows, the Windows licence adder, and
   **a single-AZ RDS table** (§18.7). The first three are blocked on `uvx`/MCP; the
   fourth is a table nobody has, and it is the largest single inaccuracy in the output. Until then their lines are excluded and both totals are floors, which
   means **the corpus estimate is a floor and its 89% apparent saving is not a
   credible finding** — the artifact says so in `cost_comparison.credibility_caveat`.
2. **The sizing-table / rate-card pair is unguarded.** ~50 types the sizing tables can
   emit have no row. `_rate_row_coverage._who_owes_what` records the obligation; no
   tool enforces it. This is a §15.2 pairing check waiting to be written.
3. **`preferences.licensing` undercounts Windows workloads.** It records 1 workload /
   4 vCPU because `clarify-licensing.md`'s firing rule reads only
   `Microsoft.Compute/virtualMachines`; the Windows App Service Plan also carries
   Windows licensing on the target. Estimate uses 2 / 6 and says why, but Clarify's
   rule is the thing that should change.
4. **The reservation `$0` rule is untested and unreachable**, by construction. It stays
   as a contract for when the billing source lands.
5. §17.9 #1–#4 and #6 unchanged; NOTES.md §1.3–1.9 and §2.x still ~24 findings.

***

## 19. [ADDED] AI / agentic workload capability — build plan (2026-09-14, session 8)

**Owner ask:** add the capability to migrate AI workloads, referencing how `gcp-to-aws`
implemented it. This section is the plan; no AI code has been written yet. Every claim is
grounded in files read at HEAD `43fa5dc`; file:line given where load-bearing. Default
posture per §0: **mirror gcp's AI subsystem; diverge only for a documented Azure fact.**

### 19.0 The headline — this is much smaller than §6a feared

§6a called the shared-AI-promotion PR "the highest-risk item in the plan" and a
prerequisite blocker. **It is already done on `main`.** `skills/shared/ai/` exists and is
fully populated (8 files: `ai-openai-to-bedrock.md`, `ai-anthropic-to-bedrock.md`,
`design-ref-agentic-to-agentcore.md`, `design-ref-harness.md`, `ai-migration-guardrails.md`,
`ai-model-lifecycle.md`, `bedrock-quotas.md`, `sdk-capability-map.json`), byte-synced into
gcp and heroku via `references/vendored/ai/`. So the risky cross-skill promotion is behind
us; azure only needs to **vendor** the tree (additive, per §6a's own note that
`sync-vendored-shared.ts` walks the vendored side).

Two more facts collapse most of the remaining work:

1. **Azure OpenAI == the OpenAI SDK path.** `shared/ai/ai-openai-to-bedrock.md`'s header
   states it is source-cloud-agnostic and *explicitly names Azure OpenAI* as a served
   source, "because the Bedrock target does not depend on which endpoint served the calls."
   `sdk-capability-map.json` keys on the **SDK call pattern** (`openai.chat.completions.create`,
   …), and Azure OpenAI apps call the `openai` SDK. So the OpenAI / Anthropic / agentic /
   guardrails / lifecycle / quota machinery ports **unchanged**.
2. **Azure already discovers and canonicalizes the AI infra.** `extract-terraform.md`
   extracts `Microsoft.CognitiveServices/accounts` (`kind`, `sku_name`);
   `arm-type-canonicalization.md` canonicalizes `azurerm_cognitive_account` /
   `azurerm_cognitive_deployment` and folds `Microsoft.OpenAI/accounts` →
   `Microsoft.CognitiveServices/accounts`. The resources land in the inventory today.

### 19.1 The capability is currently a live HALT, not merely "absent"

Because discovery works but the design refs do not exist, **any Azure estate containing a
Cognitive Services account (which is every Azure OpenAI workload) reaches Design and
`GATE_FAIL`s** on a dangling reference. This is the intersection of the owner ask with an
existing latent defect — building AI fixes it. The dangling refs:

- `design-refs/index.md:168-170` → `vendored/ai/ai-openai-to-bedrock.md` (kind OpenAI),
  `ai.md` (other kinds), `vendored/ai/ai-openai-to-bedrock.md` (`accounts/deployments`)
- `knowledge/design/fast-path-services.json:651-652` → `Microsoft.CognitiveServices`
  `route: ai.md`
- `phases/design/design.md:125` names `ai.md` as expected-but-halting
- `phases/clarify/clarify.md:112` + `clarify-assemble.md:139` route to `clarify-ai.md` /
  `clarify-ai-only.md` — also absent

None currently fires only because the Terraform corpus carries no cognitive account. That
is the §13.6 disarmed-fixture trap again: the HALT is real, just unexercised.

### 19.2 What gcp's AI subsystem is (the thing being ported)

A **self-contained, file-based track** — it does NOT hand off to the sibling `llm-to-bedrock`
or `agent-advisor` skills (0 references from inside gcp-to-aws). The "handoff" is intra-skill
fail-closed gates plus routing to vendored sub-refs. Shape:

| gcp file | Role | Produces / key contract |
|---|---|---|
| `discover/discover-app-code.md` | SDK + framework signal scan; Step 3 model detect, Step 3B agentic signals 3B.1–3B.9, ≥70% confidence gate | `ai-workload-profile.json` (`summary.ai_source`, `models[]`, `integration.gateway_type`, `workloads[]`, `agentic_profile{is_agentic,framework,orchestration_pattern}`, `tool_manifest[]`) |
| `discover/discover-openai-api.md` | consent-gated OpenAI Admin API usage capture, GET-only allowlist, supplement-not-anchor | `openai-usage-profile.json`; fills `current_costs` |
| `shared/schema-discover-ai.md` | the AI artifact schema | `ai_source ∈ gemini\|openai\|anthropic\|both\|other` |
| `clarify/clarify-ai.md` | Categories F/G/H (Q14–27); Q27 Activate credits ESSENTIAL | when AI profile exists alongside infra |
| `clarify/clarify-ai-only.md` | AI-only route: infra stays on source cloud, only LLM calls move to Bedrock | `metadata.migration_type: "ai-only"` |
| `design/design-ai.md` | model map = modality/latency/context/cost via override hierarchy; agentic branch on `migration_approach` (retarget/harness/strands/undecided) | `aws-design-ai.json`; `target_bedrock_model` XOR `target_aws_service` |
| `estimate/estimate-ai.md` | Bedrock pricing **per 1M tokens**, reads `shared/pricing-cache.md` (not `bedrock-quotas.md`); traditional-AI excluded (per-page) | `estimation-ai.json` |
| `generate/generate-ai.md` + `generate-artifacts-ai.md` | plan + emit provider adapter code, `setup_bedrock.sh`, `bedrock_monitoring.tf`, gateway configs, eval harness | `generation-ai.json`, `STARTUP_PROGRAMS.md` |

Design-ref routing by `ai_source`: gemini → `design-refs/ai-gemini-to-bedrock.md`; openai →
`vendored/ai/ai-openai-to-bedrock.md` (+ `shared/openai-on-bedrock.md`); anthropic →
`vendored/ai/ai-anthropic-to-bedrock.md`; both → gemini+openai; other/absent →
`design-refs/ai.md` (traditional-ML). Any workload with capability ∈ {document_extraction,
image_analysis, speech_transcription} also loads `ai.md`.

### 19.3 [DECIDED] What ports, what is net-new, what is Azure-swapped

| Layer | Verdict | Azure delta |
|---|---|---|
| `vendored/ai/*` (openai, anthropic, agentcore, harness, guardrails, lifecycle, quotas, sdk-capability-map) | **vendor unchanged** | byte-identical copy of `skills/shared/ai/`, both trees |
| `design-refs/ai-gemini-to-bedrock.md` | **replace** | net-new `ai-azure-openai-to-bedrock.md` — but since Azure OpenAI == OpenAI models, most estates route to the shared `vendored/ai/ai-openai-to-bedrock.md`; this ref is thin |
| `design-refs/ai.md` (traditional ML) | **rewrite signals** | Azure ML, AI Vision→Rekognition, Document Intelligence/Form Recognizer→Textract, Speech→Transcribe, Language→Comprehend; AWS targets unchanged |
| `design/design-ai.md`, `estimate/estimate-ai.md`, `generate/generate-ai.md`, `generate-artifacts-ai.md` | **port with edits** | thread `ai_source: azure_openai`; infra table `google_vertex_ai_*`→`azurerm_cognitive_*`; adapter default provider `vertex_ai`→`azure_openai` |
| `clarify/clarify-ai.md`, `clarify-ai-only.md` | **port ~unchanged** | provider-agnostic; keep Categories F/G/H and Q27 ESSENTIAL |
| `discover/discover-app-code.md` | **net-new for azure** (azure has NONE) | Azure SDK signals: python `AzureOpenAI` / `openai.api_type="azure"` / `AZURE_OPENAI_*`; node `@azure/openai`; `azure-ai-inference`. Agentic Step 3B signals port unchanged |
| `discover/discover-openai-api.md` | **port unchanged** | many Azure apps still hit `api.openai.com`; also captures Azure-OpenAI-via-openai-SDK spend |
| `shared/schema-discover-ai.md` | **port with edit** | `ai_source` gains `azure_openai`; `profile_source` gains an `iac_cognitive` analog of gcp's `iac_vertex` |
| SKILL.md | **wire** | AI trigger phrases, `ai_source`, AI conditional-load table, hybrid-stack ~800-line two-pass warning — all absent today (only the single "migrate Azure OpenAI to Bedrock" trigger exists) |

**[DECIDED] `ai_source` gains `azure_openai`, not a reuse of `openai`.** Rationale: the value
must record the *source estate fact* (this workload ran on Azure OpenAI) for the report and
for the `iac_cognitive` inference path, even though it *routes to the same* OpenAI→Bedrock
ref. Same pattern as gcp keeping `gemini` distinct while `both` still loads shared refs.
Divergence justified by an Azure-specific fact and recorded here per §0.

### 19.4 [ADDED] Consumer-contract dependency — the one non-obvious cost

`shared/ai/README.md` states a skill that vendors `references/vendored/ai/` **must also
ship** `references/shared/pricing-cache.md` and `references/shared/pricing-fallback.md`.
Azure's `references/shared/` has **neither**. These are **gcp-authored** (they live in
`gcp-to-aws/references/shared/`, not in canonical `skills/shared/ai/`), so azure needs its
own. The Bedrock rate rows are source-agnostic (copy), and only the Azure-OpenAI **source**
pricing rows differ. This is small but load-bearing — estimate-ai reads `pricing-cache.md`
for the price lookup order, so without it Estimate for AI is unpriced.

### 19.5 [ADDED] Divergence guard — do not invent a skill handoff

gcp's AI track is self-contained and does not call `llm-to-bedrock`/`agent-advisor`. Per §0,
azure must NOT add a live Skill-tool handoff gcp lacks. The existing §6b/§6c handoff prose
(pointer + `handoff-summary.md`) is the agnostic pattern and is unchanged; keep
`clarify-ai-only.md` as the AI-only entry (per §6c correction) and do not build more surface.

### 19.6 Build order (mirrors gcp; IaC-sourced AI first because discovery already works)

Ordered so each step ends at a green gate suite (both trees; tools run directly):

1. **Vendor `shared/ai/` → `references/vendored/ai/` (both trees)** + author
   `references/shared/pricing-cache.md` + `pricing-fallback.md` (§19.4). Exit: `shared:check`
   green, cross-plugin symmetry holds. **This alone un-HALTs the OpenAI-kind path.**
2. **`design-refs/ai.md` (Azure signals) + `ai-azure-openai-to-bedrock.md`** → resolves the
   remaining design HALT. Port `design/design-ai.md`; add `schema-design-aws-ai.md` /
   `aws-design-ai.json` contract.
3. **`clarify-ai.md` + `clarify-ai-only.md`** (resolve clarify HALT); **`estimate-ai.md`**;
   **`generate-ai.md` + `generate-artifacts-ai.md`**; SKILL.md wiring + `ai_source` threading;
   `schema-discover-ai.md` with `azure_openai`.
4. **`discover-app-code.md` + `discover-openai-api.md`** — makes AI detectable WITHOUT IaC
   (most startups have no cognitive-account Terraform), so this is the highest-reach step and
   carries the most Azure-signal authoring. Adds the producer of `ai-workload-profile.json`.
5. **Fixtures + oracles per phase** (§9 / §15 discipline): an AI-estate fixture with
   `expected-*` + `check_expected_*`; the pairing check "every `index.md` /
   `namespace_routing` design-ref exists on disk" (would have caught §19.1); a fresh-context
   capability run on an AI estate with `fixtures/`/`expected-*`/`after-*` hidden.

Steps 2 and 3 parallelize (design refs vs phase fragments converge on the artifact contract);
step 4 is independent of both. Step 1 gates all.

### 19.7 Testability note (the §12/§15 trap applies here too)

`_assert` will pass for an AI design produced entirely from the model's pretraining about
Bedrock — a capable model knows `gpt-4o → anthropic.claude-*` shapes without reading any ref.
So AI Design is not truly testable until (a) `ai.md` / `ai-azure-openai-to-bedrock.md` exist
(something to check against) and (b) an oracle pins the divergences where a plausible guess
and the correct mapping differ (e.g. Document Intelligence → **Textract** not "Bedrock
vision", `target_aws_service` set and `target_bedrock_model` null for the three traditional
capabilities). Build the oracle with the design ref, per §12's "the table is the first thing
that makes output checkable."

### 19.8 [DECIDED] Two mechanics questions, settled

Two things §19 named but did not pin down. Both were raised in review and both change how
the work is built, so they are decided here.

**(a) App-code discovery is REQUIRED, not optional — it is the AI detector.**
Azure's `discover` is IaC-only today (a single `iac` fragment). IaC detects AI
*infrastructure* — a `Microsoft.CognitiveServices/accounts` resource — but the AI *workload*
(which model, which SDK, whether it is agentic) lives in **application code**, not in
Terraform, and most startups have no cognitive-account Terraform at all. gcp's entire AI
detector is `discover-app-code.md` (SDK imports + agentic Step 3B signals →
`ai-workload-profile.json`); without an app-code scanner azure can only ever see AI when a
customer happened to Terraform their Cognitive Services account. So `discover-app-code` is
the piece that makes AI migration real, and `ai-workload-profile.json` (the artifact every
downstream AI unit reads) has **no producer** until it exists. It stays step 4 in §19.6 for
sequencing (design/clarify/estimate un-HALT first, on IaC-detected AI), but it is on the
critical path for the capability, not a nice-to-have. `discover-openai-api.md` is a
consent-gated *usage/cost supplement*, not a detector — separate, lower priority.

**(b) The AI units are DSL FRAGMENTS, not gcp-style prose files. This is a deliberate,
sanctioned divergence.**
gcp's AI files carry **no frontmatter** — they are plain markdown (`# Discover Phase: App
Code Discovery`) wired by imperative glob logic inside `discover.md` / `clarify.md`. That is
gcp's older prose-routing style. **Azure is DSL-native (locked decision 1, §0):** a phase
declares its parts in a `_fragments:` block with `_id` / `_trigger` / `_file`, and the
interpreter derives loading from that. So azure must NOT copy gcp's prose routing — it must
express each AI unit as a proper fragment on the owning phase, matching azure's own
`discover-iac` / `clarify-compute` shape. Copying gcp's frontmatter-less files verbatim
would reproduce the §12 false-green trap: `parse.ts:49` skips any file not starting with
`---`, so a prose AI file passes `lint:frontmatter` while being entirely unvalidated. This
divergence is exactly the kind §0 sanctions (justified by the DSL execution model itself);
we match gcp's **content, artifact shapes, `ai_source` routing, and agentic branches**, and
diverge only on the **wiring mechanism**.

The AI unit per phase, as azure fragments (trigger shown as the `_when` guard):

| Phase | Fragment `_id` | `_file` | `_trigger` `_when` |
|---|---|---|---|
| discover | `app-code` | `phases/discover/discover-app-code.md` | source code / dependency manifest present in workspace |
| discover | `openai-api` (optional) | `phases/discover/discover-openai-api.md` | AI profile has `ai_source ∈ {openai, azure_openai, both}`, OR user asks re OpenAI spend (consent-gated) |
| clarify | `ai` | `phases/clarify/clarify-ai.md` | `ai-workload-profile.json` exists |
| clarify | (`ai-only` route) | `phases/clarify/clarify-ai-only.md` | ONLY `ai-workload-profile.json` exists (no infra inventory) — routed by `clarify.md`, per §6c |
| design | `ai` | `phases/design/design-ai.md` | `ai-workload-profile.json` exists |
| estimate | `ai` | `phases/estimate/estimate-ai.md` | `ai-workload-profile.json` exists |
| generate | `artifacts-ai` | `phases/generate/generate-artifacts-ai.md` | AI design present AND `run_mode == decide_and_execute` |

Each fragment gets its own `_produces`/`_contributes` and the phase's `_postconditions`
extend to the AI artifact (`ai-workload-profile.json`, `aws-design-ai.json`,
`estimation-ai.json`, `generation-ai.json`) — mirroring how the infra fragments contribute
today. The clarify `ai-only` unit is a routed flow (a full standalone entry), not a
`_fragments` entry, exactly as §6c kept it.

**Consequence for the phase count.** Adding AI fragments does NOT add phases — they attach
to the existing seven. `lint:frontmatter` still reports 7 phase files; the fragment count
per phase grows. (Contrast the never-built `confirm` phase, §16.3, which would have changed
the phase count.)

### 19.9 [DECIDED] The three open decisions, resolved (2026-09-14)

Resolved by reading how gcp actually consumes each thing (not by assertion). File:line
evidence is in the session notes; the load-bearing findings are quoted inline.

**(a) Azure-OpenAI source pricing — NO net-new table; reuse the OpenAI rows.**
gcp's "what you pay today" ($X in the source-vs-target comparison) is **measured/stated
spend**, resolved by a 4-level precedence in `estimate-ai.md` Part 1:
`ai-workload-profile.json → current_costs.monthly_ai_spend` (1) → `openai-usage-profile.json`
(2) → token-volume × source list price (3) → none/multi-tier (4). The **static
`## Source Provider Pricing` table** in `pricing-cache.md` (Gemini + OpenAI standard-tier
rows) is used ONLY for the case-3 fallback estimate and the per-model "vs Source Provider"
comparison column — never for the primary "today" figure.
Consequence for azure: (i) when Discover/Clarify supply Azure spend, **no source-price table
is needed at all**; (ii) for the no-spend fallback and the "vs source" column, **Azure
OpenAI list prices ≈ OpenAI list prices** (same GPT models), so azure **reuses the existing
OpenAI rows in the shared `pricing-cache.md`** rather than authoring an Azure-specific table.
This also *retires* the §19.4 worry: the consumer-contract `pricing-cache.md`/`pricing-fallback.md`
azure must ship already carry the Bedrock target rates AND the OpenAI source rows; azure
adds **no AI price rows of its own**. (Azure still needs its own `pricing-cache.md` file to
exist as the consumer-contract artifact — but its AI content is a copy, not net-new pricing.)
[CORRECTS §19.4, which assumed azure must add Azure-OpenAI source rows.]

**(b) `ai_source` — add `azure_openai` as a DISTINCT label that ROUTES AS `openai`.**
The shared `vendored/ai/ai-openai-to-bedrock.md` header states it is source-cloud-agnostic
and **explicitly names Azure OpenAI** as a served source ("the Bedrock target does not depend
on which endpoint served the calls"). Everything that genuinely differs between `openai` and
`gemini`/`anthropic` is **target-side** (which design-ref, the Mantle-vs-Converse migration
path, code examples, the same-model validation rule) — and Azure OpenAI shares ALL of it with
OpenAI. So a separate branch would be a near-duplicate with zero target-side divergence.
Keep the value **distinct at the `summary.ai_source` layer** (not collapsed to `"openai"`) to
preserve the two source-cloud-specific things that would otherwise be lost: **report wording**
("migrate off Azure OpenAI") and **discovery provenance** (an Azure Cognitive Services /
`azurerm_cognitive_account` resource inferring `azure_openai`).
Enum becomes: `azure_openai | openai | anthropic | both | other` (azure DROPS gcp's `gemini`;
`both` = Azure-OpenAI/OpenAI + another provider). **The trap to avoid:** an unrecognised
`ai_source` in `design-ai.md`'s routing table falls through to `"other" → ai.md`
(traditional-ML) — a silent wrong route. So `azure_openai` MUST be explicitly wired at every
switch, treated as `openai`:
1. Add `azure_openai` to the `schema-discover-ai.md` enum (else a strict `_assert`/validator rejects it).
2. Routing row in `design-ai.md` / `SKILL.md` / `design-refs/index.md`:
   `azure_openai → vendored/ai/ai-openai-to-bedrock.md (+ shared/openai-on-bedrock.md)` — identical to `openai`.
3. Hardcoded switches map it to openai: `design-ref-harness.md`'s `source_model_provider → "open_ai"`;
   the `discover-openai-api` load gate/merge; any multi-provider check.
4. Add the display string "Azure OpenAI" in clarify/report wording spots.

**(c) `ai-only` migration route — DEFERRED to a fast-follow after the full-AI track.**
The ai-only route (infra stays on Azure, only LLM calls move to Bedrock) is **blocked today
and has no standalone value yet**, for three reasons:
- Azure `discover.md`'s precondition is `_assert: "at least one Azure source … .tf/.bicep/ARM"`
  with `_on_failure: _unrecoverable`. An AI-only customer (only app code, no IaC) **halts
  unrecoverably at Discover, never reaching Clarify.** gcp avoids this because its discover
  accepts application code as a standalone source.
- Azure `clarify.md` also requires `azure-resource-inventory.json` with ≥1 resource — an
  AI-only run has none.
- It presupposes the entire AI chain (AI discovery producing `ai-workload-profile.json`, plus
  `-ai` design/estimate/generate) that this work is only now building.
Once the full-AI track lands, ai-only is a **small fast-follow**: port `clarify-ai-only.md`
(~330 lines, mostly a re-skin of the AI/global questions; the only genuinely net-new surface
is Q4 cross-cloud latency + the cross-cloud `preferences.json` schema), add a `migration_type`
detector to `clarify.md`, and **relax the discover precondition** to accept an app-code/AI
source with no IaC. Recorded as a named fast-follow, not dropped. This supersedes §19.6's
implicit inclusion of `clarify-ai-only.md` in step 3 — it moves OUT of the core track into
the fast-follow.

**Net effect on the build plan:** step 2 is now unblocked. The consumer-contract pricing
files (§19.4) are a copy, not net-new pricing authoring. `ai_source` threading is a fixed,
enumerated list of wiring points. `clarify-ai-only.md` leaves the critical path. The full-AI
core track is: discover-app-code → clarify-ai → design-ai → estimate-ai → generate-artifacts-ai,
all keyed on `ai_source ∈ {azure_openai, anthropic, both, other}` routing to the already-vendored
shared refs.

### 19.10 [DECIDED] AI design output is a SEPARATE aws-design-ai.json (owner call, 2026-09-14)

The one durable architectural fork in step 2: does the AI design layer fold its rows into
the single `aws-design.json`, or write its own artifact?

**Decision (owner): produce a separate `aws-design-ai.json`, exactly as gcp-to-aws does.**

Rationale and the parity/convention reconciliation:
- **gcp parity (the deciding factor).** gcp's `design-ai.md` writes its own `aws-design-ai.json`;
  `estimate-ai.md` reads `aws-design-ai.json` and `generate-ai.md`/`generate-artifacts-ai.md`
  read it in turn. Matching the artifact shape keeps the entire downstream AI chain a
  straight port instead of a re-plumb — the §0 default posture (mirror gcp) wins here.
- **This does NOT break azure's assembler invariant.** azure's rule is "`design-assemble.md`
  is the single creator of `aws-design.json`." A separate `aws-design-ai.json` leaves that
  literally true — the infra assembler still solely owns `aws-design.json`; the AI layer owns
  a DIFFERENT file. So we are not violating the single-writer convention, we are adding a
  second, independently-owned artifact. This is the same shape gcp has (infra design and AI
  design are independent artifacts that Design produces side by side).
- **Wiring within azure's DSL.** The `ai` fragment on the design phase is its OWN writer of
  `aws-design-ai.json` (it does not contribute into the infra assembler). Concretely:
  - `design.md` `_fragments` gains `{ _id: ai, _trigger: { _when: "ai-workload-profile.json exists in $MIGRATION_DIR" }, _file: phases/design/design-ai.md }`.
  - `design.md` `_produces` gains `aws-design-ai.json`.
  - `design.md` `_knowledge` gains the AI refs under `_when` guards (the vendored openai/anthropic/agentic refs, `design-refs/ai.md`, `references/shared/schema-design-aws-ai.md`).
  - `design.md` `_postconditions` gain an AI-conditional block: WHEN `ai-workload-profile.json`
    exists, `aws-design-ai.json` must exist, validate, carry `metadata.ai_source` matching the
    profile, and every `design_blocks[]`/`bedrock_models[]` entry obey the target_bedrock_model
    XOR target_aws_service rule. When the profile is absent the AI fragment does not run and the
    block is vacuously satisfied.
  - `design-ai.md` frontmatter therefore looks like a fragment that self-produces:
    `_fragment: ai` / `_of_phase: design` / `_produces: aws-design-ai.json` (NOT `_contributes`),
    with its own `_postconditions`/completion gate — mirroring how gcp's design-ai fail-closes.
    This is a DELIBERATE shape divergence from `design-infra.md` (which `_contributes` to the
    assembler): the AI fragment is a self-contained writer because its artifact is separate.
    Recorded here so a future reader does not "fix" it to contribute into the assembler.

**Divergence ledger:** azure's infra fragments contribute to an assembler; the AI fragment
self-writes. Justified by the owner decision to match gcp's separate-artifact downstream
contract, and it preserves (does not break) the `aws-design.json` single-writer rule.

### 19.11 [BUILT + CORRECTED] Step 2 landed — AI design layer (2026-09-14)

Step 2 is built in both trees; all gates green (frontmatter 7/7, drift 363 identical, shared
OK, asserters 13, pricing-coverage OK). Files added: `references/shared/schema-design-aws-ai.md`
(the `aws-design-ai.json` contract), `references/design-refs/ai.md` (traditional-ML rubric with
Azure signals: Vision→Rekognition, Document Intelligence→Textract, Speech→Transcribe/Polly,
Language→Comprehend, Translator→Translate, Azure ML→SageMaker), `references/phases/design/
design-ai.md` (the AI fragment). Edited: `design.md` (ai fragment + knowledge + produces +
AI postconditions), `design-assemble.md` (now produces both artifacts).

**The design-side HALT is RESOLVED.** Both files `index.md` routes `Microsoft.CognitiveServices`
to — `ai.md` and `vendored/ai/ai-openai-to-bedrock.md` — are now on disk. A Cognitive Services
estate no longer `GATE_FAIL`s at Design.

**[CORRECTED] §19.10's wiring mechanism was wrong; the validator taught the right one.**
§19.10 said the `ai` fragment "self-writes `aws-design-ai.json`" with a `_produces` key. The
frontmatter validator (`check.ts:185-204`) rejects that: a FRAGMENT may not carry `_produces`,
and the single-creator rule requires every phase-`_produces` artifact to be created by exactly
one unit. The DSL-legal way to get a SEPARATE artifact (still matching gcp's shape and the
owner decision) is: the **assembler `_produces: aws-design-ai.json`** (assembler is the
creator), and the **`ai` fragment `_contributes: aws-design-ai.json`** (content contributor).
So `design-assemble.md` now produces BOTH `aws-design.json` and `aws-design-ai.json`; the ai
fragment contributes to the second. This preserves azure's single-creator invariant AND gives
the separate artifact gcp has. The divergence-from-`design-infra` shape is smaller than §19.10
implied: the ai fragment `_contributes` like infra does — it just contributes to a DIFFERENT
artifact that the assembler also owns.

**[NO WRAPPER] `ai-azure-openai-to-bedrock.md` was NOT created — deliberately.** §19.3/§19.6
listed it, but `index.md` routes `kind: OpenAI` DIRECTLY to `vendored/ai/ai-openai-to-bedrock.md`
(which is source-cloud-agnostic and names Azure OpenAI in its header), and
`fast-path-services.json` namespace-routes `Microsoft.CognitiveServices → ai.md` with a note
deferring OpenAI-kind to index.md. Nothing points at a wrapper, so creating one would be
orphaned surface gcp lacks (violates §0). The `ai.md` LLM-routing section points `azure_openai`/
`openai` straight at the vendored ref.

**[OPEN] `references/shared/openai-on-bedrock.md` is a dangling PROSE dependency.** The vendored
`ai-openai-to-bedrock.md` and `ai-migration-guardrails.md` cite `references/shared/
openai-on-bedrock.md` (the Bedrock-target fact base: model IDs, endpoint paths, region matrix,
quotas) 6+ times. That file is gcp-AUTHORED in gcp's `references/shared/` and is NOT in canonical
`skills/shared/` — so it is not vendorable via the sync tool. It was removed from design.md's
`_knowledge` (so it no longer fails frontmatter), but the prose cross-references inside the
vendored files remain, and a real OpenAI-source design run would want it. It is the SAME
consumer-contract gap class as `pricing-cache.md`/`pricing-fallback.md` (§19.4). RESOLUTION
options: author azure's own `references/shared/openai-on-bedrock.md` (a copy of gcp's — it is
cloud-agnostic Bedrock facts), OR consolidate all three consumer-contract files in one pass.
Deferred to the start of step 3 (estimate-ai needs pricing-cache anyway, so author all three
consumer-contract shared files together). Not a gate blocker today.

### 19.12 [DECIDED — reverses §19.9c] app-code-only runs are supported (owner call, 2026-09-14)

§19.9c DEFERRED the ai-only route ("infra stays on Azure, only LLM calls move to Bedrock"),
citing that it was blocked by discover's IaC-required precondition and had no standalone value
until the AI chain existed. The AI chain now exists (steps 2–4), and the owner instruction is
explicit: **gcp-to-aws supports migration from application code alone; azure-to-aws must too.**
So §19.9c is reversed — app-code-only is now IN scope.

**The gcp mechanism being matched (verbatim load-bearing rule, gcp SKILL.md Prerequisites):**
_"If no Terraform is found (even when app code or billing files exist …), … stop only when
nothing will produce any artifact."_ gcp routes every phase on ARTIFACT PRESENCE, and detects
"AI-only" by the resource inventory being ABSENT while `ai-workload-profile.json` is present.
gcp writes NO infrastructure inventory for an AI-only run (absent, not empty).

**Azure blocked app-code-only at five gates; the fix matches gcp at each:**

1. **discover.md precondition** (`_assert` requiring `.tf`/`.bicep`/ARM, `_unrecoverable`) —
   broaden to also accept application source code / a dependency manifest with a detectable AI
   signal. Keep `_unrecoverable` only for a truly empty workspace (no IaC AND no app code).
2. **discover.md postconditions** (`_check_file_exists` + `_validate_json` on the inventory, and
   `_assert "resources[] has ≥1 entry"`) — make them CONDITIONAL on an infra source having been
   found; add an anchor assert "at least one of azure-resource-inventory.json OR
   ai-workload-profile.json exists" (gcp's Handoff Check 1). An app-code-only run leaves the
   inventory ABSENT (matching gcp) and is vacuously clean on the infra asserts.
3. **discover-assemble.md** "stop if no valid resources / do not write an empty inventory" —
   change to gcp semantics: stop ONLY if neither a resource inventory NOR
   `ai-workload-profile.json` was produced. When app-code-only, write the AI profile, skip both
   inventory artifacts (do NOT write an empty inventory).
4. **clarify.md precondition** (`_check_file_exists [inventory,clusters]`, `_unrecoverable`) —
   require "at least one discovery artifact (inventory OR ai-workload-profile.json)"; add
   `ai-workload-profile.json` to `_input`; add **Migration Type Detection**: inventory absent +
   AI profile present → AI-only → route to `clarify-ai-only.md`. The infra-assuming
   postconditions (region/cpu/serverfarms/licensing) already fire conditionally on inventory
   content and stay vacuous under an absent inventory.
5. **Build `clarify-ai-only.md`** (the deferred route) — a standalone AI clarify flow that runs
   when only `ai-workload-profile.json` exists. Ported from gcp's `clarify-ai-only.md`: the
   cross-cloud question (Q4 — LLM calls move to Bedrock while infra stays on Azure: latency /
   PrivateLink / egress), compliance (never-dropped), Activate credits (never-dropped, ≡ Q27),
   and the AI question set reused from `clarify-ai.md`. Writes `preferences.json` with
   `metadata.migration_type: "ai-only"` and the confirmed `workloads[]`. It is a ROUTED flow
   (clarify.md detects and hands off), not a `_fragments` entry — matching §6c.

**Artifact-shape decision (match gcp): NO empty inventory.** An app-code-only run produces
`ai-workload-profile.json` and leaves `azure-resource-inventory.json` / `azure-resource-clusters.json`
ABSENT. Downstream phases already route on artifact presence (design-ai/estimate-ai/
generate-artifacts-ai fire on `ai-workload-profile.json`/`aws-design-ai.json`; the infra
fragments no-op with no inventory), so the AI-only path threads through with no new infra
plumbing — same as gcp.

**Still Terraform-first for INFRA.** This change does not touch the infra path; it adds the
app-code-only lane gcp has. A mixed repo (IaC + app code) is unaffected — both fragments run and
the inventory is written as today.

### 19.13 [DECIDED] Assess-complete handoff — emit DECISION.md at the decision gate (issue #292 item 3)

Colleague issue awslabs/startups#292 (a pre-Azure convergence plan, written before it knew
azure-to-aws had already been built) item 3: **standardize the Assess handoff** so a downstream
AI-rewrite path can consume an Assess-complete run from ANY source-cloud skill, not just gcp.
The standard signal is a tuple: `run_mode: "decide"` + `current_phase: "complete"` + a
`DECISION.md` (the Slack/GitHub-friendly decision marker) — the same shape gcp emits at its
`estimate.md` decision gate (`estimate.md:192-204`, rendered via shared `report-decision-core.md`).

**Conformance found (2026-09-15):** azure already emitted the `run_mode`/`current_phase` tuple on
option A, but produced **no `DECISION.md`** — so an Assess-complete azure run was not recognisable
by a consumer keyed on gcp's marker. That is the item-3 gap for OUR half.

**Our half — DONE:** `estimate-assemble.md` option A now writes `$MIGRATION_DIR/DECISION.md`
(Step 3a) — plain Markdown, no HTML: verdict headline, cost table (current Azure vs projected AWS,
floor/credibility caveats verbatim), migrate-if/stay-if, timeline band, top risks, assumptions,
CTA line. `DECISION.md` added to `estimate.md` + `estimate-assemble.md` `_produces` and gated by a
postcondition (`WHEN run_mode == decide, DECISION.md exists`). It is built from the artifacts that
exist at decision time (preferences + aws-design*/estimation-*), so it needs no new renderer.
Content matches gcp's `DECISION.md` twin spec (`report-decision-core.md` line 22).

**Deferred (a consumer-contract file, same class as pricing-cache/openai-on-bedrock §19.4/§19.11):**
the full HTML `decision-report.html` twin. gcp renders it via shared `report-decision-core.md`,
which is gcp-AUTHORED (not canonical, not vendored in azure). Vendoring it is the natural companion
to the other shared consumer files and is a presentation upgrade — `DECISION.md` is the
load-bearing handoff marker and stands alone.

**NOT our half — the other side of item 3 (flag to the colleague, do NOT edit unilaterally):**
`llm-to-bedrock` delegates Assess by a HARDCODED cross-skill call to gcp-to-aws (its Step 0b checks
`../gcp-to-aws/SKILL.md` and refuses to run without it; its description says "REQUIRES the
gcp-to-aws skill"). It has no awareness of azure-to-aws. For an AI-led entry ("migrate my Azure
OpenAI code to Bedrock") to route Assess to azure-to-aws, `llm-to-bedrock` must learn to select the
Assess provider by source cloud and read back the SAME tuple + `DECISION.md` + aws-design-ai.json.
That edits a sibling skill we do not own (it is #290's territory) and it raises a design question:
azure-to-aws already has a SELF-CONTAINED AI track (discover-app-code → clarify-ai → design-ai →
estimate-ai → generate-artifacts-ai), so an Azure AI user does not NEED llm-to-bedrock. Whether
azure should ALSO be a delegated Assess provider behind llm-to-bedrock (two doors to the same room)
is an owner/colleague decision, recorded here, not made in code.
