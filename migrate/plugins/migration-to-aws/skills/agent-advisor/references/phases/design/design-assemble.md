---
_assemble: assemble-design
_of_phase: design
_reads:
  - scoring facts + Confirm choices + service cards (combined inline in design.md)
_produces:
  - design.json
---

# Design — Assemble design.json

> **Assembler unit.** The Design phase reads the scoring result and Confirm
> choices, loads the winning runtime's service card, refreshes volatile facts,
> runs the lock-in / I/O-wait / FedRAMP / region gates, and assembles the
> recommendation into `design.json` inline within `design.md` (Step 5). This
> unit records the artifact-level contract for the phase: it is the single
> creator of `design.json`, and its postconditions (declared on the phase) are
> the phase's completion gate. See `design.md` § Step 5 for the design.json shape
> (verdict, chosen_runtime, deployment_model, agentcore_services,
> model_recommendation, scores, eliminated, the gate notes, handoff_required).
