---
name: llm-to-bedrock
description: "Use when the user wants to migrate code that calls OpenAI, Gemini/Google AI, or the Anthropic API to Amazon Bedrock. End-to-end: assesses the codebase, then rewrites SDK calls, evaluates output quality against Bedrock, and delivers a ready-to-merge git branch. Not for standalone Bedrock cost estimates or infrastructure-only migration. Requires the migration-to-aws plugin for the Assess phase."
---

# Migrate to Bedrock (Assess + Execute)

Single-command AI migration: OpenAI / Gemini / Anthropic → Amazon Bedrock.

The skill base directory is given in the "Base directory for this skill: X" line the harness
emits at load time. Call it `<SKILL_BASE>`. Derived paths:

- `$SCRIPTS` = `<SKILL_BASE>/../../scripts`

---

## Step 0 — Check prerequisites

### 0a. Check that migration-to-aws plugin is installed

Check whether `migration-to-aws:gcp-to-aws` appears in your available-skills list (do NOT invoke it as a test — invoking loads the whole skill as a side effect). If it is not listed, tell the user:

> "This plugin requires the `migration-to-aws` plugin for the Assess phase.
> Install it with:
> ```
> /plugin install migration-to-aws@startups-for-aws
> ```
> Then re-run `/ai-to-aws:llm-to-bedrock`."

Stop and wait for the user to install it.

### 0b. Check that `uv` is available

```bash
uv --version 2>/dev/null || echo "MISSING"
```

If missing: "Install uv first: `curl -LsSf https://astral.sh/uv/install.sh | sh`". Stop.

---

## Step 1 — Collect source code path

If `$ARGUMENTS` contains a path, use it as `$REPO`. Otherwise use **AskUserQuestion**:
"Where is your source code? Enter a local path or GitHub URL."

If a GitHub URL, `git clone` it to a temp dir; use that path as `$REPO`.

**Checks on $REPO:**

1. **Git-root check** (compare resolved paths — on macOS `/tmp` resolves to `/private/tmp`,
   so a raw string comparison false-positives):
   ```bash
   [ "$(git -C <REPO> rev-parse --show-toplevel 2>/dev/null)" = "$(cd <REPO> && pwd -P)" ] && echo GIT_ROOT_OK || echo GIT_ROOT_MISMATCH
   ```
   - `GIT_ROOT_OK` → proceed.
   - `GIT_ROOT_MISMATCH` and the command errored (not a git repo at all) → tell the user the
     path must be a git repository (the deliverable is a git branch); re-ask.
   - `GIT_ROOT_MISMATCH` but inside a repo (user pointed at a subdirectory) → AskUserQuestion:
     "Use the repo root instead" (recommended) / "Continue with this subdirectory" / "Abort".

2. **Dirty-tree check:**
   ```bash
   git -C <REPO> status --porcelain
   ```
   If uncommitted changes exist, show them and AskUserQuestion: "Continue anyway" or "Let me clean up first".

Record `$REPO` for all subsequent steps.

---

## Phase A — Assess (MANDATORY: delegate to migration-to-aws plugin)

**CRITICAL: You MUST use the Skill tool to invoke `migration-to-aws:gcp-to-aws`. Do NOT perform
the Assess phase yourself. Do NOT read source code, detect AI SDKs, or ask Clarify questions
manually. The entire Assess phase is handled by the gcp-to-aws skill — you only invoke it and
wait for completion.**

### A1 — Invoke the Assess skill

Call the **Skill** tool with skill name `migration-to-aws:gcp-to-aws`.

Before invoking, tell the user:
> "I'm now invoking the migration-to-aws Assess skill to discover your AI workloads and design
> the Bedrock migration. It will ask you some questions — please answer them."

After invoking the Skill tool, the `gcp-to-aws` skill instructions will load into context.
Follow those instructions exactly — they will drive the Discover, Clarify, Design, Estimate,
and Generate phases. The source code to scan is at `$REPO`.

**Important context for the gcp-to-aws skill execution:**
- Source code is at `$REPO` — when the skill asks for GCP sources or scans for files, point it there
- This is an AI/LLM workload migration — the AI path is the goal
- Unless Terraform/IaC files are actually present in `$REPO`, skip IaC discovery
- Unless the user offers billing data, skip billing discovery

### A2 — Wait for Assess completion

The `gcp-to-aws` skill is a state machine. After each phase completes, it may stop and wait
for the next invocation. Check progress against the LATEST run directory only (older
`.migration/` runs may contain a stale "completed" status):

