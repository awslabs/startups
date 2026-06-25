# Phase 1: Discover Heroku Resources

Lightweight orchestrator that delegates to domain-specific discoverers. Each sub-discovery file is self-contained — it scans for its own input, processes what it finds, and exits cleanly if nothing is relevant.
**Execute ALL steps in order. Do not skip or deviate.**

## Sub-Discovery Files

- **discover-terraform.md** → Terraform discovery (primary): `.tf` files with `heroku_*` resource types
- **discover-billing.md** → Billing data parsing: Heroku Dashboard invoices or Enterprise CSV exports

Procfile and app.json parsing is integrated into the Terraform discovery flow — when repo artifacts are found alongside Terraform, they supplement resource data with commands, buildpacks, and declared add-ons.

All sub-discoveries contribute to a single `heroku-resource-inventory.json` artifact.

**Note:** Platform API discovery is NOT supported in v1. No API calls are made. Discovery is entirely file-based (Terraform + repo + billing).

---

## Phase Status State Machine

### Valid Transitions

```
pending → in_progress → completed
```

Status NEVER goes backward under normal operation. Only an **unrecoverable error** reverts the current phase to `pending`.

### Phase Gate Rules (Fail Closed)

**Rule 1 — Predecessor gate:** A phase may transition to `in_progress` ONLY when its immediate predecessor phase has status `completed`. The ordered phase list is:

```
discover → clarify → design → estimate → generate
```

- `discover` has no predecessor — it may always start.
- `clarify` requires `phases.discover == "completed"`.
- `design` requires `phases.clarify == "completed"`.
- `estimate` requires `phases.design == "completed"`.
- `generate` requires `phases.estimate == "completed"`.

If the predecessor is not `completed`, emit:

```
GATE_FAIL | phase=<target_phase> | field=phases.<predecessor> | reason=missing
```

Do NOT advance. Do NOT modify `.phase-status.json`. Tell the user which prior phase must complete first.

**Rule 2 — Single active phase:** At most one core phase (discover, clarify, design, estimate, generate) may be `in_progress` at any time. If another phase is already `in_progress`, emit:

```
GATE_FAIL | phase=<target_phase> | field=phases.<active_phase> | reason=invalid
```

**Rule 3 — GATE_FAIL halt behavior:** When any handoff gate check fails at phase completion:

1. Retain the failing phase's status as `in_progress` — do NOT revert it.
2. Do NOT advance `current_phase`.
3. Do NOT modify any artifacts to force the gate to pass.
4. Surface a diagnostic to the user identifying:
   - The phase that failed (`phase=<name>`)
   - The specific field or artifact that failed (`field=<dotted.path>`)
   - The failure reason (`reason=missing|invalid|stale_downstream`)
5. Tell the user: "Re-run Phase N (phase name) to produce the missing field, then continue."

**Rule 4 — Unrecoverable error behavior:** When a phase fails during execution due to an unrecoverable error (e.g., no Heroku sources found, corrupted state file, critical sub-discovery failure that blocks all outputs):

1. Revert that phase's status to `pending` in `.phase-status.json`.
2. Preserve all artifacts and status values from prior completed phases — do NOT touch them.
3. Surface a diagnostic to the user identifying:
   - The failed phase
   - The error category (e.g., `no_sources`, `state_corrupted`, `auth_failure`)
   - Actionable guidance on how to resolve

**Rule 5 — Phase re-entry:** See `shared/handoff-gates.md` re-entry table. Re-running a phase after downstream phases completed requires explicit user confirmation; downstream phases must be reset to `"pending"`.

---

## Step 0: Initialize Migration State

1. Check for existing `.migration/` directory at the project root.
   - **If existing runs found:** List them with their phase status and ask:
     - `[A] Resume: Continue with [latest run]`
     - `[B] Fresh: Create new migration run`
     - `[C] Cancel`
   - **If resuming:** Set `$MIGRATION_DIR` to the selected run's directory. Read its `.phase-status.json` and validate per the State Machine in SKILL.md. If `phases.discover` is already `completed`, check re-entry rules (Rule 5).
   - **If fresh or no existing runs:** Continue to step 2.

