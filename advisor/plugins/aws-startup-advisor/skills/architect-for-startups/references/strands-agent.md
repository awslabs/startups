# Strands Agent
## First: Clarify Language

Before writing any code, ask the user:

> **TypeScript or Python?** (TypeScript is recommended for new projects — it has strong typing, good DX, and first-class Strands support. Python is fully supported too.)

Default to TypeScript if the user doesn't have a preference.

## Observability & Tracing

Strands has OpenTelemetry built in. Every agent invocation, model call, and tool execution emits OTel spans automatically. You just configure where to send them.

- **AgentCore deployed agents**: OTel is enabled by default → CloudWatch Logs, X-Ray traces, GenAI dashboard
- **Local development**: Set `OTEL_EXPORTER_OTLP_ENDPOINT` to route to Jaeger, Grafana, Langfuse, etc.
- **Disable**: `agentcore configure --disable-otel`

## Evaluation with Strands Evals

Ship evals from day one. Strands Evals provides LLM-as-a-Judge evaluation with 9+ built-in evaluators:

- **OutputEvaluator**: Custom rubric-based quality scoring
- **TrajectoryEvaluator**: Did the agent use the right tools in the right order?
- **HelpfulnessEvaluator**: 7-point helpfulness scale
- **FaithfulnessEvaluator**: Is the response grounded in context? (anti-hallucination)
- **HarmfulnessEvaluator**: Safety check
- **ToolSelectionAccuracyEvaluator** / **ToolParameterAccuracyEvaluator**: Tool-level correctness
- **GoalSuccessRateEvaluator**: Did the user achieve their goal across a full session?
- **ActorSimulator**: Simulates realistic multi-turn users for conversation testing

> Evals are Python-only. Even for TypeScript agents, write your eval suite in Python.

## Memory Decision Guide

| Scenario                                 | Memory Mode | Notes                                                  |
|------------------------------------------|-------------|--------------------------------------------------------|
| Stateless tool-calling agent             | NO_MEMORY   | Simplest, cheapest                                     |
| Multi-turn conversation within a session | STM_ONLY    | 30-day retention, stores conversation history          |
| Personalization across sessions          | STM_AND_LTM | Extracts preferences, facts, summaries across sessions |

Memory is opt-in. Start without it, add when you need it.

## Gotchas

- **TypeScript agents need containerized deployment** — use `--deployment-type container` when configuring TS agents with the AgentCore CLI
- **Default model is Claude Sonnet** — Strands defaults to `global.anthropic.claude-sonnet-4-5-20250929-v1:0` via Bedrock. You need model access enabled in your AWS account.
- **AWS credentials required** — Strands uses Bedrock by default. Ensure `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are set, or use IAM roles.
- **Tool count matters** — more tools = more reasoning steps = slower + more expensive. Keep PoCs to 3-5 tools.
- **Zod is included** — `@strands-agents/sdk` bundles Zod for TypeScript tool input validation. No separate install needed.
- **Memory provisioning takes time** — STM: ~30-90s, LTM: ~120-180s. The CLI waits for ACTIVE status.
- **`agentcore destroy` deletes everything** — including memory resources. Use `--dry-run` first.
- **Session lifecycle** — idle timeout defaults to 900s (15min). Set `--idle-timeout` and `--max-lifetime` during configure if you need longer sessions.
- **VPC config is immutable** — once deployed with VPC settings, you can't change them. Create a new agent config instead.
- **OTel is on by default in AgentCore** — traces go to CloudWatch/X-Ray. Disable with `--disable-otel` if you don't want it.
- **Strands Evals is Python-only** — even for TypeScript agents, write evals in Python. The eval framework uses the same Bedrock models as your agent.
- **Evals cost money** — each LLM-as-a-Judge evaluation invokes a model. Use `callback_handler=None` in eval task functions to suppress console output.
- **Memory batching requires close()** — if using `batch_size > 1`, you MUST use a `with` block or call `close()` or buffered messages are lost.