```bash
MIGRATION_DIR=$(ls -td "$REPO/.migration"/*/ 2>/dev/null | head -1)
python3 -c "import json,sys; print(json.load(open('$MIGRATION_DIR/.phase-status.json'))['phases'].get('generate','missing'))" 2>/dev/null || echo "no-status-file"
```

- `completed` → proceed to A3.
- Anything else (including `no-status-file`) → the skill needs to run again. Re-invoke
  `migration-to-aws:gcp-to-aws` via the Skill tool — it picks up where it left off.

**Cap: at most 6 re-invocations.** If `generate` is still not `completed` after 6, stop and
show the user the last status output — the Assess skill is stuck and needs manual attention;
looping further just burns context.

### A3 — Locate Assess output

Find `$MIGRATION_DIR` (the `.migration/<MMDD-HHMM>/` directory that was created):

```bash
ls -td "$REPO/.migration"/*/ 2>/dev/null | head -1
```

Verify these files exist in `$MIGRATION_DIR`:
- `aws-design-ai.json` (model mapping + architecture)
- `ai-workload-profile.json` (detected workloads)
- `preferences.json` (user preferences from Clarify)

If `aws-design-ai.json` is missing, Assess did not complete the AI path correctly. Show the
error and stop.

---

## Phase B — Execute Prep

### B1 — Read Assess outputs

Read `$MIGRATION_DIR/aws-design-ai.json` and extract:
- `ai_architecture.bedrock_models[]` → array of `{source_model, aws_model_id, use_case}`
- Collect all `aws_model_id` values into `$TARGET_MODELS` (array). Keep the `use_case` of each:
  the preflight script probes each model by the right API automatically (Converse for chat,
  InvokeModel for embeddings), but the evaluator's quality scoring only applies to chat models —
  embedding targets get format/dimension validation only.

Read `$MIGRATION_DIR/ai-workload-profile.json` and extract:
- `summary.ai_source` → source provider

Read `$MIGRATION_DIR/preferences.json` and extract:
- `design_constraints.target_region` → `$REGION` (default `us-east-1` if absent)

**Validation:** If `aws-design-ai.json` has no `ai_architecture.bedrock_models[]` array, or the
array is empty, STOP: "Assess output incomplete — model mapping missing."

### B2 — AWS identity confirmation

```bash
aws sts get-caller-identity 2>&1
```

**If the command fails** (no credentials, expired SSO token): show the error and tell the user
to run `aws configure` or `aws sso login` (suggest typing `! aws sso login` to run it in this
session), then re-run B2. Do not proceed without a confirmed identity.

On success, show Account, Arn, UserId via **AskUserQuestion**:
"This AWS identity will be used for Bedrock calls. Is this correct?"

Options:
- **Yes, use this identity** → proceed
- **Use a different AWS profile** → ask which profile, record it as `$AWS_PROFILE_CHOICE`,
  re-run B2 as `aws sts get-caller-identity --profile $AWS_PROFILE_CHOICE`, and re-confirm.
  **Do NOT rely on exporting `AWS_PROFILE`** — env vars do not persist across Bash tool calls
  or into workflow subagents (see B3). Instead pass the choice explicitly everywhere:
  `--profile` on every aws CLI call, and prepend `AWS_PROFILE=$AWS_PROFILE_CHOICE` inline on
  the B4 preflight command and inside the workflow args (`awsProfile` field) so subagents can
  do the same.

Also confirm region: "Bedrock region will be `$REGION`. OK or override?"

### B3 — Source API key (optional)

First, create the artifact directory and make it self-ignoring IMMEDIATELY — before any key
exists, so the secret is never sitting in an unignored working tree (even if the user aborts
before the rewriter runs):

```bash
mkdir -p "$REPO/.saws-migrate" && printf '*\n' > "$REPO/.saws-migrate/.gitignore"
```

Determine `$KEY_ENV_VAR` from B1's source provider (this is the env-var name the baseline
skill's parser expects — a bare key without the `NAME=` prefix will NOT be parsed):

- `openai` → `OPENAI_API_KEY`
- `anthropic` → `ANTHROPIC_API_KEY`
- `google` / `gemini` → `GEMINI_API_KEY`

**AskUserQuestion:** "Do you have an API key for the source model (e.g. OpenAI key for GPT-4o)?
Providing it enables side-by-side quality comparison. Without it, evaluation uses absolute scoring only."