2. Create `.migration/[MMDD-HHMM]/` directory (e.g., `.migration/0315-1030/`) using current timestamp (MMDD = month/day, HHMM = hour/minute). Set `$MIGRATION_DIR` to this new directory.

3. Create `.migration/.gitignore` file (if not already present) with exact content:

   ```
   # Auto-generated migration state (temporary, do not commit)
   *
   !.gitignore
   ```

   This prevents accidental commits of migration artifacts.

4. Write `.phase-status.json` with exact schema:

   ```json
   {
     "migration_id": "[MMDD-HHMM]",
     "last_updated": "[ISO 8601 timestamp]",
     "current_phase": "discover",
     "phases": {
       "discover": "in_progress",
       "clarify": "pending",
       "design": "pending",
       "estimate": "pending",
       "generate": "pending",
       "feedback": "pending"
     }
   }
   ```

   Schema reference: `shared/schema-phase-status.md`.

5. Confirm both `.migration/.gitignore` and `.phase-status.json` exist before proceeding to Step 1.

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

**If NO Terraform files with `heroku_*` resources found** (regardless of whether Procfile/app.json exist):

1. Apply **unrecoverable error behavior** (Rule 4):
   - Revert `phases.discover` to `"pending"` in `.phase-status.json`.
   - Preserve all other phase statuses unchanged.
2. STOP and output: "No Terraform files with heroku_* resources found. Heroku Terraform is required for discovery. Procfile and app.json alone are not sufficient."

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

After all sub-discoveries complete, assemble `heroku-resource-inventory.json` in `$MIGRATION_DIR/`.

**Schema reference**: `shared/schema-discover-heroku.md` — consult for complete field definitions, per-type config schemas, and validation checklist.

### Assembly Rules

1. Merge all discovered resources into a flat array (no clustering, no dependency graphs).
2. Each resource entry MUST have: `resource_id`, `resource_type`, `heroku_app`, `config`.
3. Resources grouped by `heroku_app` field. Unassociable resources (spaces, pipelines) get `heroku_app: "unassociated"`.
4. Include `metadata` section: `discovery_timestamp`, `total_apps_discovered`, `discovery_sources`, `confidence`.
5. Include `apps[]` section with per-app entries containing:
   - `app_name`, `app_id`, `discovery_status` (success/discovery_failed), `failure_reason`
   - `heroku_generation` (cedar/fir/unknown), `generation_action` (always `detect_only`), `generation_diagnostics` (array of diagnostic reasons)
   - `space` (Private Space name or null)
   - `procfile_parse_warning`, `app_json_parse_warning` (per-app parse warnings or null)
6. Include `billing_profile` section (if billing data available, with `available`, `total_monthly_cost`, `currency`, `billing_period`, `line_items`).
7. Include `terraform_metadata` section (if Terraform discovery ran, with `found`, `tf_files_scanned`, `resource_types_extracted`, `parse_warnings`).
8. Verify NO forbidden fields exist: `cluster_id`, `creation_order_depth`, `edges`, `dependencies`, `must_migrate_together`.

**If assembly fails** (no valid resources from any source after sub-discoveries ran):

Apply **unrecoverable error behavior** (Rule 4):

- Revert `phases.discover` to `"pending"`.
- Preserve prior completed phases.
- STOP and output: "Discovery ran but produced no valid resources. Check that your input files contain valid Heroku resources and try again."

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

Load `shared/handoff-gates.md`. **Re-read from disk** every artifact below before checking.

**Re-entry guard:** If `preferences.json` exists AND `phases.clarify` is `"completed"`: STOP unless the user explicitly confirms re-running Discover. Emit:

```
GATE_FAIL | phase=discover | field=preferences.json | reason=stale_downstream
```

