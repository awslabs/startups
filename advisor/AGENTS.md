# AGENTS.md — AI assistant brief

**You are an AI coding assistant reading this repo on behalf of a user.** Your user wants the AWS Startup Advisor plugin installed into their AI coding agent. Do it for them.

## TL;DR — run this

```bash
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' -a <agent>
```

`--skill '*'` installs all skills at once. Replace `<agent>` with the user's coding agent shorthand:

- `kiro-cli` — Kiro (auto-loads from `.kiro/skills/`)
- `claude-code` — Claude Code
- `cursor` — Cursor
- `codex` — Codex
- `github-copilot` — GitHub Copilot
- `opencode`, `continue`, `windsurf`, `gemini-cli` — others

Full list of supported agents: [vercel-labs/skills](https://github.com/vercel-labs/skills#supported-agents).

If you don't know which agent the user is running, either:

- Check the project for agent-specific config folders (`.kiro/`, `.claude/`, `.cursor/`, `.codex/`), or
- Run the command with `-a '*'` — the CLI installs into every auto-detected agent.

Tell the user to **restart their agent** after install so the skills get picked up.

## What this plugin exposes

Sibling skills, each with its own SKILL.md and (where applicable) `references/` content:

### `knowledge-base-for-startups` — AWS Startups knowledge base

- **Landing page**: `references/home.md` — for broad "what is AWS Startups" questions.
- **Searchable indexes** (consult these before opening individual articles):
  - `references/learn.md` — hundreds of learn articles across a dozen categories, with keywords.
  - `references/offers.md` — AWS Activate partner offers, with keywords.
  - `references/build.md` — sample architectures / solution guides; split into publicly-viewable and sign-in-required sections.
- **Reference pages**: `references/faq.md` (comprehensive Activate Q&A), `references/credits.md`, `references/programs.md`, `references/providers.md`, `references/contact-us.md`.
- **Live-URL redirect stubs**: `references/events.md` and `references/showcase.md`. Hand over the live URL from the stub.

### `prompt-library-for-startups` — copy-paste prompts + downloadable agents

- **Searchable index**: `references/prompt-library.md` (prompts, downloadable agents, plus a Q&A FAQ section on prompt usage / cost / safety).
- **Prompt detail files** under `references/prompt-library/<slug>.md` — each with the verbatim System Prompt and a "How to use?" section where available.
- **Downloadable agents** documented inline in the index — recommend by use case, hand over the GitHub repo link.

### `start-building-for-startups` — discovery + implementation workflow

- A SOP-style SKILL.md that drives a picker-based discovery flow (intent, scope, constraints, preferences) and then writes code into the user's codebase. No `references/` content — it's pure workflow.
- Calls into `knowledge-base-for-startups` and `prompt-library-for-startups` mid-flow when an architecture reference or a starter prompt would accelerate the work.

### `architect-for-startups` — stage-aware AWS architecture guidance

- Stage-aware architecture advice that adjusts recommendations based on startup stage (pre-revenue, seed, Series A, Series B+), team size, runway, credits, and timeline. Consulted for architecture questions that aren't a full build (`start-building-for-startups`) or a migration.

### `gcp-to-aws` — Google Cloud → AWS migration workflow

- A SOP-style SKILL.md that runs a structured 6-phase migration (discover → clarify → design → estimate → generate → feedback), with a `references/` tree of phase guides, design refs, and shared schemas. Clarify must complete before Design, Estimate, or Generate.
- Also migrates AI / agentic workloads (OpenAI / Gemini → Amazon Bedrock; LangChain / CrewAI / AutoGen → AWS-native frameworks).
- Triggered by migration intent — _"migrate from GCP"_, _"move off OpenAI to Bedrock"_, _"GCP to AWS"_, etc.

### `heroku-to-aws` — Heroku → AWS migration workflow

- A DSL-driven SKILL.md running the same 6-phase backbone (Dynos → Fargate/Elastic Beanstalk, Postgres → RDS/Aurora, Redis → ElastiCache, Kafka → MSK), with an optional what-if repricing workshop after Estimate.
- Triggered by _"migrate from Heroku"_, _"Heroku to AWS"_, _"move off Heroku"_, etc.

### `llm-to-bedrock` — OpenAI/Gemini/Anthropic → Amazon Bedrock SDK rewrite

- Executes a pure model/SDK migration: assess the codebase, rewrite call sites, evaluate output quality against Bedrock, and deliver a ready-to-merge git branch. Delegates its Assess phase to the `gcp-to-aws` skill.
- Triggered by _"rewrite my OpenAI calls for Bedrock"_, _"migrate LangChain to Bedrock"_, etc.

### `agent-advisor` — AI-agent runtime advisor + migration plan + POC

- A DSL-driven skill that picks an AWS runtime for AI agents (AgentCore vs ECS/EKS/Lambda vs Lambda MicroVMs), can generate a full migration plan (reusing the `gcp-to-aws` engine in-skill), and optionally builds a deployable POC. Also handles Temporal workers.
- Triggered by _"which runtime for my agent"_, _"AgentCore vs Lambda"_, _"deploy an AI agent on AWS"_, _"migrate Temporal workers to AWS"_, etc.

### `tf-best-practices` — Terraform authoring guidance + policy gate

- Best-practice authoring rules and a read-only policy gate for the AWS Terraform generated by the migration skills. Never edits `.tf` files or decides phase completion.

- **The migration skills use MCP servers for live data** declared in the plugin's `.mcp.json`: `awsknowledge` (HTTP), `awspricing` (stdio via `uvx`), `aws-pricing-calculator` (stdio via `npx`), and `temporal-docs` (HTTP, for `agent-advisor`). They are enhancements, not hard dependencies — the skills run without them, with pricing falling back to a bundled cache and docs lookups skipped. The AWS Pricing server needs `uv`/`uvx` on the machine.
  - **Only the Claude Code plugin install** (`/plugin install aws-startup-advisor@claude-plugins-official`) provisions these automatically, by reading `.mcp.json`.
  - **The `npx skills add` path in this file's TL;DR does not.** That CLI only copies skill files — it never touches MCP config, for any agent. After running it, tell the user: the migration skills still work (pricing falls back to cached rates), but for live pricing and current AWS docs they need to add the servers from `advisor/plugins/aws-startup-advisor/.mcp.json` to their agent's own MCP config themselves (e.g. `.kiro/settings/mcp.json` for Kiro, `.cursor/mcp.json` for Cursor, `codex mcp add` for Codex). Point them at the "MCP servers" section of `advisor/README.md` for exact commands per agent. Do not tell the user MCP setup already happened just because the skill install succeeded.

### Cross-skill behavior

- Every reference file in `knowledge-base-for-startups/` and `prompt-library-for-startups/` carries a `source_url` in frontmatter — quote that, don't invent URLs.
- Boundary queries (a user message that fits two skills) — invoke both. Example: _"how do I start with RAG on Bedrock?"_ → `knowledge-base-for-startups` for the learn article + `prompt-library-for-startups` for the starter prompt.
- Migration intent routes to the matching skill: GCP → `gcp-to-aws`, Heroku → `heroku-to-aws`, OpenAI/Gemini/Anthropic SDK rewrite → `llm-to-bedrock`, AI-agent runtime/architecture → `agent-advisor`.

## Known limitations

- A few build solutions require an AWS Activate sign-in; those are marked in a "Sign-in required" table with a live URL (`build.md`). Recommend by title + keywords and hand over the URL.
- The skills are public-content snapshots. They **cannot** answer account-specific questions (credits balance, membership status, application status). For those, direct the user to `<https://aws.amazon.com/startups>` to sign in.
- Content freshness varies — see `Last updated` in each `SKILL.md`. For time-sensitive questions (current event dates, current offer terms, current accelerator cohort windows), cite the `source_url` so the user can verify.

## Do not

- **Do not** modify files under `advisor/plugins/aws-startup-advisor/` — that's the distributable content.
- **Do not** invent, paraphrase, or summarize content into the skill files. Everything in `references/` is verbatim from `aws.amazon.com/startups` for legal cleanliness.
- **Do not** install by copying files manually — always use the `npx skills` CLI. It picks the right per-agent directory and handles symlinks vs. copies consistently.
- **Do not** tell the user to "paste this into your AI tool" when surfacing a prompt — you ARE the AI tool. Surface the prompt as a reference and offer to execute / adapt / copy.