Options:
- **Yes — I'll paste my key** → warn first: "Note: the key will pass through this chat
  transcript. If you prefer, choose 'I'll write it to a file myself' instead." Then a second
  AskUserQuestion to collect it (free-text via Other). Then write it in `KEY=VALUE` form:
  ```bash
  printf "%s=%s\n" "$KEY_ENV_VAR" "<key>" > "$REPO/.saws-migrate/.source-provider-env" && chmod 600 "$REPO/.saws-migrate/.source-provider-env"
  ```
  Verify the format before proceeding (catches a stray paste without the prefix):
  ```bash
  grep -qE '^(OPENAI|ANTHROPIC|GEMINI)_API_KEY=.+' "$REPO/.saws-migrate/.source-provider-env" && echo KEY_FORMAT_OK || echo KEY_FORMAT_BAD
  ```
  On `KEY_FORMAT_BAD`, rewrite the file (do not echo its contents). Then set
  `sourceBaselineAvailable = true`, `sourceKeyRef = "$REPO/.saws-migrate/.source-provider-env"`.
- **I'll write it to a file myself** → tell the user to create
  `$REPO/.saws-migrate/.source-provider-env` containing a single `$KEY_ENV_VAR=...` line,
  then run the same `grep -qE` format check above (it never prints the key).
  Set the same flags as above.
- **Skip** → `sourceBaselineAvailable = false`, `sourceKeyRef = ""`.

(`.saws-migrate/` is already self-ignoring from the first command above; the rewriter
re-asserts this before any commit as a second layer.)

**IMPORTANT:** Do NOT use `export` or environment variables for the key. They do not persist
across Bash tool calls or into workflow subagents. Write to the file path above.

### B4 — Bedrock preflight

```bash
uv run --project $SCRIPTS python $SCRIPTS/preflight_bedrock.py --region $REGION --models <comma-separated $TARGET_MODELS> --dataset-size 200
```

(`--dataset-size 200` matches the golden-dataset cap, so the quota warning reflects the worst case. Prefix with `AWS_PROFILE=$AWS_PROFILE_CHOICE` if B2 chose a non-default profile.)

Parse the JSON output. On failure the TOP LEVEL carries `reason`/`detail` (lifted from the
first failing model) plus `failing_models` (all failing ids); per-model verdicts are in `models[]`:
- `ok == false` + `reason: credentials` → show the detail (configure/refresh credentials), stop; user re-runs after fixing.
- `ok == false` + `reason: authz` → tell user the IAM action to grant (`bedrock:InvokeModel`); stop.
- `ok == false` + `reason: model_unavailable` → load `resolve-bedrock-model-id` skill with each ID from `failing_models` + region. AskUserQuestion with the candidates: "Use `<candidate>` (cross-region inference profile)" / "Paste a different model ID" / "Abort". On a choice, replace the ID in `$TARGET_MODELS` and re-run B4.
- `ok == false` + any other `reason` → show `detail` and stop.
- `ok == true` → proceed. Surface any `quota_warning`, and any model whose `reason` is
  `embedding_unprobed` (embedding family the preflight can't probe — remind the user to confirm
  model access in the console).

---

## Phase C — Execute

Phase C dispatches the five plugin agents sequentially via the **Agent tool** (subagent types
`ai-to-aws:ai-code-analyzer`, `ai-to-aws:ai-log-ingestor`, `ai-to-aws:ai-prompt-evaluator`,
`ai-to-aws:ai-code-rewriter`, `ai-to-aws:ai-report-generator`). Each agent writes its result to
a file under `$PHASE_DIR = $REPO/.saws-migrate/phase-results/`; you validate every file with
the bundled validator before moving on. There is no workflow runtime — the files ARE the state.

### The validator (used at every step)

```bash
uv run --project $SCRIPTS python $SCRIPTS/validate_result.py --schema <analysis|ingestion|eval|rewrite|delta-decisions> <file>
```

- Exit 0 + `RESULT=valid CONTROL=ok` → phase completed; proceed.
- Exit 0 + `CONTROL=blocked REASON=<r>` → blocked flow (below).
- Exit 0 + `CONTROL=partial COMPLETED=<n> TOTAL=<m>` → partial flow (eval only).
- Exit 1 (`RESULT=invalid` + error lines) or exit 2 (file missing) → **stateless fixer retry**:
  dispatch a FRESH agent of the same type whose prompt is the original context block + the
  file path + the validator's verbatim error output + the instruction "fix ONLY the output
  file at <path> so it validates; do not redo the phase's work unless a required field is
  genuinely missing from it". Cap 2 retries per phase; then stop and show the errors.

