---
name: vercel-to-aws
description: "Assess and plan migrations from Vercel to AWS for Next.js applications. Triggers on: migrate from Vercel, Vercel to AWS, move off Vercel, migrate Next.js off Vercel, assess my Vercel migration, Vercel migration assessment, leave Vercel, Vercel to Fargate, Vercel to OpenNext, estimate AWS costs for my Vercel app, Vercel coupling score, should I migrate off Vercel. Runs a pipeline of Pre-Scan, Full Discover (with Coupling Score and Pre-Flight Checks computed unconditionally), Clarify, Recommend (a fixed-precedence three-outcome engine: OpenNext/SST, ECS Fargate, or a Vercel+AWS Hybrid), Report (a validated HTML assessment), and an optional Scaffold checkpoint. Unlike GCP or Heroku sources, Vercel's infrastructure (CloudFront behaviors, Lambda tuning, edge routing) cannot be exported directly — it is derived from build output, source configs, and the Vercel REST API. Full cost estimation parity with the GCP skill is deferred to v2. Do not use for: GCP or Heroku migrations to AWS, AWS-to-Vercel reverse migration, general Next.js architecture advice without migration intent, or migrations to non-AWS targets (Cloudflare, a VPS) — those are acknowledged in the report's honesty paragraph but never built."
---

# Vercel-to-AWS Migration Skill

## Philosophy

