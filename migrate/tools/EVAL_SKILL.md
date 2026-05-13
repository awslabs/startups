# Evaluate Migration Results

> **Local testing only.** This is NOT a published skill. It lives in `tools/`
> and is used by contributors to validate migration output against invariants.
> To use it, copy-paste the relevant steps into your Claude Code session, or
> reference this file when asking Claude to evaluate results.

## Purpose

You are running the evaluation harness for the `migration-to-aws` plugin. Your job is to:

1. Locate the migration output directory
2. Run the checker script against it
3. Explain any failures in plain English
4. Produce `.eval-results.json` bound to the current commit

You do NOT re-run the migration. You only validate existing output.

---

## Step 1: Locate Migration Output

Find the migration output directory. Look for `.migration/` in the current working directory.

- If exactly one subdirectory exists under `.migration/`, use it.
- If multiple exist, ask the user which one to evaluate.
- If none exist, tell the user: "No migration output found. Run the migration skill first, then come back here."

Set `$MIGRATION_DIR` to the full path of the chosen directory.

Confirm with the user: "I found migration output at `$MIGRATION_DIR`. I'll evaluate it against the `minimal-cloud-run-sql` fixture. Proceed?"

---

## Step 2: Determine Fixture

Check if the current directory is inside `tests/fixtures/`. If so, use the fixture directory name.

Otherwise, default to `minimal-cloud-run-sql`. If the user specifies a different fixture, use that.

Set `$FIXTURE` to the fixture name.

---

## Step 3: Run the Checker Script

Execute:

```bash
python tools/eval_check.py --migration-dir $MIGRATION_DIR --fixture $FIXTURE
```

Capture both stdout (JSON results) and the exit code.

- Exit code 0 = all hard invariants pass
- Exit code 1 = one or more hard invariants fail
- Exit code 2 = configuration error (report to user and stop)

---

## Step 4: Present Results

Parse the checker's JSON output. Present results to the user in this format:

### If all invariants pass:

> All hard invariants passed (N/N). Migration output looks good.
>
> Soft observations:
>
> - S1: Number of PRIMARY resources — expected 2, got [actual]
> - S3: Cloud Run mapping — expected Fargate, got [actual]

### If any invariants fail:

For EACH failure, explain in plain language:

1. **What failed** — the invariant description
2. **Where** — which file and what was found (or missing)
3. **Why it matters** — paraphrase the source rule
4. **Where to look** — which prompt file to check (use the `source` field)

Example:

> **H6 FAILED**: Discovery outputs contain zero AWS service names
>
> Found "Fargate" in `gcp-resource-inventory.json`. The Discover phase must not mention AWS services — this is a scope boundary rule at `discover.md:180-188`. The Discover phase only catalogs what EXISTS in GCP; AWS mapping happens later in Design.
>
> Check your changes to files under `references/phases/discover/` for anything that might leak AWS service names into discovery output.

### Skipped invariants:

If any checks were skipped (custom handler not yet implemented), note them briefly:

> 12 checks skipped (custom handlers not yet implemented). These will be added in a future update.

---

## Step 5: Compute Hashes and Write Results Artifact

After presenting results, compute the artifact metadata:

### 5.1 Commit SHA

```bash
git rev-parse HEAD
```

### 5.2 Prompt files hash

Compute SHA-256 over all prompt files, sorted by path:

```bash
find features/migration-to-aws/skills/gcp-to-aws -name "*.md" -type f | sort | xargs cat | shasum -a 256
```

### 5.3 Fixture files hash

```bash
find tests/fixtures/$FIXTURE -type f | sort | xargs cat | shasum -a 256
```

### 5.4 Write `.eval-results.json`

Write the following JSON to `.eval-results.json` in the repository root:

```json
{
  "schema_version": "1",
  "metadata": {
    "commit_sha": "<from 5.1>",
    "timestamp": "<ISO 8601 UTC>",
    "runner_version": "0.1.0",
    "prompt_files_hash": "sha256:<from 5.2>",
    "fixture_files_hash": "sha256:<from 5.3>"
  },
  "fixtures": [
    {
      "name": "<$FIXTURE>",
      "status": "<pass or fail>",
      "duration_seconds": null,
      "phases_completed": ["discover", "clarify", "design", "estimate", "generate"],
      "hard_invariants": [
        {
          "id": "<id>",
          "description": "<description>",
          "status": "<pass|fail|skip>",
          "details": "<details if fail, omit if pass>"
        }
      ],
      "soft_observations": [
        {
          "id": "<id>",
          "description": "<description>",
          "expected": "<expected>",
          "actual": "<actual from checker>"
        }
      ],
      "output_files_hash": "sha256:<hash of all files in $MIGRATION_DIR>"
    }
  ],
  "summary": {
    "total_fixtures": 1,
    "passed": "<1 if all hard pass, else 0>",
    "failed": "<1 if any hard fail, else 0>",
    "hard_invariant_failures": "<count>",
    "error": null
  }
}
```

### 5.5 Output files hash

```bash
find $MIGRATION_DIR -type f | sort | xargs cat | shasum -a 256
```

---

## Step 6: Final Message

After writing the artifact:

### If passing:

> Evaluation complete. `.eval-results.json` written to repo root.
>
> Next steps:
>
> ```text
> git add .eval-results.json
> git commit -m "eval: add results for [fixture]"
> ```

### If failing:

> Evaluation complete with failures. `.eval-results.json` written (with failures recorded).
>
> Fix the issues above, re-run the migration skill, then re-run this evaluation.
> Do NOT commit `.eval-results.json` with failures — CI will reject it.

---

## Rules

- **NEVER** modify migration output files. You are read-only.
- **NEVER** re-run the migration skill. You only validate.
- **NEVER** skip writing `.eval-results.json` — always write it, even with failures.
- **ALWAYS** show the natural-language explanation before writing the artifact.
- **ALWAYS** use the checker script. Do not manually inspect JSON files to determine pass/fail — the script is the source of truth.
- If the checker script fails to run (import error, missing yaml, etc.), tell the user the exact error and suggest: "Run `pip install pyyaml` or check that Python 3.10+ is available."
