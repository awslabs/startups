# ai-to-aws

Single `/ai-to-aws:llm-to-bedrock` command that assesses AI workloads (OpenAI, Gemini, Anthropic direct) and executes migration to Amazon Bedrock — rewriting code, evaluating quality, and delivering a ready-to-merge git branch.

## Prerequisites

- The `migration-to-aws` plugin (powers the Assess phase):
  `/plugin install migration-to-aws@startups-for-aws`
- Python 3.10+ and [uv](https://docs.astral.sh/uv/)
- AWS CLI configured (`aws configure` or SSO)
- AWS credentials with `bedrock:InvokeModel` permission
- **Bedrock model access enabled** for your target models — this is a separate console step
  from IAM: [Bedrock console → Model access](https://console.aws.amazon.com/bedrock/home#/modelaccess)
- Your source code in a **git repository** (the deliverable is a git branch)
- macOS or Linux (Windows via WSL)

## Platform support

Built for Claude Code (uses its subagent dispatch). On agent platforms without a
subagent mechanism, the skill falls back to a documented inline mode — phases run
one at a time in the main session with mandatory checkpoints between them (slower
and more context-hungry, but fully functional; progress is checkpointed to disk
after every phase either way).

## Install

```
/plugin marketplace add awslabs/startups
/plugin install ai-to-aws@startups-for-aws
```

## Usage

```
/ai-to-aws:llm-to-bedrock
```

## What it does to your repo

- Writes assessment artifacts to `.migration/` and evaluation data to `.saws-migrate/`
  (both kept out of git via self-ignoring `.gitignore` files)
- Creates a `bedrock-migration` branch with the rewritten code, regenerated lockfiles,
  and generated tests — your checked-out branch is not modified
- Writes `MIGRATION_REPORT_<date>.md` to the repo root (left uncommitted; it contains
  excerpts of your prompts/responses — review before sharing)
- Nothing is pushed to a remote; you review and push the branch yourself

The report includes a "How to Undo" section for discarding everything.

## What it costs

- Evaluation invokes Bedrock once per golden-dataset case (capped at 200 cases,
  up to 4096 output tokens each) — typically cents to a few dollars
- If you provide a source-provider API key for side-by-side comparison, each case is
  also run once against the source provider at your expense
- A 1-token preflight probe per target model (~$0.00001 each)

Expect an interactive session of roughly 30–90 minutes including the assessment questions.

## License

MIT-0
