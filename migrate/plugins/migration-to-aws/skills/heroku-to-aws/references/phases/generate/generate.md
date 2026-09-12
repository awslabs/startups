---
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: estimate
_input:
  - aws-design.json
  - estimation-infra.json
  - preferences.json
  - heroku-resource-inventory.json
_fragments:
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/generate/generate-terraform.md
  - _id: docs
    _trigger: { _always: true }
    _file: phases/generate/generate-docs.md
  - _id: report
    _trigger: { _always: true }
    _file: phases/generate/generate-report.md
  - _id: eks-generate
    _trigger: { _when: "aws-design.json has an eks_cluster entry OR a service with aws_service == 'EKS'" }
    _file: phases/generate/generate-eks.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - terraform/main.tf
  - terraform/baseline.tf
  - terraform/variables.tf
  - terraform/outputs.tf
  - terraform/security.tf
  - terraform/.gitignore
  - terraform/terraform.tfvars.example
  - MIGRATION_GUIDE.md
  - README.md
  - migration-report.html
  - generation-warnings.json
  - validation-report.json
_advances_to: complete
_interactive: false
_exec:
  _agent: rw
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [aws-design.json, estimation-infra.json, preferences.json, heroku-resource-inventory.json]
    _on_failure: _unrecoverable
  - _validate_json: [aws-design.json, estimation-infra.json, preferences.json, heroku-resource-inventory.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [terraform/main.tf, terraform/baseline.tf, terraform/variables.tf, terraform/outputs.tf, terraform/security.tf, terraform/.gitignore, terraform/terraform.tfvars.example, MIGRATION_GUIDE.md, README.md, migration-report.html, generation-warnings.json, validation-report.json]
    _on_failure: _halt_and_inform
  - _assert: "terraform/main.tf has valid provider configuration; terraform/variables.tf declares at least an aws_region variable"
    _on_failure: _halt_and_inform
  - _assert: "terraform/baseline.tf contains a locals block with cloudtrail_retention_days set to a positive integer, plus aws_account_alternate_contact resources for each of operations, billing, and security, aws_iam_account_password_policy, aws_s3_account_public_access_block, aws_ebs_encryption_by_default, aws_accessanalyzer_analyzer, aws_ec2_instance_metadata_defaults, aws_cloudtrail with its log bucket, aws_budgets_budget, and aws_guardduty_detector"
    _on_failure: _halt_and_inform
  - _assert: "terraform/baseline.tf has the Compliance-Conditional section (aws_config_* recorder/delivery/status, aws_securityhub_account, FSBP standards subscription) exactly when the normalized preferences compliance array contains soc2, pci, hipaa, or fedramp; a PCI DSS standards subscription exists only when it contains pci; no NIST 800-53 standards subscription exists regardless of compliance values"
    _on_failure: _halt_and_inform
  - _assert: "terraform/variables.tf declares operations_email, billing_email, and security_email with no defaults and placeholder-rejecting validation blocks, and terraform/terraform.tfvars.example lists all three with TODO placeholders"
    _on_failure: _halt_and_inform
  - _validate_json: [validation-report.json]
    _on_failure: _halt_and_inform
  - _assert: "validation-report.json has $schema 'validation-report/v2' and its policy_status is 'POLICY_OK' (reconciled by the main-window 'Finish Generate' policy step that runs BEFORE this gate; a worker-written not_run placeholder is never accepted). POLICY_FAIL or not_run fails closed. This gate is READ-ONLY: do not run the checker, edit .tf, or edit the verdict here."
    _on_failure: _halt_and_inform
  - _assert: "at least one domain .tf file exists beyond the core files"
    _on_failure: _halt_and_inform
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections; README.md lists the artifacts"
    _on_failure: _halt_and_inform
  - _assert: "migration-report.html has decision-summary, exec-costs, next-steps, and draft-for-review footer; if scenarios/index.json has ≥2 scenarios, also what-if-scenarios"
    _on_failure: _halt_and_inform
  - _assert: "if Postgres is in the design, scripts/migrate-postgres.sh exists; if Redis is in the design, scripts/migrate-redis.sh exists"
    _on_failure: _halt_and_inform
  - _assert: "if EKS is in the design, terraform/eks.tf exists WITH cluster + node group resources, AND a kubernetes/ directory has namespace + deployment manifests"
    _on_failure: _halt_and_inform
  - _assert: "if Elastic Beanstalk is in the design, terraform/beanstalk.tf exists; if preferences.design_constraints.eb_deploy_method.value is github_actions or absent, .github/workflows/deploy-eb.yml exists; if codepipeline, terraform/pipeline.tf exists; if manual, no automated deploy artifact is required"
    _on_failure: _halt_and_inform
  - _assert: "for every Elastic Beanstalk web service, terraform/variables.tf declares required per-app eb_application_port_<app>_web and eb_health_check_path_<app>_web string variables with no defaults and basic validation, and terraform/beanstalk.tf passes them unchanged to that app's PORT and HealthCheckPath settings; non-web Elastic Beanstalk services do not require these web-only variables"
    _on_failure: _halt_and_inform
  - _assert: "every designed service is accounted for (generated or listed in generation-warnings.json)"
    _on_failure: _halt_and_inform
  - _assert: "no placeholder {{VARIABLE}} tokens remain in Terraform .tf files (those belong in variables.tf as var.* references)"
    _on_failure: _halt_and_inform
_forbids_files:
  - heroku-resource-inventory.json
  - preferences.json
  - aws-design.json
  - estimation-infra.json
---

# Phase 5: Generate Migration Artifacts

## Orientation

Transform the design + estimate into migration artifacts in `$MIGRATION_DIR/`: a
`terraform/` directory, `MIGRATION_GUIDE.md`, `README.md`, `migration-report.html`
(stakeholder summary + optional what-if scenarios), database migration scripts,
`generation-warnings.json`, and `validation-report.json` (the Terraform
validation + policy-gate verdict the main-window "Finish Generate" step
reconciles before the read-only completion gate reads it).
Terraform for each Elastic Beanstalk web service
is intentionally incomplete until the customer supplies that app's required
application port and health check path. Non-web Elastic Beanstalk services do not
require those web-only inputs. This is the multi-artifact phase.

Composed of the terraform + docs + report fragments + an EKS-generate fragment + one
cross-artifact validator assembler (declared in the frontmatter
`_fragments`/`_assemble`); the interpreter runs each fragment whose `_trigger` is
true, then the assembler. The `eks-generate` fragment is an ALTERNATIVE compute
path — it fires only when the design has an `eks_cluster` (its `_when` trigger),
emitting `eks.tf` + `kubernetes/` manifests. Templates are output skeletons
(`templates/generate/...`); the fragments are the routing algorithm. Read each unit
file for its own contract; the assembler owns the cross-artifact completion gate.

---

## Scope Boundary

**This phase covers artifact generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-designing or changing AWS service selections (Phase 3 decisions are final)
- Re-estimating costs (Phase 4 estimates are final)
- Asking the user additional clarification questions (Phase 2 is done)
- Discovering new Heroku resources (Phase 1 is done)
- Feedback collection (Phase 6 handles this)

**Your ONLY job: Transform the design into migration artifacts. Nothing else** — with one
main-window exception: running the Terraform policy checker and applying its `fix_hint`s to the
generated `terraform/` is part of _producing_ the artifacts (the dispatched worker had no shell
to do it), so the "Finish Generate" step below is in scope. Design/estimate decisions stay final.

---

## Finish Generate in the main window (policy reconcile) — BEFORE the gate

This is **leftover Generate work**, not a gate check: the dispatched `_exec._agent: rw` worker
has no shell (`INTERPRETER.md` § capability tiers — `rw` excludes Bash), so it could not run the
policy checker and left `policy_status: "not_run"`. The interpreter finishes that work in the MAIN
window (the only place with a shell), **after the worker returns and before running
`_postconditions`**. This step MAY edit `terraform/`; the `_postconditions` gate below MUST NOT
(per `INTERPRETER.md` § `_postconditions`, a gate never mutates artifacts to pass).

1. Run the policy checker against the generated Terraform (write the verdict to a temp sidecar):

   ```
   python3 "$PLUGIN_ROOT/skills/tf-best-practices/scripts/validate-terraform-policy.py" \
     "$MIGRATION_DIR/terraform" --json "$MIGRATION_DIR/validation-report.policy.json"
   ```

2. **On `POLICY_FAIL`, apply the fix-and-retry loop here (budget 3):** read `violations[]`, edit
   the named `.tf` sites via each `fix_hint`, re-run the checker. This is the ONLY place the
   `.tf` retry happens.

3. Merge the final verdict into `validation-report.json`: set `policy_status` +
   `policy_violations[]` from the last checker run, overwriting the worker's `not_run` placeholder.
   **Leave `status: "passed_degraded_offline"` and `offline_fallback_used: true`** — this step runs
   only the policy stage, never `terraform fmt/init/validate`, so claiming `status: "passed"` would
   be false; per the v2 schema the policy verdict is recorded independently of the offline status.
   Then **delete the `validation-report.policy.json` sidecar** (it is a temp input to the merge,
   not a second verdict artifact).

4. If the checker cannot run at all (no shell on the host), leave `policy_status: "not_run"`.

Then the `_postconditions` gate runs (read-only): `_validate_json` + the `policy_status ==
"POLICY_OK"` `_assert`. A residual `POLICY_FAIL` or `not_run` fails the assert → `GATE_FAIL`
(fail-closed: the gate never certifies a policy pass it could not confirm). The gate does not
edit anything.
