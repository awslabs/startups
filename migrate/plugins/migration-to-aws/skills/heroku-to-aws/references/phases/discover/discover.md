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
  - _assert: "metadata.discovery_sources reflects which sub-discoveries actually ran; if the terraform sub-discovery ran, resources[] contains at least one Terraform-sourced resource"
    _on_failure: _halt_and_inform
  - _assert: "if a billing/invoice file was present in the workspace, heroku-resource-inventory.json has a billing_profile section"
    _on_failure: _halt_and_inform
_forbids_files:
  - README.md
  - discovery-summary.md
  - "*.txt"
  - "terraform/**"
---

# Phase 1: Discover Heroku Resources

## Orientation

Inventory what exists on Heroku into a single flat `heroku-resource-inventory.json`
in `$MIGRATION_DIR/`. This phase is composed of FRAGMENTS (independent discoverers)
plus one ASSEMBLER, declared in the frontmatter `_fragments`/`_assemble` — the
interpreter runs each fragment whose `_trigger` is true (loading its `_file` only
then), then the assembler. Read each unit file for its own contract; this phase
owns only lifecycle + the cross-cutting `_postconditions`.

Two facts the contract can't express: Procfile/app.json parsing is integrated into
the terraform fragment (there is no standalone Procfile fragment) — when present
alongside Terraform, they supplement resource data with commands, buildpacks, and
declared add-ons. And Platform API discovery is NOT supported in v1: no API calls
are made, discovery is entirely file-based. Billing data, when present, is embedded
in `heroku-resource-inventory.json` (not a separate file); all user communication
is via output messages only (no report/log files).

---

## Handoff

After the interpreter emits `HANDOFF_OK | phase=discover`, build the user-facing
completion message from the inventory contents:

- "Discovered X total resources across Y apps."
- If billing data available: "Parsed billing data ($Z/month)."
- If Terraform secondary: "Supplemented with Terraform-sourced resources (N conflicts resolved)."
- If Pipeline detected: "Detected N pipeline(s) (detect-only)."
- If Cedar/Fir mixed: "Generation detection: N Cedar, M Fir, P unknown."

Format: "Discover phase complete. [artifact summaries] Next required step: Phase 2 — Clarify. Load `references/phases/clarify/clarify.md` now. Do not load Design, Estimate, or Generate until Clarify completes and `.phase-status.json` marks `phases.clarify` as `completed`."

---

## Error Handling

Non-fatal discovery errors and their handling (fatal source/gate failures are handled by `_preconditions`/`_postconditions` + `INTERPRETER.md` § `_on_error`):

| Error Category                                    | Behavior                                       |
| ------------------------------------------------- | ---------------------------------------------- |
| Terraform parse error (malformed HCL)             | Log warning, skip malformed blocks, continue   |
| Procfile/app.json parse error                     | Record warning per-app, continue               |
| Generation detection unresolvable (no stack attr) | Set `heroku_generation` to `unknown`, continue |
| Pipeline detection from Terraform incomplete      | Record with available data, continue           |

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