- **Derive, don't discover.** Vercel's infrastructure is opaque and unexportable, but it is deterministic from inputs this skill CAN read: the build output, source configs, `vercel.json`, and the Vercel API. Next.js's Adapter API (stable since 16.2) emits a typed, versioned description of the app — routes, prerenders, runtime targets, caching rules, routing decisions — and Vercel's own adapter is open source on the same public contract. This is the highest-authority signal available; prefer it whenever the app qualifies (see Requirement 4.1 signal priority).
- **Assessment is the durable value, not scaffolding.** Execution (OpenNext, the future verified Adapter-API adapter) commoditizes over time. This skill's differentiation is the assessment/decision/clarify layer, not the Terraform/SST it optionally emits.
- **Honest by construction.** Every report states what the founder loses (preview deployments first), acknowledges non-AWS landing zones as rational for some segments (the out-of-scope paragraph), and carries explicit Confidence_Tier labels reflecting weaker evidence than the GCP skill's line-item billing triangulation. Never present a stub report as complete, and never let a recommendation imply more certainty than its inputs support.
- **Generation-aware.** Target OpenNext v3 for execution today. Structure the Scaffold phase so its backend-compute and peripheral logic sits behind an interface that can be swapped for the verified Adapter-API-based AWS adapter at its GA without touching assessment/discovery/recommendation logic.
- **Version upgrade is an offer, never a gate.** If the detected Next.js version is below 16.2, present upgrading as a confidence-upgrade offer (it unlocks the Adapter API's typed build output) — never as a migration prerequisite. The default path for a cost-driven founder is migrate now on OpenNext v3, whatever their current Next.js version.
- **Compute unconditionally, filter at render.** Coupling Score and all 10 named Pre-Flight Checks are computed during Discover, before Recommend has run — never gated on a recommendation that doesn't exist yet. The Report phase filters and reframes findings by the eventual outcome; if the founder later overrides the recommendation, the previously-computed-but-suppressed findings for that outcome are already on disk.
- **Precedence, not judgment.** The Recommendation Engine evaluates a fixed, ordered set of rules and stops at the first that fires (`references/shared/vercel-recommendation-engine.md`). It is not a model deciding case-by-case; every recommendation is traceable to exactly one rule.
- **Never a dialect mismatch.** SST/OpenNext is used ONLY for the Next.js app surface under Outcome A (and Outcome C's A-shaped backend recursion never triggers it — that recursion always emits Terraform). Outcome B and Outcome C never emit SST. This exception is documented inline wherever it appears, not left implicit.
- **Report is a rendering, not the deliverable's completion.** A failed report validation does not mean the assessment failed — the underlying findings and recommendation remain valid. The Report phase retries up to 2 additional times on validation failure, then surfaces the incomplete report and stops; it never presents a stub as done.

---

## Definitions

- **"Load"** = Read the file using the Read tool and follow its instructions. Do not summarize or skip sections.
- **`$MIGRATION_DIR`** = The run-specific directory under `.migration/` (e.g., `.migration/0315-1030/`). Set during Phase 1 (PreScan).
- **`assessment-state.json`** = The skill-owned resumability ledger living alongside `.phase-status.json` in `$MIGRATION_DIR`, tracking inputs received, per-finding confidence, and Clarify answers with their design consequence. It is independent of `.phase-status.json` — see `references/state/assessment-state.schema.json` and the Assessment State Management section below. It is NOT part of the vendored DSL contract; it is specific to this skill.

---

## Phase Structure (frontmatter)

Phase and unit files carry a YAML frontmatter block that declares how the phase is
composed — its inputs, the fragments it runs, the assembler that combines them,
what it produces, its gates, and what it requires/advances-to. The DSL interpreter
contract is the vendored `references/vendored/dsl/INTERPRETER.md`: it defines every
frontmatter key, the fragment/assembler model, and the interpreter loop. **Load it
first** (once, at the start of an assessment), then execute a phase file's prose
body. Elsewhere in this skill, `INTERPRETER.md` (without a path) refers to this
same loaded contract.

This skill is skill-AGNOSTIC infrastructure reused from `gcp-to-aws` and
`heroku-to-aws` — the interpreter itself defines no phases; the phase set,
ordering, and per-phase behavior below are all DERIVED from this skill's own
phase files' frontmatter.

---

## Context Loading Rules

Each phase loads reference files on demand. To keep per-turn context manageable and prevent instruction-following degradation:

- **Budget:** Each phase should load no more than ~800 lines of instructions (excluding user artifacts like JSON profiles and MCP tool results).
- **Conditional loading:** Reference files with trigger conditions MUST NOT be loaded unless the condition is met. Do not speculatively load files.
- **No duplication:** Mapping tables, pricing data, and shared warnings exist in one canonical file. Other files reference them; they do not copy them inline.
- **Progressive depth:** Phase orchestrators (`discover.md`, `recommend.md`) contain short routing logic that points to detailed sub-files. Load the sub-file only when its path is selected.

Each phase declares its own conditional reference/knowledge loads in frontmatter (a fragment `_trigger` or a `_knowledge` entry's `_when`); do not maintain a separate load-condition table here.

---

## Execution

This skill is driven by the interpreter loop in `INTERPRETER.md` (§ The interpreter
loop): it reads `.phase-status.json`, determines the current phase, runs each
phase's `_preconditions` / fragments / `_assemble` / `_postconditions`, advances on
`HANDOFF_OK` via `_advances_to`, and validates state. The phase set, ordering, and
gates are all derived from the phase files' frontmatter and `INTERPRETER.md` — they
are not restated here.

**Cold start (entry phase).** On a cold start — no `.migration/` run with a
`.phase-status.json` yet — begin at `references/phases/prescan/prescan.md`, this
skill's entry phase (the one carrying `_init: true`). The interpreter loads THIS
phase directly; it does not scan every phase's frontmatter to discover the root.
All subsequent phases are reached by following each phase's `_advances_to`. On a
warm start, `current_phase` in `.phase-status.json` is authoritative (see
`INTERPRETER.md` § The interpreter loop).

**Backbone:** `prescan` -> `discover` -> `clarify` -> `recommend` -> `report` -> `complete`.

**Checkpoint (off-backbone):** `scaffold`, entered only when the founder opts in after receiving the report (see § Scaffold Checkpoint below).

**Clarify is mandatory.** Do not skip Clarify or jump straight to Recommend even if
the founder asks — there is no exception for "quick" or "obvious" assessments. A
`clarify-answers.json` that was not produced by an actual Clarify run does not
count. If asked to skip, refuse briefly and run Clarify. (Clarify's question set is
short precisely because PreScan and Discover already answer what they can — see
`references/phases/clarify/clarify-ask.md`.)

**Next.js-upgrade is never a gate.** No phase, precondition, or postcondition in
this skill may treat the Clarify Next.js-upgrade answer as blocking progression to
Discover, Recommend, or Report. It is a confidence-upgrade offer only.

---

## State Management

Migration state lives in `$MIGRATION_DIR` (`.migration/[MMDD-HHMM]/`), created on
the first phase and persisted across invocations. Two state files coexist there,
read and written INDEPENDENTLY of each other:

1. **`.phase-status.json`** — the vendored, skill-agnostic phase tracker. Its shape
   is defined by `references/vendored/state/phase-status.schema.json`; how it is
   created, validated, and updated across the lifecycle is defined in
   `INTERPRETER.md` § The interpreter loop.
2. **`assessment-state.json`** — this skill's OWN resumability ledger (not part of
   the vendored DSL). Its shape is defined by
   `references/state/assessment-state.schema.json`. It tracks, per finding, which
   inputs it depends on (`computed_from_inputs`) so a re-invocation with a NEW
   input (e.g. a log drain export that didn't exist before) recomputes only the
   findings that input affects, leaving everything else untouched. See § Assessment
   State Management below for the read/recompute/write protocol.

A corrupt or missing `assessment-state.json` is NEVER treated as a corrupt or
missing `.phase-status.json`, and vice versa — validate and repair each
independently. The `.migration/` directory is protected by a `.gitignore` created
at `prescan`'s `_init` step (identical mechanism to the other two skills).

### Assessment State Management

On every phase that reads or writes `assessment-state.json` (`prescan`, `discover`,
`clarify`, `recommend`, `report`):

1. **Read before write.** Load the current `assessment-state.json` (if it exists)
   before making any change — never blind-overwrite.
2. **Recompute-on-new-input.** On a warm start, `prescan-collect.md` re-reads
   `inputs_received` and determines which Tier 2/3 inputs are NEWLY present since
   the last run (a `newly_received` list). `discover`'s fragments each carry a
   short-circuit preamble (see `discover-coupling.md` / `discover-preflight.md`):
   for every finding they own, check whether `computed_from_inputs` intersects
   `newly_received`; if not, copy the finding's prior `value`/`confidence`/
   `computed_at` forward unchanged and skip recomputation for that finding only.
3. **`report_history` cap.** `report-assemble.md` appends one entry per successful
   report write and caps the array at the 5 most recent entries (FIFO eviction) —
   see that phase's `_postconditions`.
4. **Independence from `.phase-status.json`.** `_re_entry_guard` (the vendored
   stale-downstream mechanism) still operates purely at the `.phase-status.json`
   phase-completion level. Partial recompute inside `assessment-state.json` happens
   INSIDE an already-`completed` phase's confirmed re-entry — it does not replace
   or interact with `_re_entry_guard`'s all-or-nothing phase reset.

---

## Scaffold Checkpoint

The interpreter loop drives phase sequencing, gates, and state. This section
defines only the Vercel-specific checkpoint orchestration: WHERE the optional
`scaffold` checkpoint is offered (a checkpoint's placement is orchestration prose,
not part of the phase contract).

- **After Report** (once `assessment-report.html` passes validation): Output to
  the founder:

  ```
  ─── Optional: Generate IaC Scaffold ───

  Based on the recommended outcome, I can generate a thin working skeleton:
  ✓ Wires in the Pre-Flight Check remediations already identified (tag cache +
    revalidation queue together, CloudFront header mappings, etc.)
  ✓ Uses the dialect appropriate to your outcome (SST + Terraform for OpenNext,
    Terraform-only for Fargate or the Hybrid path)
  ✗ Not production-hardened — a working skeleton, not a finished deployment

  [A] Generate scaffold now
  [B] No thanks, I have the assessment
  ```

  - If the founder picks **A** -> Load `references/phases/scaffold/scaffold.md`,
    execute it. Set `phases.scaffold` to `"completed"` once resolved.
  - If the founder picks **B** -> Set `phases.scaffold` to `"completed"` (checkpoint
    RESOLVED, not participated — see `INTERPRETER.md` § Backbone vs checkpoint,
    "Checkpoint status semantics"). Migration is complete.

**Critical constraint**: Follow each phase reference file's workflow exactly. If
unable to complete a step, stop and report the specific issue. Do not fabricate or
infer data — every finding traces to an actual signal, and every sub-HIGH
Confidence_Tier names the specific missing input that would upgrade it.

---

## Files in This Skill

```
vercel-to-aws/
├── SKILL.md                                    ← You are here (skill entry point)
│
├── references/
│   ├── phases/
│   │   ├── prescan/
│   │   │   ├── prescan.md                      # Phase 1: PreScan orchestrator (_init: true)
│   │   │   ├── prescan-collect.md              # Tier 1 input collection + preconditions
│   │   │   ├── prescan-scan.md                 # Build-free workspace/API scan
│   │   │   └── prescan-assemble.md             # tier1-signals.json + assessment-state.json seed
│   │   ├── discover/
│   │   │   ├── discover.md                     # Phase 2: Discover orchestrator
│   │   │   ├── discover-capture.md             # Main-window capture pre-work (build + GET-only API + probe; holds the token)
│   │   │   ├── discover-adapter.md             # Adapter API build-capture parsing (Next >= 16.2, clean build)
│   │   │   ├── discover-manifests.md           # .next manifest-capture fallback parsing (Next < 16.2)
│   │   │   ├── discover-configs.md             # next.config.js, middleware.ts, vercel.json
│   │   │   ├── discover-api.md                 # Vercel API capture parsing (env NAMES only)
│   │   │   ├── discover-probe.md               # Header-probe capture parsing (Tier 2 only)
│   │   │   ├── discover-coupling.md            # Coupling Score (unconditional)
│   │   │   ├── discover-preflight.md           # 10 named Pre-Flight Checks (unconditional)
│   │   │   └── discover-assemble.md            # discovery.json / coupling-score.json / preflight-findings.json
│   │   ├── clarify/
│   │   │   ├── clarify.md                      # Phase 3: Clarify orchestrator (interactive)
│   │   │   ├── clarify-ask.md                  # Fixed question set, PreScan/Discover-aware skip logic
│   │   │   └── clarify-assemble.md             # clarify-answers.json
│   │   ├── recommend/
│   │   │   ├── recommend.md                    # Phase 4: Recommend orchestrator
│   │   │   ├── recommend-rules.md              # Thin dispatcher to vercel-recommendation-engine.md
│   │   │   └── recommend-assemble.md           # recommendation.json
│   │   ├── report/
│   │   │   ├── report.md                       # Phase 5: Report orchestrator
│   │   │   ├── report-render.md                # HTML rendering, outcome-filtered findings
│   │   │   └── report-assemble.md              # Validator invocation, retry-cap loop, report_history
│   │   └── scaffold/
│   │       ├── scaffold.md                     # Checkpoint: Scaffold orchestrator
│   │       ├── scaffold-opennext.md            # Outcome A (or C's A-shaped backend): SST + Terraform
│   │       ├── scaffold-fargate.md             # Outcome B (or C's B-shaped backend): Terraform only
│   │       ├── scaffold-peripherals.md         # Peripheral mappings, always runs
│   │       └── scaffold-assemble.md            # terraform/, sst.config.ts (conditional)
│   │
│   ├── shared/
│   │   ├── vercel-recommendation-engine.md     # The precedence-rule decision table (§7 of requirements.md)
│   │   └── graviton.md                         # ARM64 default for Scaffold compute (SST/Terraform mechanics)
│   │
│   ├── state/
│   │   └── assessment-state.schema.json        # Skill-owned; NOT vendored (no canonical source elsewhere)
│   │
│   └── vendored/                               # synced from skills/shared/, same as heroku-to-aws
│       ├── README.md
│       ├── dsl/INTERPRETER.md
│       └── state/phase-status.schema.json
│
├── knowledge/
│   ├── preflight-checks.json                   # M1/M2/B1-B4/S1/I1/O1/U1 definitions
│   ├── coupling-weights.json                   # Coupling Score item weights + detection methods
│   └── peripheral-mappings.json                # Vercel peripheral -> AWS target table
```

## Error Handling

| Condition                                                  | Action                                                                                                                   |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `.phase-status.json` missing phase gate                    | Stop. Output: "Cannot enter Phase X: Phase Y-1 not completed. Start from Phase Y or resume Phase Y-1."                   |
| `assessment-state.json` missing or corrupt                 | Treat independently of `.phase-status.json` — see § State Management. Do not block on a `.phase-status.json` re-read.    |
| No Tier 1 inputs available                                 | `prescan`'s `_preconditions` fails `_unrecoverable`. Stop. Tell the founder which of the three Tier 1 inputs is missing. |
| `next build` does not run clean                            | Record as a finding (build health), not a precondition failure — proceed with discovery on remaining signals.            |
| Founder asks to skip Clarify                               | Refuse briefly; explain Clarify's question set is already minimized by PreScan/Discover skip logic. Run Clarify.         |
| Report validator exits with a code other than 0 or 1       | Validator did not run. Tell the founder; never treat as pass. Do not rename or delete the HTML file.                     |
| Report validator retry cap (2 additional attempts) reached | Surface the incomplete report and its failures. Stop. Do not present the stub as complete.                               |

## Defaults

- **IaC output (Scaffold only, when opted in)**: SST + Terraform (Outcome A), Terraform only (Outcome B, Outcome C)
- **Region**: `us-east-1` (unless the founder specifies otherwise)
- **Migration mode**: Adapts based on available inputs (Tier 1 required; Tier 2/3 optional and incrementally upgrade confidence)
- **Cost currency**: USD, always labeled "estimated monthly cost/savings"
- **Execution target**: OpenNext v3 (swappable for the verified Adapter-API AWS adapter behind an interface once it reaches GA)

**Critical constraint**: Follow each phase reference file's workflow exactly. If unable to complete a step, stop and report the specific issue. Do not fabricate or infer data.
