# Run seeds for this fixture

Each `*.seed.json` here is one benchmark scenario: the machine-readable answers a non-interactive
run needs, validated against `skills/agent-advisor/scripts/schemas/seed.json`.

Stage a seed by copying it to the run root the skill looks in:

```bash
mkdir -p .agent-advisor && cp seeds/default.seed.json .agent-advisor/seed.json
```

`.agent-advisor/` is gitignored (it holds run output), which is why the seeds live here and are
copied in at staging time rather than committed in place.

## Why a seed and not just `CLAUDE.md`

`CLAUDE.md` is prose: it describes the workload well, but the agent has to *interpret* it into
Clarify's enum values, and that interpretation is not deterministic. Measured on this fixture with
no seed — same repo, same prose, same deterministic engine:

| Run | agentcore | lambda_microvms |
| --- | --- | --- |
| local rehearsal | 41 | 39 |
| platform run 1 | 43 | 38 |
| platform run 3 | 44 | 41 |

Same verdict every time (`agentcore`), different margins — because the dimensions `CLAUDE.md` does
not state (`isolation`, `idle_resume`, `deployment_preference`) were re-derived on each run. The
seed pins them, so a repeated run is byte-comparable.

`CLAUDE.md` stays useful for context and boundaries; it just no longer carries the job of supplying
enum values.

| Seed | Scenario |
| --- | --- |
| `default.seed.json` | The documented Scenario A: existing Anthropic Messages-API agent, technical audience, Messages continuity, both gates declined, no target AWS account (`probe: decline`). Expected verdict `agentcore`; expected model path `mantle_messages` / `anthropic.claude-sonnet-5` (asserted by `scripts/check_recommendation.py default`). |

## Measured with the seed

Six runs of the ATX bundle over this fixture, same seed, three at a time in parallel (2026-08-04;
`advisor/` = `mise run atx:build` output). Runs 1-3 exposed two drift causes, runs 4-6 confirm the
fixes:

| | Runs 1-3 | Runs 4-6 |
| --- | --- | --- |
| `scoring-result.json` | **byte-identical** (sha256 `0fcf9967…`) | **byte-identical** — same digest, so the fixes changed nothing about the score |
| verdict | `co_recommend` over agentcore 40 / lambda_microvms 38, ecs 28, eks 24 | unchanged |
| seeded `region` shape | reshaped in 1 of 3 | object preserved in 3 of 3 |
| scoring dimensions | 2 of 3 agreed | 3 of 3 agreed |
| model decision | identical: `mantle_messages` / `anthropic.claude-sonnet-5` | identical |
| `detected` features | 11 / 11 / 10, two of them false positives | 10 / 10 / 10, the same 10 |
| `blocks` / `tuning` / `deltas` | 7/3/7, 8/2/8, 7/2/7 | 7/2/7 in all three |

The margins stopped moving, which was the point — compare the three-way spread in the table above.
The residues all had causes worth fixing, and all are fixed in the skill rather than in the seed:

- **The seeded `region` object was reshaped** into `region` + `regions` siblings — same values,
  different shape. That violates "a seeded value is copied verbatim", so `clarify.md` Step 2.5 now
  says it outright, and the postcondition names both seed lookup locations instead of only
  `$RUN_DIR/seed.json` (the reason the rule read as inapplicable: this fixture's seed lives at the
  run root).
- **The source scan disagreed on two features** — one run marked `structured_output` `detected` with
  no such call in `src/`, another marked `tokenizer_rebaseline` `detected` though nothing counts
  tokens. Those false positives are what moved the findings counts. `model-recommend.md` Step 3 now
  requires a citable source location for `detected`, with `absent` as the status for anything not
  citable.
- **`source_paths` listed evidence files as call sites** — two runs listed the two files that call
  the SDK, one also listed `tools.py` and `agent-capabilities.json`. Step 1 now defines the field as
  call sites only, sorted.

A seed cannot pin the source scan, and should not: reading the repository is the work being graded.
`agent-capabilities.json` in this fixture is the answer key for what the scan ought to find
(`server_tools`, `files_api`, `message_batches`, `prompt_caching`, MCP connectors) — a scan that
misses those, or claims a feature this app does not use, is the thing to grade.
