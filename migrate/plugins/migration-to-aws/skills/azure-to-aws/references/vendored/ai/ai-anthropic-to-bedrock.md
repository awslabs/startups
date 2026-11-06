# Anthropic SDK → Amazon Bedrock Migration

> Canonical Anthropic-SDK → Bedrock client-swap guide. Source-cloud agnostic:
> the mapping depends on the SDK the code uses, never on which cloud hosted it.
> Vendored into each consuming skill as
> `references/vendored/ai/ai-anthropic-to-bedrock.md` and kept byte-identical by
> `shared:check`; edit HERE, then run `shared:sync`.
>
> Loaded by `design-ai.md` when `ai_source == "anthropic"`.
> The user is already on Claude via the Anthropic SDK. Migration is a client swap only.
> No model change, no prompt rewriting, no retraining required.

---

## Step 1: Map model IDs to Bedrock

| Anthropic SDK model | Bedrock model ID                           | Tier     | Input/Output per 1M |
| ------------------- | ------------------------------------------ | -------- | ------------------- |
| `claude-opus-4-*`   | `anthropic.claude-opus-4-8`                | Premium  | $5 / $25            |
| `claude-sonnet-5-*` | `anthropic.claude-sonnet-5`                | Flagship | $2 / $10 intro†     |
| `claude-sonnet-4-*` | `anthropic.claude-sonnet-5`                | Flagship | $2 / $10 intro†     |
| `claude-haiku-4-*`  | `anthropic.claude-haiku-4-5-20251001-v1:0` | Fast     | $1 / $5             |

† Claude Sonnet 5 intro pricing through Aug 31, 2026; then $3 / $15 (same as Sonnet 4.6). Prefer the `us.` inference-profile prefix for on-demand invoke. Sonnet 4.6 (`anthropic.claude-sonnet-4-6`) remains Active if the customer must stay on the 4.6 SKU.

Older Claude models — Claude 3.5 Haiku, Claude 3 Sonnet, Claude 3.5 Sonnet (v1/v2), Claude 3 Haiku, and Claude 3.7 Sonnet — are past EOL or within the 90-day exclusion window. Do **not** recommend them as migration targets. See `references/vendored/ai/ai-model-lifecycle.md` for authoritative status (recomputed each run).

**Recommendation:** Default new Bedrock targets to **Claude Sonnet 5** (flagship) / **Claude Opus 4.8** (hardest reasoning) / **Claude Haiku 4.5** (cost/speed). Converse API call shape is identical across generations. Do **not** default to Claude Fable 5 (frontier / Mythos-class pricing — opt-in only).

---

## Step 2: Select the endpoint and API

Use `bedrock-runtime` with the Anthropic Messages API for a supported model in a supported
Region. This is the default for new migrations because it preserves the source SDK and
Messages request/response shape. Select `bedrock-mantle` only after current public documentation
verifies a requirement for a customer-created Workspace, background inference, a general
server-side/preconfigured tool, a model/API combination unavailable on Runtime, or strict
in-Region processing when Runtime is CRIS-only. Ordinary client-side tools and Messages API
continuity do not select Mantle.

Before selecting a path, check the current [Endpoint availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html),
[API compatibility](https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html),
model card Programmatic Access table, and Regional table. Record `runtime_messages` by default
or `mantle_messages` only for a verified selector.

---

## Step 3: Preserve the Anthropic client on Runtime

Keep `client.messages.create(...)` and its payload shape. Change the base URL to
`https://bedrock-runtime.{region}.amazonaws.com/anthropic/v1`, replace the source API key with
an auto-refreshing short-lived Bedrock token provider, and use the Runtime model or CRIS
inference-profile ID selected from the current model card. Do not commit source API keys or
short-lived tokens.

Use `boto3` Converse only when the user explicitly chooses the normalized Bedrock-native API
or needs a Converse-only feature. That is the `runtime_converse` path and requires translating
content blocks, parameter names, streaming events, and response parsing.

---

## Step 4: IAM and quotas

Runtime Messages uses `bedrock:InvokeModel` and, for streaming,
`bedrock:InvokeModelWithResponseStream`, scoped to the selected model or inference profile.
Mantle Messages uses the documented `bedrock-mantle` action family instead. Runtime has
per-model token quotas and model-specific RPM quotas where applicable; check Service Quotas
for the exact model and inference profile.

---

## Validation checklist

- [ ] Current Endpoint availability, API compatibility, Programmatic Access, and Region data were checked
- [ ] `runtime_messages` is used unless a verified Mantle selector applies
- [ ] `client.messages.create()` and the Anthropic payload shape are preserved on Runtime
- [ ] Runtime base URL includes `/anthropic/v1`
- [ ] Credentials are short-lived and auto-refreshing; the source API key is removed
- [ ] IAM actions and model-ID form match the selected endpoint
- [ ] The exact selected model and path were probed in the target account and Region
