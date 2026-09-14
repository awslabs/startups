---
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: estimate
_input:
  - aws-design.json
  - estimation-infra.json
  - preferences.json
  - azure-resource-inventory.json
_fragments:
  - _id: artifacts-infra
    _trigger: { _always: true }
    _file: phases/generate/generate-artifacts-infra.md
  - _id: artifacts-docs
    _trigger: { _always: true }
    _file: phases/generate/generate-artifacts-docs.md
  - _id: artifacts-report
    _trigger: { _always: true }
    _file: phases/generate/generate-artifacts-report.md
  - _id: artifacts-ai
    _trigger: { _when: "aws-design-ai.json exists in $MIGRATION_DIR AND run_mode is decide_and_execute" }
    _file: phases/generate/generate-artifacts-ai.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - terraform/main.tf
  - terraform/variables.tf
  - terraform/outputs.tf
  - terraform/.gitignore
  - terraform/terraform.tfvars.example
  - MIGRATION_GUIDE.md
  - README.md
  - migration-report.html
  - generation-warnings.json
  - validation-report.json
  - generation-ai.json
_advances_to: complete
_interactive: false
_exec:
  _agent: rw
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_phase_completed: workshop
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, estimation-infra.json, preferences.json, azure-resource-inventory.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, estimation-infra.json, preferences.json, azure-resource-inventory.json]
    _on_failure: _unrecoverable
  - _assert: "run_mode in .phase-status.json is 'decide_and_execute' — the user chose Execute at the post-Estimate decision gate, accepted the decide-complete resume offer, or explicitly asked for Terraform/migration scripts this turn. An absent run_mode is NOT consent."
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: [terraform/main.tf, terraform/variables.tf, terraform/outputs.tf, terraform/.gitignore, terraform/terraform.tfvars.example, MIGRATION_GUIDE.md, README.md, migration-report.html, generation-warnings.json, validation-report.json]
    _on_failure: _halt_and_inform
  - _validate_json: [generation-warnings.json, validation-report.json]
    _on_failure: _halt_and_inform
  - _assert: "validation-report.json (written by the MAIN-WINDOW validation step, not the rw worker) has status in {passed, passed_degraded_offline, skipped_user_continue} AND policy_status == POLICY_OK — unless the user chose skip/abort on a policy failure, in which case status may be policy_failed / policy_status POLICY_FAIL and the phase completes only by that explicit user choice. The tf-best-practices policy gate runs regardless of the offline path, so policy_status is never masked by passed_degraded_offline."
    _on_failure: _halt_and_inform
  - _assert: "terraform/main.tf has a valid provider configuration; terraform/variables.tf declares at least an aws_region variable"
    _on_failure: _halt_and_inform
  - _assert: "at least one domain .tf file exists beyond the core files"
    _on_failure: _halt_and_inform
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections; README.md lists the generated artifacts"
    _on_failure: _halt_and_inform
  - _assert: "migration-report.html leads with the cluster-level architecture rationale; the per-resource mapping table appears only in an appendix; a draft-for-review footer is present"
    _on_failure: _halt_and_inform
  - _assert: "if scenarios/index.json has at least 2 scenarios, migration-report.html includes the what-if comparison"
    _on_failure: _halt_and_inform
  - _assert: "every designed service is accounted for — generated, or listed in generation-warnings.json"
    _on_failure: _halt_and_inform
  - _assert: "no placeholder {{VARIABLE}} tokens remain in any .tf file; those belong in variables.tf as var.* references"
    _on_failure: _halt_and_inform
  - _assert: "no secret VALUE from the inventory appears in any generated artifact; secrets are emitted as Secrets Manager references"
    _on_failure: _halt_and_inform
  - _assert: "WHEN aws-design-ai.json exists AND run_mode is decide_and_execute: generation-ai.json exists and validates, its rollback_plan.mechanism is 'feature_flag' with flag_name 'AI_PROVIDER' and default_value 'azure_openai'; an ai-migration/ directory was produced (setup_bedrock.sh, test_comparison.py, bedrock_monitoring.tf on every path; migrate_to_mantle.sh for the mantle path OR provider_adapter.* for the direct/gpt-oss path, not both); and no proprietary openai.gpt-* model ID is paired with a converse/bedrock-runtime path. When aws-design-ai.json is absent this is vacuously satisfied"
    _on_failure: _halt_and_inform
_forbids_files:
  - azure-resource-inventory.json
  - azure-resource-clusters.json
  - preferences.json
  - aws-design.json
  - estimation-infra.json
