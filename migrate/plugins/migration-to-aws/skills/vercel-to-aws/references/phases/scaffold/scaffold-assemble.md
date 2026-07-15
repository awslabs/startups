---
_assemble: scaffold-assemble
_of_phase: scaffold
_reads:
  - outcome-a (sst.config.ts conditional, terraform/) - when fired
  - outcome-b (terraform/) - when fired
  - peripherals (terraform/, terraform/README.md) - always
_produces:
  - { file: "sst.config.ts", _when: "outcome-a fragment fired in full app-surface mode" }
  - { file: "terraform/", _when: "any fragment fired" }
---

# Scaffold Phase: Assembler

> Combines whichever compute fragment fired (at most one, per `scaffold.md`
> Step 1) with the always-run peripherals fragment's output into the final
> `terraform/` directory and, conditionally, `sst.config.ts`. Confirms Outcome
> C never emits a Next.js hosting scaffold, and runs the completion gate.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Confirm At-Most-One Compute Fragment Fired

Before merging, confirm that `scaffold-opennext.md` and `scaffold-fargate.md`
did NOT both fire in this run — this should be structurally impossible given
`scaffold.md`'s mutually exclusive `_when` triggers, but this assembler
double-checks as defense in depth. If somehow both produced output, this is a
BUG — halt and surface a diagnostic rather than merging both (merging would
risk emitting SST alongside a from-scratch Fargate stack, which is explicitly
forbidden).

---

## Step 2: Confirm Outcome C Never Gets a Next.js Hosting Scaffold (Requirement 8.4)

If `recommendation.json.outcome == "C"`: confirm NEITHER
`scaffold-opennext.md` (in full app-surface mode) NOR
`scaffold-fargate.md` (in full app-surface mode) contributed a Next.js hosting
scaffold. Only the BACKEND-ONLY modes of these fragments (per their own Step 0
mode determination) should have contributed anything, and their contribution
should be Terraform-only backend compute — never a Next.js app surface, never
`sst.config.ts`.

If this check fails (a Next.js hosting artifact somehow appeared under
Outcome C), this is a BUG — halt and surface a diagnostic. Do not silently
drop the offending artifact and proceed; that would hide a real defect in an
upstream fragment.

---

## Step 3: Merge Terraform Files

Combine the compute fragment's Terraform output (if any) with
`scaffold-peripherals.md`'s Terraform output into `$MIGRATION_DIR/terraform/`.
Ensure cross-references are correct (e.g. a peripheral's connection string
correctly wired into the compute stack's environment configuration, or into
`sst.config.ts` as a secret if Outcome A's full app-surface mode fired).

---

## Step 4: Write `sst.config.ts` (Conditional)

ONLY if `scaffold-opennext.md` fired in FULL APP-SURFACE MODE (i.e.
`recommendation.json.outcome == "A"`, not the Outcome-C backend-only mode):
write `$MIGRATION_DIR/sst.config.ts`.

In every other case (`outcome == "B"`, `outcome == "C"` in either
`backend_shape`, or `outcome == "stay"`), do NOT create this file at all —
its absence is itself meaningful and should never be papered over with an
empty or placeholder file.

---

## Completion Gate

Per `scaffold.md`'s own `_postconditions` (warn-and-skip, not halt-and-inform
— Scaffold is optional overall):

1. Check `$MIGRATION_DIR/terraform/README.md` exists.
   - **If it exists:** proceed.
   - **If it does NOT exist:** apply `_warn_and_skip` — record a warning that
     the scaffold's documentation is incomplete, but do NOT halt the phase or
     block the checkpoint from resolving. Scaffold is optional; a partial
     scaffold is still better than none, and the assessment + report already
     stand on their own regardless of Scaffold's outcome.

No `GATE_FAIL`/`HANDOFF_OK` emission is required here specifically because
this is a checkpoint's completion, not a backbone phase's — `scaffold.md`
Step 5 marks `phases.scaffold` `"completed"` directly after this assembler
runs, per the checkpoint-resolved semantics (`INTERPRETER.md` § Backbone vs
checkpoint).

---

## Scope Boundary

**This assembler covers merging Scaffold's fragments, confirming the Outcome
C / at-most-one-compute-fragment invariants, and the warn-not-halt completion
check ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Silently merging both compute fragments' output if both somehow fired (halt
  and surface instead)
- Creating a placeholder `sst.config.ts` when it should be absent
- Treating a missing `terraform/README.md` as a hard failure

**Your ONLY job: merge, confirm invariants, warn-check, done.**