### The context block (instantiated at every dispatch)

Build this exact line format (agents parse the labels). Omit lines marked optional when empty:

```
Repository: <$REPO>
AWS region: <$REGION>
AWS profile (pass as --profile / AWS_PROFILE= inline on every aws/boto3 invocation): <$AWS_PROFILE_CHOICE — omit line if default>
Target Bedrock model(s): <comma-joined $TARGET_MODELS, with any resolved overrides already applied>
Migration plan dir: <$MIGRATION_DIR>
Resolved target model id: <override for the primary chat model — omit if none>
Scripts directory (pinned uv toolchain): <$SCRIPTS>
Report date suffix: <saved suffix from run-context — C5/C6 dispatches only>
Source baseline available: <true|false>
Source provider env file: <path — omit if none>
User-supplied log files: <comma-joined — omit if none>
Golden dataset cap (max cases the ingestor may emit): 200
Phase results directory: <$PHASE_DIR>
Prior phase results (Read these files): <paths of already-validated phase JSONs>
Confirmed behavior-delta decisions file (Read it): <$PHASE_DIR/delta-decisions.json — C5 only>
```

Prior-phase results are passed as FILE PATHS — never inline their JSON into the prompt.

### C0 — Run-context gate (resume safety)

The Eval phase makes one paid Bedrock call per golden case (and, with a source key, one paid
source-provider call per case). Before any dispatch, tell the user evaluation will invoke
Bedrock at their expense, capped at 200 cases.

1. `mkdir -p $PHASE_DIR`. Build `$PHASE_DIR/current-context.json` with exactly these fields
   (hashes via `shasum -a 256`; key hash is a fingerprint — never store the key value):

```json
{
  "repo_root": "<cd $REPO && pwd -P>",
  "migration_dir": "<$MIGRATION_DIR>",
  "region": "<$REGION>",
  "aws_profile": "<$AWS_PROFILE_CHOICE or \"\">",
  "aws_account": "<Account from B2>",
  "repo_head_sha": "<git -C $REPO rev-parse HEAD>",
  "repo_branch": "<git -C $REPO rev-parse --abbrev-ref HEAD>",
  "repo_dirty_sha256": "<sha256 of: git status --porcelain + git diff + git diff --cached, EACH with pathspecs -- . ':(exclude).saws-migrate' ':(exclude).migration' ':(exclude)MIGRATION_REPORT_*.md'; \"\" when all three are empty>",
  "target_models": [{"source_model": "...", "aws_model_id": "...", "use_case": "..."}],
  "resolved_model_overrides": {},
  "source_provider": "<from B1>",
  "source_baseline_available": <true|false from B3>,
  "source_key_sha256": "<sha256 of .source-provider-env contents, \"\" when absent>",
  "log_files": [{"path": "...", "sha256": "..."}],
  "max_golden_cases": 200,
  "assess_design_sha256": "<sha256 of $MIGRATION_DIR/aws-design-ai.json>",
  "report_date_suffix": "<date +%Y-%m-%d>",
  "schema_version": 1,
  "plugin_version": "<version from <plugin>/.claude-plugin/plugin.json>"
}
```

2. **Stage 0 (post-C5 normalization).** If `$PHASE_DIR/rewrite.json` exists and validates as
   a payload (`CONTROL=ok`), do NOT use live `repo_*` values. Run three integrity checks:
   (1) `rewrite.baseline_parent_sha` equals the SAVED `repo_head_sha`; (2) `git rev-parse
   <rewrite.branch_name>` equals `rewrite.branch_tip_sha`; (3) `git status --porcelain` (with
   the artifact exclusions) is empty. All pass → copy the saved `repo_*` values into
   current-context verbatim, continue to step 3. Check 2 fails (tip moved) → STOP and
   AskUserQuestion: "Keep your commits (regenerate report only, with a mixed-authorship note)"
   / "Reset the branch to the rewriter's tip and regenerate from C6" / "Abort". Check 3 fails
   (dirty tree) → STOP and ask: commit/stash (then re-check) or discard the edits. Check 1
   fails → treat as a full `repo_*` mismatch in step 3.

3. If `$PHASE_DIR/run-context.json` exists, compare:

