# PR #68 Review: ai-to-aws plugin

## Fixes before merge

### 1. `ChatBedrock` → `ChatBedrockConverse` (merge blocker)

The rewriter's §8 LangChain example and behavior-delta snippets use `ChatBedrock`, but the analyzer's own schema example says `ChatBedrockConverse`. `ChatBedrock` targets the legacy `InvokeModel` API; `ChatBedrockConverse` uses the Converse API (which is what the rest of the plugin standardizes on).

**Fix:** In `agents/ai-code-rewriter.md` §8 LangChain example, change:

```python
# Current (wrong)
from langchain_aws import ChatBedrock
llm = ChatBedrock(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-east-1")

# Should be
from langchain_aws import ChatBedrockConverse
llm = ChatBedrockConverse(model_id="us.anthropic.claude-sonnet-4-20250514-v1:0", region_name="us-east-1")
```

Also update any behavior-delta code examples that reference `ChatBedrock`.

### 2. README IAM permissions incomplete

Prerequisites list only `bedrock:InvokeModel`. The plugin's own `bedrock-iam-inference-profile.md` correctly requires `bedrock:InvokeModelWithResponseStream` for streaming migrations. Update the README prerequisites to:

```
- AWS credentials with `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` permissions
```

Or just use the wildcard: `bedrock:InvokeModel*`.

### 3. README cost guidance is optimistic for Sonnet

"Typically cents to a few dollars" is true for Haiku. For Sonnet 4 at the stated cap (200 cases × up to 4096 output tokens), worst case is ~$12–15 in Bedrock eval cost alone. Suggest splitting:

> - **Haiku evaluation:** typically cents to a few dollars
> - **Sonnet evaluation:** up to ~$12–15 worst case at full 200-case cap

### 4. `bedrock-iam-inference-profile.md` uses `invoke-model` for verification

This reference uses `aws bedrock-runtime invoke-model` as its verification step, but the rest of the plugin standardizes on Converse. For internal consistency, the verification example should use `converse` instead.

### 5. PR body checklist

The PR description is still the empty template with unchecked boxes. Fill it before merge.

### 6. `llm-to-bedrock/SKILL.md` — clarify skill naming

Note that `gcp-to-aws` handles AI-only workloads with no GCP infra. Users migrating off OpenAI with no GCP footprint will find the `gcp-to-aws` skill name confusing. A one-line note in the SKILL.md ("This skill also covers pure AI/LLM migrations with no infrastructure component") would help.

---

## Marketplace and README updates needed on merge

### 7. `migrate/plugins/.agents/plugins/marketplace.json` — add `ai-to-aws`

Currently only lists `migration-to-aws`. Add:

```json
{
  "name": "ai-to-aws",
  "source": {
    "source": "local",
    "path": "./ai-to-aws"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```

### 8. `migrate/plugins/.cursor-plugin/marketplace.json` — add `ai-to-aws`

Currently only lists `migration-to-aws`. Add:

```json
{
  "name": "ai-to-aws",
  "source": "./ai-to-aws",
  "description": "End-to-end AI migration to Amazon Bedrock: assess your codebase, rewrite SDK calls, evaluate quality, and deliver a ready-to-merge git branch. Requires migration-to-aws (powers the Assess phase)."
}
```

### 9. Per-plugin manifests for Cursor/Codex discovery

For full parity with `migration-to-aws`, the following files should exist inside `migrate/plugins/ai-to-aws/`:

- `migrate/plugins/ai-to-aws/.cursor-plugin/plugin.json`
- `migrate/plugins/ai-to-aws/.codex-plugin/plugin.json`

Without these, Cursor/Codex won't recognize the directory as a valid plugin even if the parent marketplace lists it.

### 10. `.claude-plugin/marketplace.json` — update `migration-to-aws` description

The PR already adds `ai-to-aws` here (good), but the `migration-to-aws` description still says "Migrate from GCP to AWS" with no mention that an execute companion now exists. Consider:

> "Assess & plan your migration from GCP to AWS — including your entire AI stack. Pair with ai-to-aws to execute AI/LLM migrations automatically."

### 11. `migrate/README.md` — add plugins table entry

The parent README's plugins table only shows `migration-to-aws`. Add `ai-to-aws`:

| Plugin               | Description                                                                                  | Status    |
| -------------------- | -------------------------------------------------------------------------------------------- | --------- |
| **migration-to-aws** | Assess & plan: resource discovery, architecture mapping, cost analysis, execution planning   | Available |
| **ai-to-aws**        | Execute: rewrite LLM SDK calls to Bedrock, evaluate quality, deliver a ready-to-merge branch | Available |

### 12. `migrate/plugins/ai-to-aws/.mcp.json` — add MCP config

