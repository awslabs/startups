# OpenAI Models on Amazon Bedrock

**Point-in-time public snapshot:** 2026-11-04
**Sources:** [Inference endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html),
[Endpoint availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html),
[API compatibility](https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html), and
[OpenAI model cards](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards-openai.html).

This file is the plugin's OpenAI-on-Bedrock fact base. It contains public, time-sensitive
metadata only. Current AWS documentation and a target-account probe override this snapshot.

## Endpoint policy

Use `bedrock-runtime` for most new applications. Preserve the source OpenAI API with
`runtime_openai_responses` or `runtime_openai_chat` when the selected model supports it.
Select `bedrock-mantle` only for a verified requirement:

- background/asynchronous Responses inference;
- general server-side or preconfigured tools, including Web Search;
- customer-created Projects;
- a required model/API combination unavailable on Runtime; or
- strict in-Region processing when the model's Runtime form is CRIS-only.

API continuity, ordinary client-side tool calling, stored Responses conversations, or a model
appearing on both endpoints does not select Mantle. Runtime Responses supports stored state;
Runtime is synchronous and uses the default project.

## Live eligibility gate

Before every recommendation, read the selected model card and verify all four dimensions:

1. **Endpoint availability** for Runtime and Mantle.
2. **Programmatic Access**, including bare versus geographic/Global inference-profile IDs.
3. **API compatibility** for Responses, Chat Completions, Converse, or Invoke.
4. **Regional availability**, including CRIS source and destination Regions.

Then probe the exact endpoint, API, Region, and invocation model ID in the target account.
Endpoint support does not prove API or Region support.

## GPT-5.4 and GPT-5.5 public snapshot

Current public model cards list both models on Runtime through Geo or Global CRIS and on
Mantle for in-Region inference. Both cards document Responses and Chat Completions. Runtime
has no bare in-Region ID for these models in this snapshot.

| Model   | Mantle ID        | Runtime CRIS IDs                             | OpenAI-compatible APIs      |
| ------- | ---------------- | -------------------------------------------- | --------------------------- |
| GPT-5.5 | `openai.gpt-5.5` | `us.openai.gpt-5.5`, `global.openai.gpt-5.5` | Responses, Chat Completions |
| GPT-5.4 | `openai.gpt-5.4` | `us.openai.gpt-5.4`, `global.openai.gpt-5.4` | Responses, Chat Completions |

Do not generalize these rows to another model or future date. Re-read its card.

## Hosts, credentials, and IAM

| Path           | Base URL                                                   | ID form                 | IAM family                                                                 |
| -------------- | ---------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------- |
| Runtime OpenAI | `https://bedrock-runtime.{region}.amazonaws.com/openai/v1` | current Runtime/CRIS ID | `bedrock:InvokeModel*`                                                     |
| Mantle OpenAI  | `https://bedrock-mantle.{region}.api.aws/openai/v1`        | documented bare ID      | `CreateInference`, `GetProject`, `ListProjects`, and `CallWithBearerToken` |

Use an auto-refreshing short-lived Bedrock token provider for long-running services. Never
reuse an OpenAI API key, commit a token, pair a bare Mantle ID with Runtime, or pair a prefixed
Runtime CRIS ID with Mantle.

## Endpoint and routing pricing

For the same model and routing option, public endpoint guidance says per-token pricing is the
same across Runtime and Mantle. Routing still changes price. Current cards can price in-Region
and geographic CRIS differently from Global CRIS, and Global routing has broader data-residency
implications. GPT-5.4 and GPT-5.5 point-in-time rates published by the cited model-card pricing
sections are:

| Model   | In-Region / US Geo input · output per 1M | Global CRIS |
| ------- | ---------------------------------------- | ----------- |
| GPT-5.5 | $5.50 · $33.00                           | Unverified  |
| GPT-5.4 | $2.75 · $16.50                           | Unverified  |

The public sections cited here do not publish a distinct price for the `global.` GPT-5.4 or
GPT-5.5 IDs. Treat pricing for those IDs as unavailable unless a current public AWS source
explicitly lists it; do not derive it from OpenAI's standard rates.

Never infer availability from a price row or price from an endpoint row. Revalidate the model
card's pricing, context tier, API, and Region immediately before estimating. A cached amount is
an estimate, not a quote.

## Throughput

Runtime uses combined per-model token quotas and model-specific RPM quotas where applicable.
Mantle has no RPM quota and uses separate input/output TPM quotas where published. Use bounded
concurrency and request queues, token-aware admission, `Retry-After`, and exponential backoff
with jitter under a finite retry budget. See [Runtime quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-runtime.html),
[Mantle quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-mantle.html), and
[scaling best practices](https://docs.aws.amazon.com/bedrock/latest/userguide/scaling-throughput-best-practices.html).

## Refresh checklist

1. Re-read the endpoint matrix and selected model card.
2. Re-check Programmatic Access, API compatibility, Region/CRIS routing, and model lifecycle.
3. Re-check endpoint-versus-routing prices and context tiers.
4. Update `pricing-cache.md` only from a current public source.
5. Keep customer-facing rationale free of private documents or non-public probe provenance.
