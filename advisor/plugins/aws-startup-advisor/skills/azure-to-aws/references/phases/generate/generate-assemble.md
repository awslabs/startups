---
_assemble: assemble-generation
_of_phase: generate
_reads:
  - artifacts-infra (fragment contribution)
  - artifacts-docs (fragment contribution)
  - artifacts-report (fragment contribution)
  - artifacts-ai (fragment contribution, when aws-design-ai.json exists and run_mode is decide_and_execute)
_produces:
  - generation-warnings.json
  - validation-report.json
  - generation-ai.json
  - README.md
  - { file: MIGRATION_GUIDE.md, _when: "run has an infra track" }
---

# Generate — Assemble and Account

> **Assembler unit.** The single creator of `generation-warnings.json`. The
> artifact-emitting fragments contribute the documents and create the other files.
> This unit finalizes the documents after all fragments and proves nothing was dropped.
> See `generate.md` for how it is composed into the phase.
>
> **`validation-report.json` — declared here, written by the orchestrator.** This unit is
> the phase's declared owner of `validation-report.json` (the single-creator ledger), but
> its CONTENT — the Terraform fmt/init/validate result plus the `tf-best-practices` policy
> verdict — is authored by the orchestrator (`generate.md`) in the MAIN window after this
> worker returns, because the file-only `rw` worker cannot invoke skills or run
> `terraform`/`python`. This assembler writes `generation-warnings.json` and finalizes the
> documents as described below.

**Execute the steps in order. This is the phase's accounting gate.**

## Step 1: Account for every designed service

**Route on what exists (mirrors gcp-to-aws generate accounting).** When the run is AI-only / app-code-only there is no `aws-design.json` and no emitted `terraform/` — account against the AI artifacts instead: every `aws-design-ai.json` `models_to_migrate` entry is either **generated** (its adapter/monitoring landed in `ai-migration/`, e.g. `provider_adapter.py` / `migrate_to_mantle.sh`, `bedrock_monitoring.tf`) or carries a `generation-warnings.json` entry (e.g. `already_on_bedrock` model_change:false, or a `residual_azure_dependency` such as an Azure AI Search vector store to retarget). Any AI model or residual coupling that is neither generated nor warned is a dropped item — a gate failure. The `.tf`/secret/placeholder scans in Step 3 run against `ai-migration/*.tf` on this path. The rest of this step (below) applies to a run WITH an infra track.

Walk `aws-design.json` `services[]`. Each entry must be in exactly one of these states,
and the state must be demonstrable:

- **Generated** — a resource for it exists in an emitted `.tf` file. A service folded by the
  App Service Plan fan-in is counted ONCE via its parent's single compute target: the PARENT
  (the `Microsoft.Web/serverfarms` plan → its one compute target) is the `generated[]` entry,
  and each folded child is recorded as `skipped: folded_into_plan` — folded, not dropped, and
  not double-counted.
- **Intentionally not generated** — a skip (config source / observability) or a `deferred[]`
  specialist item. This MUST have a `generation-warnings.json` entry saying why.

Any service that is neither generated nor warned is a **dropped resource** — a gate
failure, not a warning.

## Step 2: Carry deferrals

For every `aws-design.json` `deferred[]` entry, write a `generation-warnings.json` entry
with its reason and recommendation, so a specialist deferral is visible in the output and
not only in the design.

## Step 2a: Carry the current AI memory plan into the documents

After all fragments finish, retain the base document content when `artifacts-docs` ran.
For an AI-only run, create `README.md` from the AI fragment's emitted file list and usage
instructions. When the AI fragment ran in this invocation, read its newly written `generation-ai.json`.
For each memory-ingestion activity in `migration_plan.phases[].activities`, write an
**AgentCore Memory** section preserving the API, rationale, application integration point,
IAM requirements, strategy setup, extraction verification, and raw-event retention behavior.

