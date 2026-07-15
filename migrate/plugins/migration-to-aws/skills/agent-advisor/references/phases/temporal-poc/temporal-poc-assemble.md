---
_assemble: assemble-temporal-poc
_of_phase: temporal-poc
_reads:
  - connection target from temporal-design.json + the smoke-worker deliverables (written inline in temporal-poc.md)
_produces:
  - temporal-poc/poc-report.html
---

# Temporal Worker POC — Assemble the smoke-worker POC

> **Assembler unit.** The Temporal POC checkpoint reads the connection target
> from `temporal-design.json` and generates the smoke-worker deliverables under
> `temporal-poc/` (smoke_worker.py, Dockerfile, ecs-poc.tf, run_local.sh,
> deploy.sh, README) per poc-shapes.md's "Temporal worker POC", then renders
> `temporal-poc/poc-report.html` inline within `temporal-poc.md` (Steps 2–4).
> This unit records the artifact-level contract for the checkpoint: it is the
> single creator of the HTML report, and its postconditions (declared on the
> phase) are the checkpoint's completion gate. The POC proves task pickup
> (worker polls the user's server, runs one smoke workflow) — it never migrates
> the user's workflows and never touches production task queues. See
> `temporal-poc.md` § Steps 1–4 and poc-shapes.md § "Temporal worker POC".
