# Evaluation Guide

How to validate the migration skill after making changes to prompt files.

---

## Quick Reference

| What                                  | Command                                                             |
| ------------------------------------- | ------------------------------------------------------------------- |
| Structural check (instant, no Claude) | `mise run eval:check`                                               |
| Full evaluation (after migration run) | `python tools/eval_check.py --migration-dir <DIR> --fixture <NAME>` |
| Guided evaluation (Claude assists)    | Tell Claude: `Read tools/EVAL_SKILL.md and follow the instructions` |

---

## When to Evaluate

Run the evaluation harness whenever you:

- Edit any prompt file under `features/migration-to-aws/skills/gcp-to-aws/`
- Modify schema definitions, classification rules, or mapping tables
- Change the fast-path table, rubric, or pricing cache
- Add or remove questions from the Clarify phase

---

## Step-by-Step Workflow

### 1. Make your prompt changes

Edit the relevant files under `features/migration-to-aws/skills/gcp-to-aws/`.

### 2. Run the structural check

```bash
mise run eval:check
```

This runs instantly with no Claude API calls. It verifies that critical directives
still exist in the prompt files:

- FORBIDDEN blocks (scope boundaries for each phase)
- BigQuery specialist gate directive
- Security rules (no hardcoded credentials, no wildcard IAM)
- Dry-run default for generated scripts

If this fails, a directive was accidentally deleted. The output tells you
exactly which file and line to check.

### 3. Pick a fixture

Choose the fixture that best covers your change:

| Fixture                    | Use when you changed...                                                   |
| -------------------------- | ------------------------------------------------------------------------- |
| `minimal-cloud-run-sql`    | General prompt changes, state machine, phase ordering, generate phase     |
| `bigquery-specialist-gate` | BigQuery handling, specialist gate, Clarify advisory, analytics exclusion |
| `ai-workload-openai`       | AI detection, model mapping, lifecycle rules, Category F questions        |
| `user-preferences`         | Clarify question flow, preference schema, Design preference consumption   |
| `negative-services`        | Classification rules, auth exclusion, forbidden service mappings          |

For broad changes, run `minimal-cloud-run-sql` first (it has the most invariants),
then any fixture specific to your change area.

### 4. Run the migration skill against the fixture

```bash
cd tests/fixtures/minimal-cloud-run-sql
```

Open Claude Code and trigger the migration:

```
migrate from GCP to AWS
```

The skill runs all 6 phases using the fixture's Terraform files and pre-seeded
preferences. Wait for it to complete (you'll see "Migration planning complete"
or similar).

### 5. Run the evaluation

**Option A — Direct (recommended for CI and scripting):**

```bash
python tools/eval_check.py \
  --migration-dir tests/fixtures/minimal-cloud-run-sql/.migration/<RUN_ID> \
  --fixture minimal-cloud-run-sql
```

Replace `<RUN_ID>` with the directory name (e.g., `0419-1200`). The checker
outputs JSON with pass/fail for every invariant.

**Option B — Claude-assisted (recommended for understanding failures):**

In Claude Code, type:

```
Read tools/EVAL_SKILL.md and follow the instructions to evaluate the migration results
```

Claude runs the checker, explains any failures in plain language, computes
hashes, and writes `.eval-results.json`.

### 6. Review results

The checker output looks like:

```json
{
  "summary": {
    "hard_total": 26,
    "hard_passed": 26,
    "hard_failed": 0,
    "hard_skipped": 0,
    "status": "pass"
  }
}
```

- **All pass** — your change is safe. Proceed to commit.
- **Failures** — read the `details` field for each failed invariant. It tells
  you what was found, what was expected, and which prompt file to check.
- **Skips** — a custom handler isn't implemented yet. Not a blocker.

### 7. Commit the results

```bash
git add .eval-results.json
git commit -m "eval: results for minimal-cloud-run-sql"
```

The `.eval-results.json` file is SHA-bound to your commit and prompt file
hashes. CI can verify it wasn't forged or stale.

---

## Test Fixtures

### minimal-cloud-run-sql

The default fixture. 2 PRIMARY resources (Cloud Run + Cloud SQL), 3 SECONDARY
resources. Tests the full 6-phase pipeline with all defaults.

**26 hard invariants** covering: phase ordering, inventory schema, cluster
integrity, preferences schema, design mappings, confidence values, cost
estimation, security rules, dry-run defaults.

**Location:** `tests/fixtures/minimal-cloud-run-sql/`

### bigquery-specialist-gate

Tests the BigQuery specialist gate — the rule that `google_bigquery_*` resources
must map to "Deferred — specialist engagement" and be excluded from cost totals.

**9 hard invariants** focused on: deferred mapping, no Redshift/Athena/Glue/EMR,
non-BigQuery resources still get normal mappings.