---

# Phase 5: Generate Migration Artifacts

## Orientation

Emit the Terraform, the scripts, the docs, and the report. This phase runs under
`_exec: { _agent: rw }` with `_interactive: false` — the work is bulky, file-only,
and self-contained, so it runs in an isolated sub-agent while the gates, the state
transition, and the `HANDOFF_OK` stay in the main window.

**The Terraform validation, the `tf-best-practices` policy gate, and the
`validation-report.json` write also stay in the main window** — the dispatched `rw`
worker emits `terraform/` only; it cannot invoke skills or run `terraform`/`python`.
This mirrors gcp-to-aws's `generate.md`, which owns validation inline in its own main
window and passes only the terraform DIR to the skill (the caller owns the report). See
§ "Step: Run the phase" step 4.

## Generate is opt-in, and the check has no mechanical teeth

The `run_mode` precondition above is an `_assert`. **CI binds `_assert` bodies but
never evaluates them** — the string is checked for being a non-empty value in the
right list, and nothing more. So the consent rule depends entirely on the interpreter
honoring the prose. A future reader should not assume this is enforced.

The DSL has no vocabulary for an opt-in phase, and inventing one for a single case
would be worse than this: the alternative is a mechanical check that the state file
carries a specific value, which the grammar does not have a check kind for.
`estimate-assemble.md` owns writing `run_mode`, and it writes
`decide_and_execute` **before** this phase loads, so a session that dies mid-Generate
resumes as an Execute run.

The `_check_phase_completed: workshop` precondition is the other half of the ordering:
the `workshop` sidebar declares `_gates: generate`, and a declined sidebar counts as
resolved.

## Sequencing

Emit in tier order — network, identity, and secrets first, then data, then compute,
then edge. That is the same tiering the clusters carry, which is why the tiering
replaced topological depth: Generate's sequencing is what the ordering is *for*.

## Status — skeleton (build step 1)

Wiring only: three artifact fragments and an assembler, with the full artifact floor
and the postcondition contract declared.

| Lands in | What                                                             |
| -------- | ---------------------------------------------------------------- |
| step 6   | The Terraform, script, doc, and report emitters                   |
| step 6   | The report shape — cluster-level rationale first, rows to an appendix |
| step 6   | The AI handoff summary, when the handoff offer is accepted         |

## Step: Run the phase

Steps 2–3 are the phase's WORK and are dispatched to the file-only `rw` worker. Step 4
and step 5 run in the MAIN window — the worker cannot invoke skills or run
`terraform`/`python`.

1. Verify the entry gate, including `run_mode`.
2. Run each fragment whose `_trigger` holds. (worker)
3. Run `generate-assemble.md`. (worker — emits `terraform/`, the docs, the report, and
   `generation-warnings.json`; it does NOT validate or write `validation-report.json`.)
4. **Validate the generated Terraform and write the validation report — MAIN WINDOW,
   after the worker returns and before `_postconditions`.** This MUST run in the main
   window because the `rw` worker cannot invoke skills or run `terraform`/`python`. This
   phase is the **caller** of the `tf-best-practices` validation protocol, exactly as
   gcp-to-aws's `generate.md` owns validation inline in its main window:
   - Invoke the `tf-best-practices` skill for the post-writing validation context, passing
     `$MIGRATION_DIR/terraform` — the DIR only (the caller owns the report, just as gcp
     passes only the terraform DIR to the skill). Treat it as a black box: run the
     fmt/init/validate stages where available, and the zero-dependency policy checker,
     which **runs regardless of the offline path** (a provider-registry outage skips
     `terraform validate` but never the policy gate).
   - Apply fix-and-retry to the reported `violations[]` sites (budget 3), then run the
     retry/skip/abort prompt.
   - WRITE the single canonical report at `$MIGRATION_DIR/validation-report.json` — the two
     segments joined by a single `/` (slash-joined). Merge the skill's policy verdict into
     THAT file as `policy_status` (+ `policy_violations` on failure), recorded independently
     of the fmt/init/validate outcome so a policy failure is never masked by
     `passed_degraded_offline`. **Never** write a separate `policy-verdict.json`, and never
     pin the skill's raw verdict path as the report.
   - An unresolved `POLICY_FAIL` the user does not `skip`/`abort` sets `status: policy_failed`
     and blocks completion (the `_postconditions` `_assert`).
5. Evaluate `_postconditions`. On all-pass emit `HANDOFF_OK` and advance to
   `complete`; on any failure emit `GATE_FAIL` and stop.
