---
_phase: scaffold
_title: "Optional IaC Scaffold"
_kind: checkpoint
_requires_phase: report
_input:
  - recommendation.json
_knowledge:
  - { file: knowledge/peripheral-mappings.json, _when: "always - loaded by the peripherals fragment" }
  - { file: references/shared/graviton.md, _when: "always - loaded by whichever compute fragment fires, and by the peripherals fragment for a detected Cron" }
_trigger: { _when: "the founder opts in to a scaffold at the post-report checkpoint" }
_fragments:
  - _id: outcome-a
    _trigger: { _when: "recommendation.outcome is 'A', or 'C' with backend_shape 'A-shaped'" }
    _file: phases/scaffold/scaffold-opennext.md
  - _id: outcome-b
    _trigger: { _when: "recommendation.outcome is 'B', or 'C' with backend_shape 'B-shaped'" }
    _file: phases/scaffold/scaffold-fargate.md
  - _id: peripherals
    _trigger: { _always: true }
    _file: phases/scaffold/scaffold-peripherals.md
_assemble:
  _file: phases/scaffold/scaffold-assemble.md
_produces:
  - { file: "sst.config.ts", _when: "outcome-a fragment fired" }
  - { file: "terraform/", _when: "any fragment fired" }
  - { file: "terraform/README.md", _when: "the peripherals fragment always runs and always emits this" }
_preconditions:
  - _check_phase_completed: report
    _on_failure: _halt_and_inform
_postconditions:
  - _check_file_exists: "terraform/README.md"
    _on_failure: _warn_and_skip
_forbids_files:
  - "README.md"
---

# Checkpoint: Optional IaC Scaffold

Off-backbone checkpoint (`_kind: checkpoint`, no `_advances_to`) — entered only
when the founder opts in at the post-Report checkpoint (see `SKILL.md` §
Scaffold Checkpoint for the exact prompt). Returns control to the flow rather
than advancing `current_phase`; marking `phases.scaffold` `"completed"` means
the checkpoint was RESOLVED (offered and dealt with), not that the founder
necessarily participated — a declined offer is still `"completed"` (see
`INTERPRETER.md` § Backbone vs checkpoint, "Checkpoint status semantics").

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Determine Which Compute Fragment(s) Fire

Read `recommendation.json`. Determine which fragment(s) fire based on
`outcome` and (if `outcome == "C"`) `backend_shape`:

