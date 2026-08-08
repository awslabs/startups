# Install AWS Startup Advisor Skills

You are an AI coding agent. Follow these instructions exactly.

## Step 1: Check for Node.js

Run:

```bash
node -v
```

If this fails with "command not found", tell the user:

> "Node.js is required but not installed. Download it from https://nodejs.org (LTS recommended), install it, then ask me to try again."

Stop here until Node.js is available. Do not proceed without it.

## Step 2: Install the skills

Run:

```bash
npx skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*'
```

If prompted "Ok to proceed? (y)", respond yes.

If the command fails with an npm authentication or registry error, retry with the public registry:

```bash
npx --registry https://registry.npmjs.org skills add https://github.com/awslabs/startups/tree/main/advisor/plugins/aws-startup-advisor --skill '*'
```

## Step 3: Confirm success

The output should show 5 installed skills:

- `architect-for-startups`
- `knowledge-base-for-startups`
- `migration-to-aws`
- `prompt-library-for-startups`
- `start-building-for-startups`

If all 5 appear, tell the user:

> "AWS Startup Advisor skills are installed. You can now ask me about credits, partner offers, architecture for your startup stage, migration from GCP, or I can scaffold a new app for you.
>
> Try asking:
>
> - 'Do my AWS Activate credits expire?'
> - 'What partner offers help with observability?'
> - 'Scaffold a serverless API for my startup'
> - 'Help me migrate from GCP to AWS'
> - 'Give me a prompt for an MVP on AWS'"

If any skill failed to install, show the error output to the user and suggest they retry the command manually in their terminal.

## What these skills do

- **knowledge-base-for-startups** — AWS Activate credits, programs, partner offers, sample architectures, and hundreds of learn articles on topics like gen AI, cost optimization, security, and fundraising.
- **prompt-library-for-startups** — 30 curated prompts (MVP scaffolding, RAG chatbot, security baseline, cost anomaly detection, GPU quota, EKS deployment, Well-Architected review) plus 4 downloadable agents (Migration, Multi-Account Transition Advisor, Bill Shock Preventer, Service Quota Agent).
- **architect-for-startups** — Stage-aware architecture advice that adjusts recommendations based on whether you're pre-revenue, seed, Series A, or Series B+. Factors in team size, runway, credits, and timeline.
- **start-building-for-startups** — Interactive discovery workflow. Scans your codebase, asks about your goals and constraints, then writes an AWS architectural scaffold directly into your project.
- **migration-to-aws** — 6-phase migration from GCP or AI providers (OpenAI, Gemini, LangChain) to AWS. Discovers resources, designs architecture, estimates costs, generates Terraform artifacts.

## No AWS credentials required

These skills are offline reference content and agent instructions. They do not call AWS APIs and do not require AWS credentials to install or use. Some skills (like `start-building-for-startups` and `migration-to-aws`) may call AWS APIs during execution if the user has credentials configured, but installation itself is credential-free.
