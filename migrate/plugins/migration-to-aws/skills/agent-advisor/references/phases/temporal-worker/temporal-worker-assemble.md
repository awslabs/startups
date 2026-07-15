---
_assemble: assemble-temporal-worker
_of_phase: temporal-worker
_reads:
  - workflow/activity inventory + Tier 1/Tier 2 decisions + agent-session scoring (produced inline in temporal-worker.md)
_produces:
  - temporal-design.json
  - temporal-migration-plan.md
  - temporal-migration-report.html
---

# Temporal Worker — Assemble the migration plan

> **Assembler unit.** The Temporal Worker branch inventories workflows /
> activities / task queues, applies decision-refs/temporal.md (Way 1 vs 2, Tier 1
> polling per task queue, Tier 2 execution per Activity class — running the main
> scoring engine for agent-session classes), and writes `temporal-design.json`,
> then renders `temporal-migration-plan.md` + `temporal-migration-report.html`
> inline within `temporal-worker.md` (Steps 3–5). This unit records the
> artifact-level contract for the branch: it is the single creator of those
> three artifacts, and its postconditions (declared on the phase) are the
> branch's completion gate. This is a self-contained checkpoint branch —
> Workflow orchestration code is never rewritten. See `temporal-worker.md`
> § Steps 3–5, and Gate T (Step 5.7) which can hand off to the temporal-poc
> checkpoint.
