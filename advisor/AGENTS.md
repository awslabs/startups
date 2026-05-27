# AGENTS.md — AI assistant brief

**You are an AI coding assistant reading this repo on behalf of a user.** Your user wants the AWS Startup Advisor plugin (three skills) installed into their AI coding agent. Do it for them.

## TL;DR — run this

```bash
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' -a <agent>
```

`--skill '*'` installs all three skills at once. Replace `<agent>` with the user's coding agent shorthand:

- `kiro-cli` — Kiro (auto-loads from `.kiro/skills/`)
- `claude-code` — Claude Code
- `cursor` — Cursor
- `codex` — Codex
- `github-copilot` — GitHub Copilot
- `opencode`, `continue`, `windsurf`, `gemini-cli` — others

Full list of 50+ supported agents: [vercel-labs/skills](https://github.com/vercel-labs/skills#supported-agents).

If you don't know which agent the user is running, either:

- Check the project for agent-specific config folders (`.kiro/`, `.claude/`, `.cursor/`, `.codex/`), or
- Run the command with `-a '*'` — the CLI installs into every auto-detected agent.

Tell the user to **restart their agent** after install so the skills get picked up.

## What this plugin exposes

Three sibling skills, each with its own SKILL.md and (where applicable) `references/` content:

### `knowledge-base-for-startups` — AWS Startups knowledge base

- **1 landing page**: `references/home.md` — for broad "what is AWS Startups" questions.
- **3 searchable indexes** (consult these before opening individual articles):
  - `references/learn.md` — 277 articles across 8 categories, with keywords.
  - `references/offers.md` — 13 publicly-viewable AWS Activate partner offers, with keywords.
  - `references/build.md` — 22 sample architectures / solution guides; split into publicly-viewable and sign-in-required sections.
- **5 reference pages**: `references/faq.md` (111 Q&A), `references/credits.md`, `references/programs.md`, `references/providers.md`, `references/contact-us.md`.
- **2 live-URL redirect stubs**: `references/events.md` and `references/showcase.md`. Hand over the live URL from the stub.

### `prompt-library-for-startups` — copy-paste prompts + downloadable agents

- **1 searchable index**: `references/prompt-library.md` (30 prompts, 4 downloadable agents, plus a Q&A FAQ section on prompt usage / cost / safety).
- **30 prompt detail files** under `references/prompt-library/<slug>.md` — each with the verbatim System Prompt and a "How to use?" section where available.
- **4 downloadable agents** documented inline in the index — recommend by use case, hand over the GitHub repo link.

### `start-building-for-startups` — discovery + implementation workflow

- A SOP-style SKILL.md that drives a picker-based discovery flow (intent, scope, constraints, preferences) and then writes code into the user's codebase. No `references/` content — it's pure workflow.
- Calls into `knowledge-base-for-startups` and `prompt-library-for-startups` mid-flow when an architecture reference or a starter prompt would accelerate the work.

### Cross-skill behavior

- Every reference file in `knowledge-base-for-startups/` and `prompt-library-for-startups/` carries a `source_url` in frontmatter — quote that, don't invent URLs.
- Boundary queries (a user message that fits two skills) — invoke both. Example: _"how do I start with RAG on Bedrock?"_ → `knowledge-base-for-startups` for the learn article + `prompt-library-for-startups` for the starter prompt.

## Known limitations

- Some offer-detail pages and a few build solutions require an AWS Activate sign-in; those are either excluded (offers) or marked in a "Sign-in required" table with a live URL (`build.md`). Recommend by title + keywords and hand over the URL.
- The skills are public-content snapshots. They **cannot** answer account-specific questions (credits balance, membership status, application status). For those, direct the user to `<https://aws.amazon.com/startups>` to sign in.
- Content freshness varies — see `Last updated` in each `SKILL.md`. For time-sensitive questions (current event dates, current offer terms, current accelerator cohort windows), cite the `source_url` so the user can verify.

## Do not

- **Do not** modify files under `advisor/plugins/aws-startup-advisor/` — that's the distributable content.
- **Do not** invent, paraphrase, or summarize content into the skill files. Everything in `references/` is verbatim from `aws.amazon.com/startups` for legal cleanliness.
- **Do not** install by copying files manually — always use the `npx skills` CLI. It picks the right per-agent directory and handles symlinks vs. copies consistently.
- **Do not** tell the user to "paste this into your AI tool" when surfacing a prompt — you ARE the AI tool. Surface the prompt as a reference and offer to execute / adapt / copy.