Use `MIGRATION_GUIDE.md` for an infra/mixed run and `README.md` for an AI-only run. Follow the
current run's track, not files left by a previous run; do not create `MIGRATION_GUIDE.md` for
AI-only runs. Replace a previously generated AgentCore Memory section rather than duplicating
it. If the AI fragment did not run or its current plan has no memory-ingestion activity,
omit that section and remove only
its previously generated version, preserving the rest of the document.

## Step 3: Scans (gate failures, not warnings)

Scan the emitted `.tf` files:

1. **Placeholder scan** — any leftover `{{VARIABLE}}` token is a gate failure. User-supplied
   values belong in `variables.tf` as `var.*` references (with validation blocks).
2. **Secret-value scan** — no secret VALUE from `azure-resource-inventory.json` may appear in
   any generated artifact. Secrets are emitted as Secrets Manager references only. A hit is a
   gate failure. (Match against the inventory's captured secret values / Key Vault secret
   contents; note discovery never captured Key Vault secret _values_, so this guards against
   any that leaked via app-settings.)

On any gate failure: emit `GATE_FAIL`, do not mark the phase complete, do not patch the
artifact to force a pass.

## Step 4: Do not overwrite inputs

Emit `generation-warnings.json`, finalize `README.md` and the infra/mixed run's
`MIGRATION_GUIDE.md` from fragment contributions, and retain the other fragment outputs.
Never write a phase input — `generate.md`'s `_forbids_files` names the state artifacts
explicitly.

## generation-warnings.json shape

The generated-service field is named **`generated[]`** — a canonical ARRAY parallel to
`deferred[]` and `skipped[]`, one element per generated service, never a bare count. This
is the single authoritative name: there is no `generated_detail`, no `generated_services`,
and no scalar `generated` — those drifted names are retired.

```json
{
  "phase": "generate",
  "generated": [ { "azure_id": "...", "azure_type": "...", "aws_service": "...", "target_file": "..." } ],
  "deferred": [ { "azure_id": "...", "azure_type": "...", "reason": "...", "recommendation": "..." } ],
  "skipped": [ { "azure_id": "...", "reason": "config_source|observability|folded_into_plan", "detail": "..." } ],
  "warnings": [ { "code": "...", "subject": "...", "detail": "..." } ],
  "accounted": <int>
}
```

`accounted` is DERIVED and it is the HEADLINE figure — `len(generated) + len(deferred)`. It
counts the primary services actually emitted (each App Service Plan fan-in fold counted ONCE
via its parent's compute target) plus the deferred specialist items. Every `services[]` entry
is still reflected in exactly one of `generated[]`, `deferred[]`, or `skipped[]` — the ledger
stays complete and nothing is dropped — but `skipped[]` entries (reason `config_source`,
`observability`, or `folded_into_plan`) are recorded for completeness and **EXCLUDED from the
`accounted` headline**: a config source, an observability sink, or a plan-folded child is not a
distinct billed service, and folding it into `accounted` double-counts against its parent.
`total_resources` in `azure-resource-inventory.json` remains the separate RAW discovered figure
(do not conflate the two).

**EventHub — record the namespace as `generated`, its children as folded.** A
`Microsoft.EventHub/namespaces` maps to Kinesis or MSK (per `kafka_enabled`) and is emitted as a
`services[]` entry, so it is a `generated[]` entry. Its `Microsoft.EventHub/.../eventhubs` and
`.../consumergroups` children are folded into that namespace's target — record each as
`skipped: folded_into_plan`, never as `generated` and never as `deferred`. (This fixes the
design-vs-generation inversion where the namespace was folded and a child was counted.)

## Step 5: Report

Report to the parent orchestrator (`generate.md` owns the phase-status update and the
final `HANDOFF_OK`). Do not update `.phase-status.json` here.

## Status — implemented (build step: Generate)

Accounting + scans implemented: per-service accounting (generated / deferred / skipped /
folded), deferral carry-through, placeholder + secret-value scans as gate failures, and
the `generation-warnings.json` shape. Mirrors the discipline of gcp-to-aws's generate
completion gate while owning azure's fan-in "folded" state explicitly.
