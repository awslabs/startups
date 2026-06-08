# AWS Startup Advisor

A plugin of sibling skills that work alongside each other in any modern AI coding agent (Kiro, Claude Code, Cursor, Codex, GitHub Copilot, and many others):

- **`knowledge-base-for-startups`** — AWS Startups knowledge base. Activate FAQ, credits guide, programs, partner offers, sample architectures, and hundreds of learn articles. Read-only reference content from [aws.amazon.com/startups](https://aws.amazon.com/startups), all searchable and offline after install.
- **`prompt-library-for-startups`** — AWS-curated copy-paste prompts plus downloadable installable agents (Multi-Account Transition Advisor, Bill Shock Preventer, Service Quota).
- **`start-building-for-startups`** — interactive discovery workflow that gathers requirements via picker questions and writes an AWS architectural scaffold directly into the user's codebase.
- **`migration-to-aws`** — Plan a migration from Google Cloud Platform — and OpenAI/Gemini AI workloads — to AWS, directly in your IDE. The plugin runs a guided, multi-phase workflow: discover resources from Terraform/IaC, app code, and GCP billing exports; design an AWS architecture; estimate costs; and generate migration artifacts. AI-provider migration maps OpenAI/Gemini usage to closest-fit Amazon Bedrock model families. Processing is local — your data stays in your environment. Requires MCP servers (see below).

The skills are designed to be cross-aware — `start-building-for-startups` consults `knowledge-base-for-startups` and `prompt-library-for-startups` mid-flow; `knowledge-base-for-startups` and `prompt-library-for-startups` defer to each other on boundary queries; and migration intent routes to `migration-to-aws`.

## MCP servers

The `migration-to-aws` skill depends on two MCP servers, declared in `advisor/plugins/aws-startup-advisor/.mcp.json` and provisioned automatically when the plugin is installed:

- **AWS Knowledge** (`awsknowledge`, HTTP) — current AWS documentation lookups.
- **AWS Pricing** (`awspricing`, stdio via `uvx awslabs.aws-pricing-mcp-server`) — live pricing data for cost estimates. Requires [`uv`/`uvx`](https://docs.astral.sh/uv/) on the user's machine.

The other three skills do not require MCP servers.

---

## Install

**Prerequisite:** Node.js 18+ (ships with `npx`). Grab the LTS or current release for your OS from [nodejs.org/en/download](https://nodejs.org/en/download). Verify with `node -v && npx -v`.

Install all skills at once into a single agent:

```bash
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' --agent <agent>
```

`--skill '*'` selects every skill in the plugin; pair it with `--agent <agent>` to scope the installation to a single coding agent. The CLI writes each skill into the right per-agent folder; restart your agent afterward to pick them up.

> **If you omit `--agent`, the CLI shows an interactive picker.** Use the **space bar** to select your agent (e.g. Claude Code, Kiro), then press **Enter** to confirm. If you press Enter without selecting, nothing gets selected and the CLI falls back to writing the skills into `.agents/skills/` — which most agents won't discover, so your agent ends up empty-handed. Either select with space, or pass `--agent <agent>` explicitly to skip the picker.

### Examples

```bash
# Kiro
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' --agent kiro-cli

# Claude Code
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' --agent claude-code

# Cursor
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' --agent cursor

# Install all skills into all auto-detected agents on your machine
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' --agent '*'

# Install globally (cross-project)
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*' --agent kiro-cli --global
```

### Install only one skill

```bash
# Just the knowledge base
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill knowledge-base-for-startups --agent <agent>

# Just the prompt library
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill prompt-library-for-startups --agent <agent>

# Just the build workflow
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill start-building-for-startups --agent <agent>

# Just the migration workflow
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill migration-to-aws --agent <agent>
```

### Supported `--agent` values

| Agent          | `--agent`        |
| -------------- | ---------------- |
| Kiro           | `kiro-cli`       |
| Claude Code    | `claude-code`    |
| Cursor         | `cursor`         |
| Codex          | `codex`          |
| GitHub Copilot | `github-copilot` |
| OpenCode       | `opencode`       |
| Continue       | `continue`       |
| Windsurf       | `windsurf`       |
| Gemini CLI     | `gemini-cli`     |

Full list of supported agents: [vercel-labs/skills — Supported Agents](https://github.com/vercel-labs/skills#supported-agents).

---

## Try it

Once installed, ask your agent:

| Prompt                                                          | Skill that handles it                                                                                           |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| _"Do AWS Activate Credits expire?"_                             | `knowledge-base-for-startups` → `references/faq.md`                                                             |
| _"Find startups articles on cost optimization for early stage"_ | `knowledge-base-for-startups` → `references/learn.md` index → an article file                                   |
| _"What partner offers help with observability?"_                | `knowledge-base-for-startups` → `references/offers.md` index                                                    |
| _"Show me a sample architecture for RAG on Bedrock"_            | `knowledge-base-for-startups` → `references/build.md`                                                           |
| _"Give me a prompt for an MVP on AWS"_                          | `prompt-library-for-startups` → `awsome-mvp-builder.md`                                                         |
| _"Prompt for a RAG chatbot using Claude on Bedrock"_            | `prompt-library-for-startups` → `rag-chatbot-with-claude.md`                                                    |
| _"Help me migrate workloads from GCP to AWS"_                   | `migration-to-aws` → 6-phase migration workflow                                                                 |
| _"Help me build a SaaS app on AWS"_                             | `start-building-for-startups` → discovery workflow → scaffolded code                                            |
| _"How do I start with RAG?"_                                    | `knowledge-base-for-startups` (learn article) + `prompt-library-for-startups` (starter prompt) — boundary query |

---

## Uninstall

```bash
npx skills remove knowledge-base-for-startups --agent <agent>
npx skills remove prompt-library-for-startups --agent <agent>
npx skills remove start-building-for-startups --agent <agent>
```