```bash
uv run --project $SCRIPTS python $SCRIPTS/validate_result.py --check-run-context $PHASE_DIR/run-context.json --current $PHASE_DIR/current-context.json
```

   - `RUN_CONTEXT=match` → resume: walk C1→C2→C3→(C4: delta-decisions.json)→C5→(C6: report
     file) in order; a phase counts completed iff its file validates with `CONTROL=ok` (C6:
     iff `MIGRATION_REPORT_<saved suffix>.md` exists while rewrite.json is payload-valid).
     STOP the walk at the first missing/invalid/control-state file — blocked/partial files
     route to their flows below, NEVER count as completed. Offer the user "skip completed
     phases X..Y, resume at Z". Files after an unexplained gap: archive them with the gap.
   - `RUN_CONTEXT=mismatch` → scoped invalidation. Map each MISMATCH line through this table,
     archive the named units to `$REPO/.saws-migrate/phase-results-archive/<saved suffix>-$(date +%H%M%S)/`
     (a SIBLING of phase-results/ — never nest it inside), **then immediately overwrite
     run-context.json with current-context.json** (carrying forward the saved
     `report_date_suffix` unless REPORT itself is being invalidated), then re-run the
     invalidated phases in order. Tell the user which fields differed and what re-runs.

| Mismatched field(s) | Archive (units) | Keep |
|---|---|---|
| repo_root, migration_dir, region, aws_profile, aws_account, source_provider, assess_design_sha256, schema_version, plugin_version | everything | — |
| repo_head_sha / repo_branch / repo_dirty_sha256 | everything | — |
| target_models / resolved_model_overrides | ANALYSIS, EVAL, REWRITE, REPORT | INGESTION |
| log_files / max_golden_cases | everything | — |
| source_key_sha256 / source_baseline_available | ANALYSIS, EVAL, REWRITE, REPORT | INGESTION |

   Units: ANALYSIS = analysis.json · INGESTION = ingestion.json + `.saws-migrate/golden-dataset/`
   · EVAL = eval.json + `.saws-migrate/eval-results/` (minus cost_compare.py) · REWRITE =
   rewrite.json + delta-decisions.json · REPORT = `MIGRATION_REPORT_<saved suffix>.md`.

   **Post-C5 reruns of C1–C3 need the pre-migration tree.** If rewrite.json was payload-valid
   and the table invalidates ANALYSIS/INGESTION/EVAL: confirm with the user that the old
   migration branch will be discarded (keep-or-reset flow first if the tip moved), then
   `git checkout <saved repo_branch>`, delete the old branch and the `saws-migrate-baseline`
   tag, and re-run from C1. If the user declines, stop — re-analyzing a tree that contains
   the rewrite produces garbage.

4. No saved run-context → fresh run: write current-context.json as run-context.json, dispatch C1.

### C1 — Analyzer · C2 — Ingestor · C3 — Evaluator

For each phase in order, dispatch the agent with the context block (listing all
prior-phase file paths), then validate its output file:

| Step | agentType | Output file | Schema |
|---|---|---|---|
| C1 | `ai-to-aws:ai-code-analyzer` | `$PHASE_DIR/analysis.json` | analysis |
| C2 | `ai-to-aws:ai-log-ingestor` | `$PHASE_DIR/ingestion.json` | ingestion |
| C3 | `ai-to-aws:ai-prompt-evaluator` | `$PHASE_DIR/eval.json` | eval |

**Blocked flow** (`CONTROL=blocked`): resolve with the user per REASON —
- `model_access` → user enables the model in the Bedrock console (nothing fingerprinted
  changes; re-dispatch the blocked phase only)
- `model_unresolvable` → user picks/pastes an ID → record it in
  `resolved_model_overrides`, fold it into the Target line
- `source_key_auth` → user supplies a new key (re-run B3) or sets baseline unavailable
- `assess_output_missing` → re-run Phase A, then restart Phase C at C0

After ANY resolution, re-run the C0 recipe (rebuild current-context, apply the invalidation
table, overwrite run-context) and re-dispatch **from the earliest invalidated phase** — the
table, not the block location, decides where execution resumes.

**Partial flow** (eval only, `CONTROL=partial`): AskUserQuestion —
- **Continue remaining cases** → re-dispatch the evaluator with the extra context line:
  `Resume: raw_results.jsonl already contains completed cases — evaluate only prompts whose
  ids are not present in it, then re-score and overwrite eval.json`
