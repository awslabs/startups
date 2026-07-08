---
_phase: discover
_title: "Discover Heroku Resources"
_init: true
_input: workspace
_fragments:
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/discover/discover-terraform.md
  - _id: billing
    _trigger: { _glob: "**/*{billing,invoice}*.{csv,json}" }
    _file: phases/discover/discover-billing.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - heroku-resource-inventory.json
_advances_to: clarify
_interactive: false
_exec:
  _agent: rw
_re_entry_guard:
  _stale_if_completed: clarify
  _stale_artifact: preferences.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "at least one .tf file containing a heroku_* resource exists in the workspace"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: heroku-resource-inventory.json
    _on_failure: _halt_and_inform
  - _validate_json: heroku-resource-inventory.json
    _on_failure: _halt_and_inform
  - _assert: "heroku-resource-inventory.json has at least one resource entry, and metadata has discovery_timestamp and total_apps_discovered set"
    _on_failure: _halt_and_inform
  - _assert: "every resource in resources[] has resource_id, resource_type, heroku_app, and config fields"
    _on_failure: _halt_and_inform
  - _assert: "no forbidden clustering fields are present (cluster_id, creation_order_depth, edges, dependencies, must_migrate_together)"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - discovery-summary.md
  - "*.txt"
  - "terraform/**"
---

# Phase 1: Discover Heroku Resources

Lightweight orchestrator that delegates to domain-specific discoverers. Each sub-discovery file is self-contained — it scans for its own input, processes what it finds, and exits cleanly if nothing is relevant.
**Execute ALL steps in order. Do not skip or deviate.**

Procfile and app.json parsing is integrated into the Terraform discovery flow (there is no standalone Procfile fragment) — when repo artifacts are found alongside Terraform, they supplement resource data with commands, buildpacks, and declared add-ons.

**Note:** Platform API discovery is NOT supported in v1. No API calls are made. Discovery is entirely file-based (Terraform + repo + billing). All sub-discoveries contribute to a single `heroku-resource-inventory.json` artifact via the phase assembler.

---

## Step 0: Initialize Migration State

This phase has `_init: true`. Per `INTERPRETER.md` (§ `_init`), establish migration
state before running the sub-discovery fragments: resolve resume-vs-fresh, set
`$MIGRATION_DIR`, create `.migration/.gitignore`, and write the initial
`.phase-status.json`. Confirm both files exist before proceeding to Step 1.

---

## Step 1: Validate Prerequisites and Scan for Input Sources

### 1a. Check for Terraform files (PRIMARY)

Glob for: `**/*.tf` containing `heroku_*` resource types.

- If found → Mark Terraform discovery as enabled. This is the primary discovery path.
- If not found → Log: "No Terraform files with heroku_* resources found."

### 1b. Check for Procfile / app.json (SUPPLEMENTARY)

Search for: `Procfile`, `app.json` at workspace root or in subdirectories.

- If found → Mark repo artifact discovery as enabled. These supplement Terraform with commands and declared add-ons.
- If not found → Log: "No Procfile or app.json found — `command` fields will be null for formations."

### 1c. Check for billing data (OPTIONAL)

Glob for: `**/*billing*.csv`, `**/*invoice*.csv`, `**/*billing*.json`, `**/*invoice*.json`

- If found → Mark billing discovery as enabled.
- If not found → Log: "No billing files found — skipping billing discovery."

### 1d. Source validation gate

**If NO Terraform files with `heroku_*` resources found** (regardless of whether Procfile/app.json exist): this phase's `_preconditions` `_assert` fails with `_on_failure: _unrecoverable` (see `INTERPRETER.md` § Gate protocol / `_on_error`) — STOP and output: "No Terraform files with heroku_* resources found. Heroku Terraform is required for discovery. Procfile and app.json alone are not sufficient."

---

## Step 2: Run Sub-Discoveries

Execute applicable sub-discoveries in order. Each produces its contribution to the inventory.

**2a. Terraform Discovery (PRIMARY):**

If Terraform files with `heroku_*` resources found → Load `references/phases/discover/discover-terraform.md`

This produces:

- Resource extraction from `.tf` files (`heroku_app`, `heroku_addon`, `heroku_formation`, `heroku_domain`, `heroku_pipeline`, `heroku_space`)
- Procfile and app.json parsing (integrated — supplements Terraform with commands, buildpacks, declared add-ons)
- Cedar/Fir generation detection from `stack` attribute
- Private Space and peering detection from `heroku_space` resources

