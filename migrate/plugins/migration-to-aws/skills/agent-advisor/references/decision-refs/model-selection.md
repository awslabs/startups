# Bedrock Model Selection (mapping only — no pricing)

The deterministic authority is `scripts/model_recommendation.py`, which dispatches each
workload to a provider module and a dated public-source catalog. Runtime scoring does not own
model selection, and model choice never changes the selected compute runtime.

## Endpoint policy

Use `bedrock-runtime` by default. Select `bedrock-mantle` only after a current public model card
and a target-account check establish one of these requirements:

- background or long-running Responses inference;
- server-side or preconfigured tools, including Web Search;
- customer-created OpenAI Projects or Anthropic Workspaces;
- a required model/API combination unavailable on `bedrock-runtime`; or
- strict in-Region processing when the supported Runtime form is CRIS-only.

API continuity alone does not select Mantle. Runtime exposes the OpenAI Responses and Chat
Completions APIs and the Anthropic Messages API. Client-side tool calling and ordinary stored
Responses continuation also work on Runtime.

| API need                      | Default path               | Mantle exception                                        |
| ----------------------------- | -------------------------- | ------------------------------------------------------- |
| OpenAI Responses              | `runtime_openai_responses` | `mantle_openai_responses` for a verified selector above |
| OpenAI Chat Completions       | `runtime_openai_chat`      | `mantle_openai_chat` for a verified selector above      |
| Anthropic Messages            | `runtime_messages`         | `mantle_messages` for a verified selector above         |
| Shared Bedrock-native surface | `runtime_converse`         | none                                                    |
| Provider-native Bedrock body  | `runtime_invoke`           | none                                                    |

Public sources: [inference endpoint comparison](https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html),
[OpenAI Chat Completions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions.html),
[Anthropic Messages](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-messages-api.html),
and [endpoint availability by model](https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html).

## Joint model/path decision

- **Anthropic** uses `scripts/anthropic_model_recommendation.py` and
  `references/models/anthropic-bedrock-2026-07-21.json`.
- **OpenAI** uses `scripts/openai_model_recommendation.py` and
  `references/models/openai-bedrock-2026-08-21.json`.
- **Azure OpenAI / other** remains `provider_module_pending` until a dedicated module exists.

The engine applies these rules:

- A dated snapshot is provisional. Every result carries `region`, `catalog_verified_at`, and a
  required live probe of the exact `(invocation_model_id, api_path)` pair.
- Unknown model/API or Region support produces `decision_required` or an unresolved verification,
  never an inferred path.
- Logical model identity, path model ID, and invocation/CRIS ID remain distinct. The verifier
  never substitutes another model.
- A hard Mantle-only requirement that conflicts with an explicit Converse or Invoke requirement
  stays `decision_required` until the user chooses which requirement to keep.

## Priority and specialized features

`priority` (`quality | balanced | speed | cost | unknown`) orders candidates before hard
capability and path filters. `model_features` is a hard capability filter. A common feature such
as client-side tool use does not force Mantle or a larger model when a cheaper candidate has
current evidence.

Image generation, speech, and embeddings are separate target contracts rather than text-model
swaps. Detailed pricing and migration execution belong to `llm-to-bedrock`.

The selectable model pool is drift-guarded against
`skills/shared/ai/ai-model-lifecycle.md`; Legacy or EOL models cannot enter the pool.