- **Proceed with partial pass rate** → re-dispatch the evaluator with: `Finalize partial: do
  NOT call Bedrock again — score the cases already in raw_results.jsonl and emit the FULL
  eval payload over only those cases, with total_cases = the number scored and a notes prefix
  line 'partial_coverage: <completed>/<total> cases (throttled)'`. Then C4 runs normally.
- **Abort** → stop; the files stay on disk for a later C0 resume.

### C4 — Checkpoint (two gates) + persist decisions

**Gate (a) — Quality go/no-go.** Read `$PHASE_DIR/eval.json`. The threshold is
**pass rate >= 0.9 AND `source_baseline_quality != 'poor'`** (with `no_golden_cases: true`
in the notes there is no quality signal — always ask). At or above → proceed silently.
Below, AskUserQuestion:
- **Proceed anyway** → gate (b)
- **Change target model** → record in `resolved_model_overrides`, re-run C0 (the table
  invalidates ANALYSIS/EVAL and execution resumes at C1). Cap: 2 retries.
- **Abort** → stop, no code touched.

**Gate (b) — Behavior-delta resolution.** For each `analysis.behavior_deltas[]` with
`user_visible == true`, AskUserQuestion with the options from `behavior-delta-detection`.

**Persist:** write the decisions array (entries `{delta_type, location, resolution_chosen,
source}`; `[]` when there were no user-visible deltas) to `$PHASE_DIR/delta-decisions.json`
and validate it (`--schema delta-decisions`). The file must exist before C5 — it is what
makes a C5 retry or a post-crash resume self-sufficient.

### C5 — Rewriter · C6 — Report

| Step | agentType | Output | Schema |
|---|---|---|---|
| C5 | `ai-to-aws:ai-code-rewriter` | `$PHASE_DIR/rewrite.json` | rewrite |
| C6 | `ai-to-aws:ai-report-generator` | `MIGRATION_REPORT_<saved suffix>.md` in repo root | (none — file existence is the completion check) |

C5's context block includes the `Confirmed behavior-delta decisions file` line and the
`Report date suffix` line (from run-context, NOT today's date on a resume). C6's context
block lists all four phase-result file paths.

### C7 — Render summary

```bash
uv run --project $SCRIPTS python <SKILL_BASE>/render_report.py --phase-results $PHASE_DIR --repo $REPO --date-suffix <saved suffix>
```

Print the summary. Point the user at `rewrite.branch_name` (usually `bedrock-migration`, but
a collision-suffixed variant like `bedrock-migration-2` when they already had that branch)
and the report file. Tell them how to undo — substitute the ACTUAL branch name from
`rewrite.branch_name`, never a hardcoded one (on a collision run, `bedrock-migration` is the
user's own pre-existing branch and deleting it would destroy their work):

> To discard: `git checkout <your original branch>`, `git branch -D <rewrite.branch_name>`,
> `git tag -d saws-migrate-baseline`, and `rm -rf .saws-migrate .migration` removes all
> migration artifacts (including the API key file — also consider rotating the key you pasted).

---

## Inline mode (platforms without an Agent/subagent dispatch tool)

If this platform has no subagent dispatch tool, run phases inline ONE AT A TIME, with a
mandatory stop between phases:

1. `Read` exactly ONE agent definition (`<plugin>/agents/<name>.md`) — never load more than
   one phase's definition into context at once.
2. Follow it start-to-finish; write and validate the same phase-result file.
3. STOP. Report the phase outcome (validator CONTROL line + one-line summary) and ask the
   user to confirm before loading the next phase's definition. This checkpoint is mandatory:
   it is the context-pressure release valve, and the phase-result file means nothing is lost
   if the user continues in a fresh session instead.

Warn the user up front that inline mode is slower and context-heavier than subagent dispatch,
and that the rewriter phase performs git operations (branch, commits, worktree) directly in
this session.

---

## Failure handling

- An agent dispatch dies (tool error, terminal failure) → the phase file is missing →
  validator exit 2 → the stateless fixer-retry path (which, finding no file to fix, re-runs
  the phase). Do not auto-retry more than the 2-retry cap.
- User aborts at any gate → confirm no SOURCE CODE was modified (C5 never started if aborted
  before then). Note that `.migration/` and `.saws-migrate/` artifacts do exist; show the
  undo commands from C7 if the user wants them gone.
- Assess skill fails → show the error and stop. User can re-run `/ai-to-aws:llm-to-bedrock`.