**Location:** `tests/fixtures/bigquery-specialist-gate/`

### ai-workload-openai

Tests AI workload detection for apps using the OpenAI SDK on GCP. Includes
both Terraform and Python source code (`src/chatbot.py` with `openai` imports).

**11 hard invariants** focused on: AI profile creation, model detection,
confidence threshold, excluded/legacy model rules, Category F questions.

**Location:** `tests/fixtures/ai-workload-openai/`

### user-preferences

Same infrastructure as minimal, but with pre-seeded user answers
(target_region=us-west-2, availability=single-az, cutover_strategy=blue-green).
Tests that Design output respects user preferences.

**10 hard invariants** focused on: chosen_by="user" preserved, Design region
matches preference, single-AZ honored.

**Location:** `tests/fixtures/user-preferences/`

### negative-services

Tests that forbidden AWS services never appear in Design output. Contains
auth resources (should be excluded from inventory), BigQuery (should be
deferred), and Cloud Run (should map to Fargate, not Lightsail/Beanstalk).

**8 hard invariants** focused on: auth exclusion, no Cognito, no Lightsail,
no Elastic Beanstalk, no analytics services for BigQuery.

**Location:** `tests/fixtures/negative-services/`

---

## Understanding Invariants

Invariants are defined in YAML files:

- **Shared:** `tests/invariants.yml` — used by `minimal-cloud-run-sql`
- **Per-fixture:** `tests/fixtures/<name>/invariants.yml` — used by all other fixtures

Each invariant has:

| Field         | Purpose                                                      |
| ------------- | ------------------------------------------------------------ |
| `id`          | Unique identifier (e.g., H25, BQ3, NEG1)                     |
| `description` | What's being checked                                         |
| `source`      | Which prompt file contains the rule (file:line)              |
| `check.type`  | How it's checked (file_exists, content_absent, custom, etc.) |

### Check types

| Type              | What it does                                          | Needs Python handler? |
| ----------------- | ----------------------------------------------------- | --------------------- |
| `file_exists`     | Assert a file exists in migration output              | No                    |
| `file_absent`     | Assert a file does NOT exist                          | No                    |
| `content_present` | Assert patterns exist in file(s)                      | No                    |
| `content_absent`  | Assert patterns do NOT exist in file(s)               | No                    |
| `json_path_value` | Assert a JSON field has a specific value              | No                    |
| `json_every`      | Assert every item in a JSON array has required fields | No                    |
| `uniqueness`      | Assert all values at a path are unique                | No                    |
| `cross_file_join` | Assert values in one file match values in another     | No                    |
| `custom`          | Delegate to a Python script in `tools/invariants/`    | Yes                   |

### Custom handlers

Python scripts in `tools/invariants/` handle logic too complex for YAML.
Each script:

1. Takes the migration directory as `sys.argv[1]`
2. Reads the relevant JSON file(s)
3. Prints `{"status": "pass"}` or `{"status": "fail", "details": "..."}`
4. Includes documentation with: invariant description, skill file reference,
   and pass/fail examples

---

## Adding a New Invariant

### For declarative checks (no Python):

Add an entry to the fixture's `invariants.yml`:

```yaml
- id: H50
  description: "New check description"
  source: "prompt-file.md:line"
  check:
    type: content_absent
    file: gcp-resource-inventory.json
    patterns:
      - "forbidden pattern"
```

### For complex checks (Python handler):

1. Add the YAML entry pointing to a handler:

   ```yaml
   - id: H50
     description: "New check description"
     source: "prompt-file.md:line"
     check:
       type: custom
       handler: "tools/invariants/h50_new_check.py"
   ```

1. Create `tools/invariants/h50_new_check.py` following the pattern of
   existing handlers. Include the docstring with invariant description,
   skill file reference, and examples.

1. Run the evaluation to verify your new invariant passes on existing output.

---

## Troubleshooting

### `pip install pyyaml` error

The checker requires PyYAML. Install it:

```bash
pip install pyyaml
```

### "No invariants found for fixture"

The fixture name doesn't match any `invariants.yml`. Check:

- `tests/fixtures/<name>/invariants.yml` exists, OR
- `tests/invariants.yml` has `fixture: <name>` at the top

### Handler returns "skip"

The custom Python handler file doesn't exist yet. Either implement it or
accept the skip — skipped invariants don't affect pass/fail.

### False positive on H41 (hardcoded credentials)

The pattern `password = "` catches Terraform attribute assignments with string
values. If your generated Terraform has a legitimate use (e.g.,
`manage_master_user_password = true`), the check should already pass since we
only match `password = "` (with a quote). If you encounter a new false
positive, tighten the pattern in `tests/invariants.yml`.
