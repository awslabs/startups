# Agent Maintenance — Shared-Section Checklist

The five agent files under this directory are dispatched independently as
plugin subagents. Each one is loaded into its own context, so it cannot
`import` shared content — every agent file must repeat the sections it needs.

That repetition creates a maintenance hazard: a change to one of those sections
needs to be considered in **every other agent** that has a sibling copy. This
file is the inventory; consult it whenever you edit any of the items listed
below in any agent file.

The five agent files this applies to:

- `ai-code-analyzer.md`
- `ai-log-ingestor.md`
- `ai-prompt-evaluator.md`
- `ai-code-rewriter.md`
- `ai-report-generator.md`

---

## Sections shared across agents

These are not enforced by tooling. When you edit any of them in one file,
re-read the corresponding section in the four others and decide whether the
edit applies there too. The differences listed in the **Intentional drift**
column are deliberate — preserve them.

| Topic                                                                                         | Where it appears                                                                                               | Intentional drift to preserve                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intro paragraph: "source repo is local, AWS creds via `aws configure`, no Docker sandbox"** | analyzer, ingestor, evaluator (verbatim); rewriter and report-generator have agent-specific variants           | Rewriter's intro adds the "work directly on the repo, no worktree" instruction; report-generator's intro names the `Repository:` context line explicitly.                                                                                                                                                                                                                                                                                                                                                  |
| **`# 1. CRITICAL RULES` rule 1 — Bash tool + "never simulate"**                               | All five agents                                                                                                | `Bash` is capitalized in four agents; evaluator uses lowercase `bash` (matches its long-standing tool-name usage in subsequent sections — do not "fix" without auditing the whole file). Analyzer and ingestor also list `Read` / `Grep` / `Glob` as preferred for reading; the other three do not.                                                                                                                                                                                                        |
| **NON-INTERACTIVE + Output protocol (write JSON to phase-result file + self-validate)**       | analyzer, ingestor, evaluator, rewriter                                                                        | Each names a different schema (`analysis` / `ingestion` / `eval` / `rewrite`) and target file (`<Phase results directory>/<name>.json`). Evaluator additionally documents the `partial` control state for throttle truncation; rewriter documents `blocked` for git-state issues. Report-generator does not have this rule — its deliverable is the `MIGRATION_REPORT_*.md` file, not a phase-result JSON.                                                                                                 |
| **Untrusted-content rule**                                                                    | All five agents                                                                                                | Each agent's wording is tailored to the data it actually reads — source files (analyzer, rewriter), log lines and prompts (ingestor), responses being judged (evaluator), report inputs (report-generator). Keep the per-agent specificity; do not collapse into one generic sentence.                                                                                                                                                                                                                     |
| **Placeholder syntax** (`<NAME>`, `<scriptsDir>`, etc.)                                       | analyzer, rewriter, report-generator have explicit sections; ingestor and evaluator use the conventions inline | The set of placeholders used differs by agent. If you add a new placeholder, document it in the agent that introduces it.                                                                                                                                                                                                                                                                                                                                                                                  |
| **uv-vs-`python3` rule**                                                                      | The canonical statement lives in `ai-prompt-evaluator.md` §1 rule 5. The other agents follow it implicitly.    | Rule: any Python that imports `boto3`/`botocore` MUST use `uv run --project <scriptsDir> python` (the pinned env guarantees the AWS SDK version Bedrock calls expect). Pure stdlib one-liners — JSONL parsing, JSON status reads, `py_compile` of the customer's code, `python3 -m venv` building the customer's venv — use bare `python3` (the pinned env adds no value, only ~100 ms per call). When you add a new Python invocation in any agent, classify it under this rule before choosing the form. |

---

## When you change one of the shared sections, do this

1. Open each agent file in the list above and search for the section you just
   changed (the table above tells you which agents have it).
2. Apply the same edit, **keeping the per-agent drift listed in the right
   column intact**.
3. If your change makes one of the drifts obsolete (e.g. unifying the `Bash`
   vs `bash` casing across all five), update this file's table too so it
   stops claiming the drift is intentional.

There is no CI check for drift today. If the agent count grows past ~5, or
edits to these sections become frequent, consider a Python script that diffs
the named sections across agents and fails CI on unexpected divergence — or
move to a templated build step. Both are deliberately out of scope for the
current size.