For parity with `migration-to-aws` (which ships `.mcp.json` and `mcp.json`), add an MCP config to `ai-to-aws`. The execution agents use `bedrock_pricing.py` locally but the Assess phase delegates to `migration-to-aws`'s MCP servers. At minimum, copy the `awsknowledge` server config so the plugin is self-describing when inspected in isolation.

### 13. Root `.agents/plugins/marketplace.json` — add `ai-to-aws`

In addition to item #7 (`migrate/plugins/.agents/plugins/marketplace.json`), check if a root-level `.agents/plugins/marketplace.json` exists. If so, add `ai-to-aws` there too — this is the top-level Codex/Agents discovery file:

```json
{
  "name": "ai-to-aws",
  "source": {
    "source": "local",
    "path": "./migrate/plugins/ai-to-aws"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```

### 14. `ai-to-aws/README.md` — add Cursor/Codex install instructions

Once the `.cursor-plugin/plugin.json` and `.codex-plugin/plugin.json` manifests are created (item #9), add install instructions to the `ai-to-aws` README matching the pattern in `migration-to-aws`:

````markdown
### Codex

\```bash
codex plugin marketplace add awslabs/startups
codex plugin install ai-to-aws
\```

### Cursor

> Install via the Cursor plugin marketplace once published, or point Cursor
> to the local plugin directory.
````

---

## Suggestion: `bedrock-mantle` as a rewrite strategy tier (fast follow)

### The idea

The rewriter's §8 strategy for raw SDK users (OpenAI/Anthropic) does a full rewrite to boto3 `converse()`. But `bedrock-mantle` natively supports the OpenAI Chat Completions API and Anthropic Messages API — meaning some raw SDK migrations can be a 2-line change:

```python
# Before
from openai import OpenAI
client = OpenAI()

# After (bedrock-mantle — keep the same SDK)
from openai import OpenAI
client = OpenAI(
    base_url="https://bedrock-mantle.us-east-1.api.aws/v1",
    api_key=os.environ["BEDROCK_API_KEY"]
)
```

Same for Anthropic direct:

```python
# Before
import anthropic
client = anthropic.Anthropic()

# After (bedrock-mantle — keep the same SDK)
import anthropic
client = anthropic.Anthropic(
    base_url="https://bedrock-mantle.us-east-1.api.aws/anthropic/v1",
    api_key=os.environ["BEDROCK_API_KEY"]
)
```

### Critical caveat: Mantle is NOT universal

**Claude Sonnet 4 (the PR's primary example model) is NOT available on bedrock-mantle.** Per [endpoint availability docs](https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html):

| Model             | bedrock-runtime | bedrock-mantle |
| ----------------- | :-------------: | :------------: |
| Claude Sonnet 4   |       ✅        |       ❌       |
| Claude Sonnet 4.5 |       ✅        |       ❌       |
| Claude Sonnet 4.6 |       ✅        |       ❌       |
| Claude Haiku 4.5  |       ✅        |       ✅       |
| Claude Opus 4.7   |       ✅        |       ✅       |
| Claude Opus 4.8   |       ✅        |       ✅       |
| Claude Fable 5    |       ✅        |       ✅       |
| Claude Mythos 5   |       ❌        |       ✅       |

For the most common migration target (Sonnet 4 replacing GPT-4o), **Converse on bedrock-runtime is the only path.** The PR's current approach is correct for this case.

The Mantle express lane applies only when:

1. Target model is available on bedrock-mantle, AND
2. User doesn't need Converse-only features (guardrails, cross-model format standardization), AND
3. User doesn't need geo inference profiles (Mantle doesn't support `us.` prefix routing)

### Tradeoffs vs Converse

|                         | bedrock-mantle                          | Converse API (bedrock-runtime)        |
| ----------------------- | --------------------------------------- | ------------------------------------- |
| Code change effort      | Minimal (2 lines + model ID)            | Full rewrite                          |
| Model availability      | Limited (Haiku 4.5, Opus 4.7+, Fable 5) | All Bedrock models                    |
| Geo inference profiles  | ❌ Not supported                        | ✅ Supported                          |
| Response format rewrite | None needed                             | Required                              |
| API key auth            | ✅ Supported                            | SigV4 (or API key on bedrock-runtime) |
| Guardrails integration  | Limited (extra headers)                 | Full native support                   |
| Cross-model portability | Tied to OpenAI/Anthropic format         | Works across all Bedrock models       |

### Recommendation

Add a strategy tier to §8 where the rewriter offers `bedrock-mantle` as the "express lane" for raw SDK migrations **when the target model supports it** (primarily Haiku-class cost-optimized workloads), defaulting to the full Converse rewrite for Sonnet/Opus targets. Check endpoint availability per target model before offering this path.

This is a fast follow, not a merge blocker — the PR's Converse-first approach is correct for the primary use case (Sonnet migrations).