**2b. Billing Discovery (OPTIONAL):**

If billing data files found → Load `references/phases/discover/discover-billing.md`

This produces:

- Billing profile: total monthly cost, billing period, currency, per-resource line items
- Per-app cost breakdown when available

---

## Step 3: Assemble Inventory

Load `references/phases/discover/discover-assemble.md` (the phase's assembler) and follow it to combine the sub-discovery outputs into the single `heroku-resource-inventory.json` artifact. It owns that artifact's assembly rules and the failure behavior if no valid resources were produced.

---

## Step 4: Check Outputs

Verify required artifacts exist in `$MIGRATION_DIR/`:

1. `heroku-resource-inventory.json` — MUST exist with at least one resource entry.
2. `.phase-status.json` — MUST exist and be valid JSON with correct schema.

**Route output gates (fail closed):**

- If Terraform discovery ran → inventory MUST contain resources sourced from Terraform.
- If Procfile/app.json found → formation resources SHOULD have `command` fields populated (warning if not, not a gate failure).
- If billing discovery ran → inventory MUST contain a `billing_profile` section.
- If any triggered route is missing its required contribution: STOP and output which sub-discovery failed.

---

## Completion Handoff Gate (Fail Closed)

The completion checks are declared in this phase's `_postconditions` frontmatter and
enforced per `INTERPRETER.md` § Gate protocol: re-read `heroku-resource-inventory.json`
from disk, run the mechanical checks (`_check_file_exists` / `_validate_json`) and the
`_assert` judgment checks (at least one resource + required metadata, per-resource
fields, no forbidden clustering fields), plus the route output gates from Step 4, then
emit `GATE_FAIL` (STOP; do not patch artifacts) or
`HANDOFF_OK | phase=discover | artifacts=<files verified>` and advance.

---

## Step 5: Update Phase Status and Hand Off

Only after `HANDOFF_OK`, apply the phase-status update protocol (`INTERPRETER.md` § The interpreter loop) — mark `phases.discover` completed and advance per `_advances_to` — in the **same turn** as the output message below.

Output to user — build message from inventory contents:

- "Discovered X total resources across Y apps."
- If billing data available: "Parsed billing data ($Z/month)."
- If Terraform secondary: "Supplemented with Terraform-sourced resources (N conflicts resolved)."
- If Pipeline detected: "Detected N pipeline(s) (detect-only)."
- If Cedar/Fir mixed: "Generation detection: N Cedar, M Fir, P unknown."

Format: "Discover phase complete. [artifact summaries] Next required step: Phase 2 — Clarify. Load `references/phases/clarify/clarify.md` now. Do not load Design, Estimate, or Generate until Clarify completes and `.phase-status.json` marks `phases.clarify` as `completed`."

---

## Output Files

This phase's artifacts are declared in `_produces` and its scope boundary (files it must NOT create) in `_forbids_files`. Billing data, when present, is embedded in `heroku-resource-inventory.json` — not a separate file. All user communication is via output messages only (no report/log files).

---

## Error Handling

Non-fatal discovery errors and their handling (fatal source/gate failures are handled by `_preconditions`/`_postconditions` + `INTERPRETER.md` § `_on_error`):

| Error Category                                    | Behavior                                       |
| ------------------------------------------------- | ---------------------------------------------- |
| Terraform parse error (malformed HCL)             | Log warning, skip malformed blocks, continue   |
| Procfile/app.json parse error                     | Record warning per-app, continue               |
| Generation detection unresolvable (no stack attr) | Set `heroku_generation` to `unknown`, continue |
| Pipeline detection from Terraform incomplete      | Record with available data, continue           |

When all sub-discoveries produce no resources (or no Heroku Terraform is present), the phase's source `_precondition` fails `_unrecoverable`; a completion-gate failure halts per the gate protocol (retain `in_progress`, do not patch).

---

## Scope Boundary

**This phase covers Heroku Discovery ONLY.**

FORBIDDEN — Do NOT include ANY of:

- AWS service names, recommendations, or equivalents
- Migration strategies, phases, or timelines
- Terraform generation for AWS
- Cost estimates or comparisons
- Effort estimates

**Your ONLY job: Inventory what exists on Heroku. Nothing else.**
