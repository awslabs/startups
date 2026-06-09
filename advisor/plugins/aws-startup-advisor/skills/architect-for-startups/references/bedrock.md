# Bedrock
## Model Selection

The model choice is the single biggest cost and quality decision. Get this right first.

| Need                                  | Recommended Model          | Why                                                   |
|---------------------------------------|----------------------------|-------------------------------------------------------|
| Classification, routing, extraction   | Nova Micro or Claude Haiku | Fast, cheap, accurate for structured tasks            |
| General Q&A, summarization            | Nova Lite or Nova Pro      | Strong quality-to-cost ratio                          |
| Multimodal (image + text)             | Nova Lite                  | Cost-effective vision without Sonnet pricing          |
| Complex reasoning, nuanced generation | Claude Sonnet              | Best balance of capability and cost                   |
| Hardest problems, highest quality bar | Claude Opus                | Reserve for tasks where Sonnet falls short            |
| Embeddings                            | Titan Embed v2             | Cheaper than Cohere, solid quality for most use cases |
| Code generation                       | Claude Sonnet              | Strong code quality without Opus pricing              |

**Note**: Model availability and pricing change frequently. Verify current options via `awsknowledge` MCP tools before making final recommendations.

### Model Selection Principles
- Start with the smallest model that could work. Upgrade only when evidence shows it falls short.
- Benchmark on real data, not generic benchmarks. A smaller well-prompted model often beats a larger general one.
- Use Bedrock's intelligent prompt routing to auto-route requests to the right model tier.
- Evaluate the Nova family before defaulting to third-party models — Nova Pro offers comparable quality to Claude Sonnet for many tasks at significantly lower cost per token, and Nova Lite/Micro provide sub-100ms latency for classification and routing tasks where you don't need full reasoning capability. Nova models also have no cross-provider data transfer fees and deeper native Bedrock integration (Guardrails, Knowledge Bases, Flows).

## Bedrock Agents

### Design Principles
- One agent, one job. If the agent description contains "and", consider splitting.
- Fewer tools = fewer reasoning steps = faster + cheaper. 3-5 tools is the sweet spot.
- Use direct `InvokeModel` for simple tasks. Not everything needs an agent.

### Architecture Patterns

**Router + Specialists**: A lightweight classifier (Nova Micro) routes to specialized agents. Each specialist has a focused tool set and optimized prompt. This beats one mega-agent with 20 tools.

**Knowledge Base + Guardrails**: For customer-facing Q&A — KB for retrieval, guardrails for safety, single model call for generation. No agent orchestration needed; use `RetrieveAndGenerate` API directly.

**Agent with Session Memory**: For multi-turn conversations — use AgentCore sessions with memory. Let the agent maintain context across turns instead of stuffing history into the prompt each time.

### Action Groups
- Use Lambda-backed action groups for complex logic
- Use Return Control for client-side tool execution (keeps agent stateless, avoids Lambda cost)
- Define OpenAPI schemas tightly — vague schemas cause the model to guess (and guess wrong)

## Knowledge Bases

### Chunking Strategy
- **Fixed-size chunking** (default): Good starting point. 300-500 tokens with 10-20% overlap.
- **Semantic chunking**: Better quality, higher embedding cost. Use for high-value, heterogeneous documents.
- **Hierarchical chunking**: Best for long documents with clear structure (manuals, legal docs).
- Curate the data source — garbage in, garbage out applies doubly to RAG.

### Vector Store Selection
- **OpenSearch Serverless**: Default choice. Managed, scales, integrates natively.
- **Aurora PostgreSQL (pgvector)**: Good if already running Aurora — consolidates infrastructure.
- **Pinecone / Redis**: If existing investments in these stores.
- For PoCs, share a single OpenSearch Serverless collection across multiple KBs to minimize cost.

### Retrieval Tuning
- Start with hybrid search (semantic + keyword) — outperforms pure semantic for most workloads
- Tune retrieved chunk count (default 5). More chunks = more context = more input tokens. Find the minimum that gives good answers.
- Use metadata filtering to scope retrieval — avoid searching everything when the document category is known.

## Guardrails
- Apply to user-facing inputs and outputs. Skip for internal agent reasoning steps.
- Content filters are cheaper than denied topic policies — use filters for broad categories, denied topics for specific restrictions.
- Contextual grounding checks catch hallucination at inference time — useful for RAG apps.
- PII detection/redaction is built in — use it instead of building custom regex.

## Anti-Patterns

- **Defaulting to the biggest model "just to be safe"** — start small, upgrade with evidence
- **Building an agent when a single InvokeModel call would do** — agents compound cost per turn
- **Stuffing entire documents into prompts instead of using Knowledge Bases** — RAG is cheaper and more maintainable
- **Ignoring prompt caching** — it is automatic for supported models, just structure prompts correctly
- **Using on-demand for bulk processing that could be batch** — 50% savings left on the table
- **One massive Knowledge Base instead of scoped, curated collections** — hurts retrieval quality and costs more
- **Skipping guardrails on user-facing apps** — "we'll add them later" becomes a security incident
- **Not monitoring token usage** — costs sneak up fast during iteration, especially with agents

## Output Format

When advising on a Bedrock solution:

| Component              | Choice                               | Rationale                                                      |
|------------------------|--------------------------------------|----------------------------------------------------------------|
| Primary model          | Claude Sonnet                        | Complex reasoning required, cost-effective for the quality bar |
| Routing model          | Nova Micro                           | Cheap classifier for request triage                            |
| Architecture           | Router + Specialist agents           | 3 focused agents vs 1 mega-agent                               |
| Knowledge Base         | OpenSearch Serverless, hybrid search | Best retrieval quality, managed infrastructure                 |
| Guardrails             | Content filters + PII redaction      | Customer-facing surface                                        |
| Estimated monthly cost | $X,XXX                               | Use MCP servers available to estimate the cost                 |

Include cost profile and watch-out-for items specific to the use case.
