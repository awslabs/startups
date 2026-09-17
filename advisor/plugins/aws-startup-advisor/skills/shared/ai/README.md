# Shared AI references (canonical)

Plugin-neutral, source-cloud-agnostic AI migration content. Each file here is the
single source of truth and is vendored into every consuming skill at
`references/vendored/ai/<same name>`, kept byte-identical by `shared:check`.
**Edit here, never in a vendored copy**, then run `shared:sync`.

| File                                 | What it owns                                                   |
| ------------------------------------ | -------------------------------------------------------------- |
| `ai-model-lifecycle.md`              | Bedrock Active/Legacy/EOL registry + the 90-day exclusion rule |
| `ai-migration-guardrails.md`         | Shared constraints for every agentic migration path            |
| `bedrock-quotas.md`                  | TPM/RPM quota-risk assessment (works without an AWS account)   |
| `ai-openai-to-bedrock.md`            | OpenAI-protocol (incl. Azure OpenAI) → Bedrock model selection |
| `ai-anthropic-to-bedrock.md`         | Anthropic SDK → Bedrock Converse client swap                   |
| `design-ref-harness.md`              | AgentCore Harness design reference                             |
| `design-ref-agentic-to-agentcore.md` | Strands Agents + AgentCore Runtime design reference            |
| `sdk-capability-map.json`            | SDK method → capability lookup used by app-code discovery      |

Deliberately NOT here: a source-cloud's own mapping guide (e.g. gcp-to-aws's
`ai-gemini-to-bedrock.md`) and its `schema-discover-ai.md`, both of which are
written against one provider's SDK surface.

**Consumer contract.** A skill that vendors `references/vendored/ai/` must also ship
`references/shared/pricing-cache.md` and `references/shared/pricing-fallback.md` —
the files below reference them by that path for Bedrock model rates. They are
deliberately NOT part of this canonical set: `pricing-cache.md` doubles as some
skills' AWS-infrastructure rate card and carries source-provider rates, so it is
per-skill by design.
