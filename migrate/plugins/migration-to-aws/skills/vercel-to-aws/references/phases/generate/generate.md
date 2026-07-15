---
_phase: generate
_title: "Generate Migration Artifacts"
_requires_phase: estimate
_advances_to: report
_input:
  - recommendation.json
  - estimation-infra.json
  - discovery.json
  - preflight-findings.json
  - coupling-score.json
  - clarify-answers.json
_knowledge:
  - { file: knowledge/peripheral-mappings.json }
  - { file: references/shared/graviton.md }
_fragments:
  - _id: baseline
    _trigger: { _always: true }
    _file: phases/generate/generate-baseline.md
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/generate/generate-terraform.md
  - _id: compute-opennext
    _trigger: { _when: "recommendation.json.outcome == 'A'" }
    _file: phases/generate/generate-opennext.md
  - _id: compute-fargate
    _trigger: { _when: "recommendation.json.outcome == 'B' OR (outcome == 'C' AND backend_shape == 'B-shaped')" }
    _file: phases/generate/generate-fargate.md
  - _id: compute-lambda
    _trigger: { _when: "recommendation.json.outcome == 'C' AND backend_shape == 'A-shaped'" }
    _file: phases/generate/generate-lambda.md
  - _id: peripherals
    _trigger: { _always: true }
    _file: phases/generate/generate-peripherals.md
  - _id: scripts
    _trigger: { _always: true }
    _file: phases/generate/generate-scripts.md
  - _id: docs
    _trigger: { _always: true }
    _file: phases/generate/generate-docs.md
_assemble:
  _file: phases/generate/generate-assemble.md
_produces:
  - terraform/main.tf
  - terraform/variables.tf
  - terraform/outputs.tf
  - terraform/baseline.tf
  - terraform/vpc.tf
  - terraform/security.tf
  - terraform/.gitignore
  - terraform/terraform.tfvars.example
  - terraform/README.md
  - MIGRATION_GUIDE.md
  - README.md
  - generation-warnings.json
_interactive: false
_exec:
  _agent: rw
_preconditions:
  - _check_phase_completed: estimate
    _on_failure: _halt_and_inform
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _check_file_exists: [recommendation.json, estimation-infra.json, discovery.json, preflight-findings.json, clarify-answers.json]
    _on_failure: _unrecoverable
  - _validate_json: [recommendation.json, estimation-infra.json, discovery.json, preflight-findings.json, clarify-answers.json]
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [terraform/main.tf, terraform/variables.tf, terraform/outputs.tf, terraform/baseline.tf, terraform/vpc.tf, terraform/security.tf, terraform/.gitignore, terraform/terraform.tfvars.example, terraform/README.md, MIGRATION_GUIDE.md, README.md, generation-warnings.json]
    _on_failure: _halt_and_inform
  - _assert: "terraform/main.tf has valid provider configuration with hashicorp/aws ~> 5.80; terraform/variables.tf declares at least aws_region, project_name, environment, migration_id"
    _on_failure: _halt_and_inform
  - _assert: "at least one compute domain .tf file exists (compute.tf or cdn.tf) beyond the core files, OR recommendation.outcome is 'stay'"
    _on_failure: _halt_and_inform
  - _assert: "at most ONE of compute-opennext, compute-fargate, compute-lambda fired — mutual exclusion"
    _on_failure: _halt_and_inform
  - _assert: "MIGRATION_GUIDE.md has Prerequisites and Verification sections; README.md lists the artifacts"
    _on_failure: _halt_and_inform
  - _assert: "no placeholder {{VARIABLE}} tokens remain in Terraform .tf files (all configurable values use var.* references)"
    _on_failure: _halt_and_inform
  - _assert: "every service from estimation-infra.json is accounted for (generated or listed in generation-warnings.json)"
    _on_failure: _halt_and_inform
_forbids_files:
  - recommendation.json
  - estimation-infra.json
  - discovery.json
  - preflight-findings.json
  - coupling-score.json
  - clarify-answers.json
  - assessment-state.json
---

# Phase: Generate Migration Artifacts

**Execute ALL steps in order. Do not skip or optimize.**

Transform the recommended architecture and cost estimate into deployable
Terraform configurations, migration scripts, and documentation.

---

## Step 0: Validate Prerequisites

The entry gate (estimate completed, single active phase, all inputs present +
valid JSON) is enforced by this phase's `_preconditions` frontmatter per
`INTERPRETER.md` § Gate protocol; proceed once it passes.

---

## Step 1: Generate Security Baseline

Load `references/phases/generate/generate-baseline.md` and execute completely.
This always runs regardless of recommendation outcome — `baseline.tf` is
workload-independent.

---

## Step 2: Generate Core Terraform

Load `references/phases/generate/generate-terraform.md` and execute completely.
Produces `main.tf`, `variables.tf`, `outputs.tf`, `vpc.tf`, `security.tf`,
`.gitignore`, and `terraform.tfvars.example`.

---

## Step 3: Generate Compute (Outcome-Dependent)

Exactly ONE of the following fires based on `recommendation.json.outcome`:

- **Outcome A**: Load `references/phases/generate/generate-opennext.md`
- **Outcome B** (or C with B-shaped backend): Load
  `references/phases/generate/generate-fargate.md`
- **Outcome C with A-shaped backend**: Load
  `references/phases/generate/generate-lambda.md`
- **Outcome "stay"**: No compute fragment fires (baseline + peripherals only)

If `recommendation.json.outcome` is the unresolved tiebreak array `["A", "B"]`,
ask the founder to pick before proceeding — the generate phase cannot emit both.

---

## Step 4: Generate Peripheral Resources

Load `references/phases/generate/generate-peripherals.md` and execute
completely. This always runs — maps detected peripherals to Terraform resources.

---

## Step 5: Generate Migration Scripts

Load `references/phases/generate/generate-scripts.md` and execute completely.
This always runs — produces numbered migration scripts in `scripts/`.

---

## Step 6: Generate Documentation

Load `references/phases/generate/generate-docs.md` and execute completely.
This always runs — produces `terraform/README.md`, `MIGRATION_GUIDE.md`, and
`README.md`.

---

## Step 7: Assemble and Validate

Load `references/phases/generate/generate-assemble.md` (the phase's assembler)
and follow it to validate the complete artifact set, confirm mutual exclusion,
write `generation-warnings.json`, run the completion handoff gate, and update
`.phase-status.json`.

---

## Scope Boundary

**This phase covers artifact generation ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-running the Recommendation Engine or changing the outcome
- Re-estimating costs (Phase 5 estimates are final)
- Asking additional clarification questions (Phase 3 is done)
- Re-discovering Vercel resources (Phase 2 is done)

**Your ONLY job: Transform the design into deployable artifacts. Nothing else.**