| `outcome`                                        | `backend_shape`                                                        | Fires                                                                                                                                                                             |
| ------------------------------------------------ | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `"A"`                                            | n/a                                                                    | `scaffold-opennext.md` only                                                                                                                                                       |
| `"B"`                                            | n/a                                                                    | `scaffold-fargate.md` only                                                                                                                                                        |
| `"C"`                                            | `"A-shaped"`                                                           | `scaffold-opennext.md` only, in its Outcome-C-recursion mode (Terraform-only backend, NEVER SST — see that fragment's own scope boundary)                                         |
| `"C"`                                            | `"B-shaped"`                                                           | `scaffold-fargate.md` only                                                                                                                                                        |
| `"C"`                                            | `["A-shaped", "B-shaped"]` (unresolved tiebreak carried into Scaffold) | Ask the founder to pick one before proceeding — Scaffold cannot emit both; if the founder declines to pick, do not fire either compute fragment, only `scaffold-peripherals.md`   |
| `"stay"`                                         | n/a                                                                    | Neither compute fragment fires; only `scaffold-peripherals.md` runs, if the founder still wants the thin peripheral-only carve-out mentioned in the report's out-of-scope section |
| `["A", "B"]` (top-level tiebreak never resolved) | n/a                                                                    | Same as the `backend_shape` tiebreak row above — ask the founder to pick before proceeding                                                                                        |

At most ONE of `scaffold-opennext.md` / `scaffold-fargate.md` ever fires in a
single Scaffold run — this is enforced structurally by the mutually exclusive
`_when` triggers in this phase's frontmatter, never by both firing and one
being discarded.

**Persisting a founder's tiebreak resolution (critical — do not skip):** the
fragment `_trigger._when` conditions above read `backend_shape`/`outcome`
directly from `recommendation.json` on disk — they do not know about a
choice the founder just made verbally at this checkpoint. If the founder
picks a shape (or a top-level outcome) to resolve an unresolved tiebreak,
you MUST update `recommendation.json` BEFORE proceeding to Step 2, or the
dispatch table above will re-evaluate against the stale unresolved array
every time and never converge:

1. Read the current `recommendation.json` (read-merge-write, same discipline
   as every other artifact write in this skill).
2. For a `backend_shape` tiebreak: set `backend_shape` to the founder's
   single chosen value (`"A-shaped"` or `"B-shaped"`), set
   `backend_tiebreak` to `false`, and set `backend_resolving_input` to
   `null` — per `vercel-recommendation-engine.md`'s own Constraints ("when
   `backend_tiebreak == true`, `backend_shape` is the 2-element array");
   once resolved to one value, `backend_tiebreak` MUST be `false`, never
   left `true` alongside a resolved single shape. Leave `outcome`,
   `fired_rule`, `separable`, `tiebreak`, and `resolving_input` untouched —
   this resolution is scoped to the backend level only.
3. For a top-level `outcome` tiebreak (the `["A", "B"]` array case): set
   `outcome` to the founder's single chosen value (`"A"` or `"B"`), set
   `tiebreak` to `false`, and set `resolving_input` to `null`.
4. Add one entry to `reasons` naming that this was a founder pick made at
   the Scaffold checkpoint (not a Discover/Recommend signal), so the
   decision traceability appendix — if the report is ever re-rendered after
   this point — can distinguish a checkpoint-time manual pick from an
   assessment-time finding.
5. If the founder DECLINES to pick: do NOT modify `recommendation.json` at
   all. Proceed directly to Step 3 (skip Step 2 entirely this run) — the
   unresolved array remains on disk exactly as Recommend left it, and a
   future Scaffold re-entry will correctly ask again.

---

## Step 2: Run the Compute Fragment (If One Fires)

Load whichever of `scaffold-opennext.md` / `scaffold-fargate.md` applies per
Step 1.

---

## Step 3: Run the Peripherals Fragment (Always)

Load `references/phases/scaffold/scaffold-peripherals.md`. This always runs
regardless of Step 1's outcome — even a `"stay"` recommendation may still want
a thin peripheral-only carve-out per the report's out-of-scope section.

---

## Step 4: Assemble

Load `references/phases/scaffold/scaffold-assemble.md` (the phase's
assembler) and follow it to combine fragment outputs, confirm Outcome C never
emits a Next.js hosting scaffold, and run the completion gate.

---

## Completion Gate (Warn, Not Halt — Scaffold Is Optional)

Per `scaffold.md`'s own `_postconditions`: `terraform/README.md`'s absence is
`_warn_and_skip`, not `_halt_and_inform` — Scaffold is optional output; a
partial or skipped scaffold does not block the migration from being
considered complete (the assessment + report already stand on their own).

---

## Step 5: Mark Checkpoint Resolved

Regardless of what fired (including "founder declined to pick between a
tiebreak" or "founder chose not to scaffold at all"), mark `phases.scaffold`
`"completed"` — the checkpoint is resolved either way. Do NOT set
`current_phase` — checkpoints never appear as a `current_phase` value.

---

## Error Handling

| Error Category                                            | Behavior                                                                                                                        |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `recommendation.json`'s outcome is an unresolved tiebreak | Ask the founder to pick before scaffolding; if declined, run only `scaffold-peripherals.md`                                     |
| Founder opts in but then wants to cancel mid-generation   | Stop, mark `phases.scaffold` `"completed"` anyway (resolved, not necessarily fully generated), note what was and wasn't written |

---

## Scope Boundary

**This checkpoint covers dispatching to the correct compute fragment (if any)
and the peripherals fragment ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Firing both `scaffold-opennext.md` AND `scaffold-fargate.md` in the same run
- Re-running the Recommendation Engine or any assessment phase
- Advancing `current_phase` (checkpoints never do)

**Your ONLY job: dispatch to the right fragment(s), assemble, mark resolved.
Nothing else.**