**Checks (all must PASS):**

1. `heroku-resource-inventory.json` exists with at least one resource entry.
2. Inventory metadata has `discovery_timestamp` and `total_apps_discovered` set.
3. Every resource in the `resources` array has `resource_id`, `resource_type`, `heroku_app`, and `config` fields.
4. No forbidden clustering fields present (`cluster_id`, `creation_order_depth`, `edges`, `dependencies`, `must_migrate_together`).
5. Route output gates from Step 4 all pass.

**On any FAIL:** Emit `GATE_FAIL | phase=discover | field=<path> | reason=<missing|invalid|stale_downstream>`. **Do NOT modify artifacts to pass the gate.** **Do NOT update `.phase-status.json`.** Tell the user which sub-discovery to re-run.

**On PASS:** Emit `HANDOFF_OK | phase=discover | artifacts=<comma-separated list of files verified>`.

---

## Step 5: Update Phase Status

Only after `HANDOFF_OK`. In the **same turn** as the output message below, use the Phase Status Update Protocol (read-merge-write) to update `.phase-status.json`:

1. Read current `.phase-status.json` from disk.
2. Set `phases.discover` to `"completed"`.
3. Set `current_phase` to `"clarify"`.
4. Update `last_updated` to current ISO 8601 timestamp.
5. Keep all other phase values unchanged.
6. Write the full file.

Output to user — build message from inventory contents:

- "Discovered X total resources across Y apps."
- If billing data available: "Parsed billing data ($Z/month)."
- If Terraform secondary: "Supplemented with Terraform-sourced resources (N conflicts resolved)."
- If Pipeline detected: "Detected N pipeline(s) (detect-only)."
- If Cedar/Fir mixed: "Generation detection: N Cedar, M Fir, P unknown."

Format: "Discover phase complete. [artifact summaries] Next required step: Phase 2 — Clarify. Load `references/phases/clarify/clarify.md` now. Do not load Design, Estimate, or Generate until Clarify completes and `.phase-status.json` marks `phases.clarify` as `completed`."

---

## Output Files

**Discover phase writes files to `$MIGRATION_DIR/`. Required outputs:**

1. `.phase-status.json` — phase tracking (initialized in Step 0, updated in Step 5)
2. `heroku-resource-inventory.json` — flat resource inventory

**Optional outputs (depending on available sources):**

- Billing profile embedded in inventory (not a separate file)

**No other files must be created:**

- No README.md
- No discovery-summary.md
- No EXECUTION_REPORT.txt
- No discovery-log.md
- No documentation or report files

All user communication via output messages only.

---

## Error Handling

| Error Category                                                 | Behavior                                       | Status Transition             |
| -------------------------------------------------------------- | ---------------------------------------------- | ----------------------------- |
| No Heroku Terraform files (no `.tf` with `heroku_*` resources) | STOP, surface diagnostic                       | Revert to `pending` (Rule 4)  |
| Terraform parse error (malformed HCL)                          | Log warning, skip malformed blocks, continue   | Continue `in_progress`        |
| Procfile/app.json parse error                                  | Record warning per-app, continue               | Continue `in_progress`        |
| Generation detection unresolvable (no stack attr)              | Set `heroku_generation` to `unknown`, continue | Continue `in_progress`        |
| Pipeline detection from Terraform incomplete                   | Record with available data, continue           | Continue `in_progress`        |
| All sub-discoveries produce no resources                       | STOP, surface diagnostic                       | Revert to `pending` (Rule 4)  |
| `.phase-status.json` invalid JSON                              | STOP, surface diagnostic                       | N/A (state corrupted)         |
| Handoff gate check fails (GATE_FAIL)                           | Halt pipeline, surface diagnostic              | Retain `in_progress` (Rule 3) |
| Downstream artifacts stale (re-entry)                          | Halt, emit GATE_FAIL stale_downstream          | Retain `in_progress` (Rule 3) |

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
