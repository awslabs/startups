# OpenAI to Bedrock — Model Selection Guide

> Canonical OpenAI-compatible → Bedrock model-selection guide. Source-cloud
> agnostic: it serves direct OpenAI API usage, Azure OpenAI, and any other
> OpenAI-protocol endpoint, because the Bedrock target does not depend on which
> endpoint served the calls.
> Vendored into each consuming skill as
> `references/vendored/ai/ai-openai-to-bedrock.md` and kept byte-identical by
> `shared:check`; edit HERE, then run `shared:sync`.

**Applies to:** OpenAI SDK usage detected in applications hosted on any source cloud → Amazon Bedrock

This file is loaded by `design-ai.md` when `ai-workload-profile.json` has `summary.ai_source` = `"openai"` or
`"both"`. It provides the selection policy and mapping tables for OpenAI → Bedrock migration decisions.

**Facts live in `references/shared/openai-on-bedrock.md`** — model IDs, endpoint paths, region matrix, quotas, prompt
caching rules, and pricing provenance. Read it before applying this file. Do not restate those facts here.

**Model lifecycle:** before recommending any Bedrock model, check `references/vendored/ai/ai-model-lifecycle.md`. Do not
recommend Legacy models as primary selections for new migrations.

**Recommend defaults (Sep 2026):** Claude Sonnet 5 (`anthropic.claude-sonnet-5`) for balanced/flagship; Claude Opus 4.8 for hardest reasoning; Claude Haiku 4.5 for cost/speed. Sonnet 5 is **$2/$10** — the launch rate became the standard price on Sep 1, 2026 (the scheduled increase to $3/$15 was cancelled); comparison tables below use $2/$10. Do not default to any Claude Fable / Mythos frontier model.

---

## Key Insight: OpenAI's Own Models Run on Bedrock

**The old premise of this guide — "OpenAI models are unavailable on AWS, so migrating means switching model families"
— is obsolete.** GPT-5.6 Sol / Terra / Luna, GPT-5.5, and GPT-5.4 are generally available on Bedrock, at OpenAI's
data-residency-tier rates, counting toward existing AWS commitments.

Two consequences that invert the previous decision logic:

1. **When the source model is on Bedrock, keep it.** A same-model move has no behavior delta to validate, no prompt
   re-engineering, and no eval regression risk — the migration is an endpoint and credential change, not a model
   change. This is the default recommendation.
2. **Price the selected routing option, not the endpoint name.** Public endpoint guidance says
   the same model and routing option has the same per-token price on Runtime and Mantle. In-Region,
   geographic CRIS, and Global CRIS can have different rates and residency implications. Recheck
   the current model card; do not assume GPT-5.4 or GPT-5.5 lacks Runtime CRIS.

Cross-family mapping (to Claude / Nova / DeepSeek) is still the right answer in two situations: the source model has
no Bedrock equivalent, or the user's priority is cost and is willing to accept a model change to get it. Both are
covered below — but neither is the default.

---

## Selection Policy

Use `bedrock-runtime` for most new applications. Preserve the source API with
`runtime_openai_responses` or `runtime_openai_chat` when the selected model supports that API.
Select Mantle only for a verified requirement: background inference, general server-side or
preconfigured tools including Web Search, customer-created Projects, a required model/API
combination unavailable on Runtime, or strict in-Region processing where Runtime is CRIS-only.
API continuity, ordinary client-side tools, stored Responses state, and endpoint availability
alone do not select Mantle.

Before choosing, revalidate the current [Endpoint availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-endpoint-availability.html),
[API compatibility](https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html),
model-card Programmatic Access, and Regional tables. Cached model IDs and endpoint facts are
hints, not proof.

Apply in order. Stop at the first tier that resolves.

### Tier 0 — Source model is on Bedrock (default path)

If the detected model is GPT-5.6 Sol / Terra / Luna, GPT-5.5, or GPT-5.4, the target is **the same model on
Bedrock**.

| Source model  | Bedrock target | Model ID (mantle / runtime CRIS)                        | Assessment                                                      |
| ------------- | -------------- | ------------------------------------------------------- | --------------------------------------------------------------- |
| GPT-5.6 Sol   | GPT-5.6 Sol    | `openai.gpt-5.6-sol` / `us.` `global.` prefixed         | `strong_migrate` — same model; parity on Global CRIS, else +10% |
| GPT-5.6 Terra | GPT-5.6 Terra  | `openai.gpt-5.6-terra` / `us.` `in.` `global.` prefixed | `strong_migrate` — same model; parity on Global CRIS, else +10% |
| GPT-5.6 Luna  | GPT-5.6 Luna   | `openai.gpt-5.6-luna` / `us.` `in.` `global.` prefixed  | `strong_migrate` — same model; parity on Global CRIS, else +10% |
| GPT-5.5       | GPT-5.5        | `openai.gpt-5.5` / current prefixed Runtime ID          | `strong_migrate` — same model; price by routing option          |
| GPT-5.4       | GPT-5.4        | `openai.gpt-5.4` / current prefixed Runtime ID          | `strong_migrate` — same model; price by routing option          |

Then apply the **region gate** below. Record `model_change: false` and the exact path in
`aws-design-ai.json` → `ai_architecture.code_migration`: `runtime_openai_responses` for a
supported Responses source, `runtime_openai_chat` for a supported Chat Completions source,
or a Mantle path only when a verified selector applies. Runtime uses the current model card's
prefixed CRIS ID when required; Mantle uses the documented bare model ID.

Report the assessment honestly: `strong_migrate` here means "low-risk, well-supported move", not "cheaper".

### Region gate (applies to every Tier 0 selection — endpoint-aware)

The gate differs by family (see `shared/openai-on-bedrock.md` § Regional Availability):

Check the selected model's current Endpoint availability, Programmatic Access, API
compatibility, and Regional tables. Runtime is the default when the model and source API are
supported. If Runtime is CRIS-only, choose the permitted geographic or Global profile and
state its routing and residency implications. Select Mantle for strict single-Region processing
only when its in-Region form is documented for that model and Region. If neither endpoint
supports the required model/API/Region combination, offer a Region change, a same-vendor model
change, and a cross-family option; do not silently substitute one. Record the outcome in
`regional_warnings[]`.

### Tier 1 — Source model is not on Bedrock (present two options, do not pre-pick)

Applies to GPT-4o, GPT-4.1, GPT-4 / GPT-4 Turbo, GPT-3.5 Turbo, the o-series, GPT-5 / 5.1 / 5.2, and all `*-Pro`
and `*-Mini` / `*-Nano` variants — none of which are on Bedrock.

There is no same-model target, so a model change is unavoidable. **Present both options with their trade-offs and
let the user choose.** Do not silently default to either.

| Option                              | What it means                                           | Trade-off                                                                                          |
| ----------------------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| **A) Stay with OpenAI, newer tier** | Move to the nearest GPT tier on Bedrock (table below)   | Same vendor, same prompt idioms and tool-calling semantics; still a generation change needing eval |
| **B) Cross-family**                 | Move to Claude / Nova / DeepSeek (tables further below) | Often materially cheaper; different prompt behavior, so budget for prompt work and eval            |

Option A tier mapping:

| Source tier                                              | Bedrock GPT target |
| -------------------------------------------------------- | ------------------ |
| Flagship reasoning (o1-pro, o3-pro, GPT-5 Pro, `*-Pro`)  | GPT-5.6 Sol        |
| Flagship general (GPT-4o, GPT-4.1, GPT-5/5.1/5.2, GPT-4) | GPT-5.6 Terra      |
| Mid / reasoning (o1, o3, o4-mini)                        | GPT-5.6 Terra      |
| Fast / cheap (`*-mini`, `*-nano`, GPT-3.5 Turbo)         | GPT-5.6 Luna       |

Option A is subject to the same region gate as Tier 0.

### Tier 2 — Cost priority override

If `ai_constraints.ai_priority == "cost"`, present the cheapest adequate Bedrock target **as an explicit
alternative alongside** the Tier 0 / Tier 1 recommendation — not as a replacement for it. The user asked for a
migration, and swapping model families is a bigger change than they may have signed up for; make the trade visible
rather than deciding for them.

See "Cost-optimized cross-family alternatives" below for the numbers.

---

## Cost-Optimized Cross-Family Alternatives

All figures per 1M tokens. Percentages are blended savings at a 2:1 input-to-output ratio. **Both sides of these
comparisons are now Bedrock prices** where the OpenAI model is on Bedrock — this is a Bedrock-vs-Bedrock model
choice, not a provider comparison. Verify rates via `shared/pricing-cache.md` or the AWS Pricing MCP, noting that
the Pricing MCP does not carry GPT-5.x (see `shared/openai-on-bedrock.md`).

### Against Tier 0 models (same-model baseline vs cross-family)

> Claude Sonnet 5 rows use $2/$10 — the launch rate, made the standard price on Sep 1, 2026 (the scheduled
> increase to $3/$15 was cancelled). Earlier revisions priced Sonnet 5 at $3/$15, which overstated it by a third
> and put several comparisons below on the wrong side.
>
> GPT-5.6 Sol rows use $4.40/$22.00 in-region — 1.10x the $4/$20 standard rate set by the Aug 21, 2026
> reduction, which AWS lists as promotional through at least Nov 21, 2026. The pre-reduction in-region
> rate was $5.50/$33.00; GPT-5.5 keeps that rate.

| Bedrock GPT baseline | Price        | Cross-family alternative | Price        | Delta                  |
| -------------------- | ------------ | ------------------------ | ------------ | ---------------------- |
| GPT-5.6 Sol          | 4.40 / 22.00 | Claude Opus 4.8          | 5.00 / 25.00 | Sol 12% cheaper        |
| GPT-5.6 Terra        | 2.20 / 13.20 | Claude Sonnet 5          | 2.00 / 10.00 | Sonnet 20% cheaper     |
| GPT-5.5              | 5.50 / 33.00 | Claude Sonnet 5          | 2.00 / 10.00 | Sonnet 68% cheaper     |
| GPT-5.5              | 5.50 / 33.00 | Claude Opus 4.8          | 5.00 / 25.00 | Opus 20% cheaper       |
| GPT-5.4              | 2.75 / 16.50 | Claude Sonnet 5          | 2.00 / 10.00 | Sonnet 36% cheaper     |
| GPT-5.6 Luna         | 0.22 / 1.32  | Claude Haiku 4.5         | 1.00 / 5.00  | **Luna 75% cheaper**   |
| GPT-5.6 Luna         | 0.22 / 1.32  | Nova Lite                | 0.06 / 0.24  | Nova Lite 80% cheaper  |
| GPT-5.6 Luna         | 0.22 / 1.32  | Nova Micro               | 0.035 / 0.14 | Nova Micro 88% cheaper |

Findings worth surfacing to users:

- **The Aug 21, 2026 Sol price cut flips the Sol↔Opus comparison.** GPT-5.6 Sol is now ~12% cheaper blended
  than Claude Opus 4.8, where Opus was previously 20% cheaper — but the cut is promotional (through at least
  Nov 21, 2026), so do not present the saving as durable.
- **GPT-5.6 Luna undercuts Claude Haiku 4.5 by ~75%.** For the fast/cheap tier, the OpenAI model is the cheaper
  Bedrock option. Do not reflexively map a cheap OpenAI model to Haiku on cost grounds.
- **Sonnet 5's now-permanent $2/$10 undercuts every same-family GPT tier except Luna.** It is ~20% cheaper than
  GPT-5.6 Terra and ~36% cheaper than GPT-5.4 blended; earlier revisions of this guide called Terra 19% cheaper and
  GPT-5.4 near parity on the cancelled $3/$15 rate. Cost now favors the cross-family move for Terra/GPT-5.4-class
  workloads — but it is still a model change; keep the same-model path as the default and present this as the
  cost alternative.
- **Every row above is short-context (272K).** For a >272K workload, re-run the comparison at the GPT-5.6 long-context
  tier (2.0x input, 1.5x output); Claude and Nova do not have an equivalent step, so the cross-family option becomes
  markedly cheaper.

### Sources with no Bedrock equivalent (cross-family reference)

Used for Tier 1 Option B. Source prices are OpenAI's own; Bedrock prices are the target.

| OpenAI Model                | Source price    | Cross-family target  | Bedrock price | Delta                                    |
| --------------------------- | --------------- | -------------------- | ------------- | ---------------------------------------- |
| GPT-5.5 Pro                 | 30.00 / 180.00  | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 94% cheaper                      |
| GPT-5.4 Pro                 | 30.00 / 180.00  | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 94% cheaper                      |
| GPT-5.2 Pro                 | 21.00 / 168.00  | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 93% cheaper                      |
| GPT-5 Pro                   | 15.00 / 120.00  | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 91% cheaper                      |
| o1-pro                      | 150.00 / 600.00 | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 98% cheaper                      |
| o3-pro                      | 20.00 / 80.00   | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 89% cheaper                      |
| o1                          | 15.00 / 60.00   | Nova 2 Pro (Preview) | 1.375 / 11.00 | Bedrock 85% cheaper                      |
| o3                          | 2.00 / 8.00     | DeepSeek-R1          | 1.35 / 5.40   | Bedrock 32% cheaper                      |
| o4-mini / o3-mini / o1-mini | 1.10 / 4.40     | GPT-5.6 Luna         | 0.22 / 1.32   | Bedrock 73% cheaper                      |
| GPT-5.2                     | 1.75 / 14.00    | Claude Sonnet 5      | 2.00 / 10.00  | Bedrock 20% cheaper                      |
| GPT-5.1 / GPT-5             | 1.25 / 10.00    | Claude Sonnet 5      | 2.00 / 10.00  | Source 11% cheaper                       |
| GPT-5 Mini                  | 0.25 / 2.00     | Nova Lite            | 0.06 / 0.24   | Bedrock 86% cheaper                      |
| GPT-5 Nano                  | 0.05 / 0.40     | Nova Micro           | 0.035 / 0.14  | Bedrock 58% cheaper                      |
| GPT-4.1                     | 2.00 / 8.00     | Claude Sonnet 5      | 2.00 / 10.00  | Source 14% cheaper                       |
| GPT-4.1 Mini                | 0.40 / 1.60     | Nova Lite            | 0.06 / 0.24   | Bedrock 85% cheaper                      |
| GPT-4.1 Nano                | 0.10 / 0.40     | Nova Micro           | 0.035 / 0.14  | Bedrock 65% cheaper                      |
| GPT-4o                      | 2.50 / 10.00    | Claude Sonnet 5      | 2.00 / 10.00  | Bedrock 7% cheaper                       |
| GPT-4o Mini                 | 0.15 / 0.60     | Nova Lite            | 0.06 / 0.24   | Bedrock 60% cheaper                      |
| GPT-4 Turbo                 | 10.00 / 30.00   | Claude Sonnet 5      | 2.00 / 10.00  | Bedrock 72% cheaper                      |
| GPT-4                       | 30.00 / 60.00   | Claude Sonnet 5      | 2.00 / 10.00  | Bedrock 88% cheaper                      |
| GPT-3.5 Turbo               | 0.50 / 1.50     | GPT-5.6 Luna         | 0.22 / 1.32   | Bedrock 30% cheaper + far better quality |

For the rows where the source is still cheaper (GPT-5.1/5, GPT-4.1), note that these models are on a
vendor deprecation path anyway; Option A (GPT-5.6 on Bedrock) is usually the better framing than defending a stale
model on price.

### Open-weight gpt-oss

`openai.gpt-oss-120b` (0.15 / 0.60) and `openai.gpt-oss-20b` (0.07 / 0.30) remain available and, unlike the
proprietary GPT models, **do** support `bedrock-runtime` / Converse. They sit a capability class below the GPT-5.x
frontier tier. Recommend them when the user wants OpenAI-architecture models on the Bedrock-native runtime surface
(for Guardrails, invocation logging, or Converse-based tooling) rather than through mantle.

---

## Migration Decision Framework

**Migrate to Bedrock, same model (Tier 0), if:** the source is GPT-5.6 / 5.5 / 5.4 and the target region carries it.
This is the common case and needs no cost justification.

**Migrate to Bedrock, model change (Tier 1/2), if:**

- The source model is not on Bedrock (see the region and catalog lists in `shared/openai-on-bedrock.md`)
- The user's priority is cost and they accept a model change — note that the cheapest option is often Nova, and that
  GPT-5.6 Luna already beats Claude Haiku 4.5 on price
- Bedrock-native features are required that mantle does not expose (Guardrails, Knowledge Bases, invocation logging,
  Converse-based tooling) — these need a Bedrock-native model or gpt-oss

**Consider staying on OpenAI's own API only if:**

- The target region is fixed and carries no suitable model, and a model change is unacceptable
- The workload needs the **Realtime API** — no Bedrock equivalent
- The workload uses **GPT-5.5's native audio/video (omnimodal) input** in ways the Bedrock deployment cannot
  serve — Claude on Bedrock is text+image only, and the mantle GPT path should be probed for the specific
  modality before committing
- The workload depends on **gpt-image**, **Whisper**, **TTS**, or **OpenAI embeddings** — these map to other AWS
  services (Stability AI, Transcribe, Polly, Titan Embeddings), not to an OpenAI model on Bedrock
- The workload uses **Assistants API with file search, vector stores, or code interpreter** — see the decision tree
  below
- Chat Completions cannot be reshaped to Responses and probing confirms Chat Completions is unsupported

**Cost belongs on that list, modestly.** Bedrock in-region runs ~10% above OpenAI's standard tier, so a
cost-only decision genuinely favours staying. Say so; then weigh it against commitments, governance, and residency
rather than dismissing it. For a long-context (>272K) workload the gap is much wider — the 1M tier is 2.0x input and
1.5x output — so profile the context distribution before concluding.

---

## Feature Migration

| OpenAI Feature                             | Bedrock Equivalent                                          | Notes                                                                            |
| ------------------------------------------ | ----------------------------------------------------------- | -------------------------------------------------------------------------------- |
| OpenAI SDK (direct)                        | Same model on Runtime OpenAI API                            | Preserve Responses or Chat shape when the model supports it; use `/openai/v1`    |
| Responses API                              | Runtime Responses API by default                            | Stored state works on Runtime; Mantle is for a verified selector                 |
| Chat Completions                           | Runtime Chat Completions by default                         | Preserve the source surface when the model/API table supports it                 |
| Function calling                           | Client-side tools on Runtime or Mantle                      | General server-side/preconfigured tools, including Web Search, can select Mantle |
| Reasoning effort                           | `reasoning={"effort": ...}` on mantle                       | `none` / `low` / `medium` / `high` / `xhigh` / `max`                             |
| Prompt caching                             | GPT-5.6 only (90% off cached input)                         | Not listed for GPT-5.5 / 5.4; Claude has its own caching                         |
| Streaming                                  | Supported                                                   | Verify per surface                                                               |
| Vision                                     | GPT-5.x (image input) or Claude / Llama 4                   | Same-model preserves behavior                                                    |
| JSON mode                                  | Claude (excellent), Nova Pro (good)                         | Most models via prompt                                                           |
| Embeddings (ada-002, `text-embedding-3-*`) | Titan Embeddings v2                                         | No OpenAI embedding model on Bedrock; must re-embed all documents                |
| DALL-E / gpt-image                         | Stability AI                                                | Nova Canvas v1 is Legacy; see `ai-model-lifecycle.md`                            |
| Whisper (STT)                              | Amazon Transcribe                                           | Different service, API, and pricing model                                        |
| TTS                                        | Amazon Polly / Nova 2 Sonic                                 | Different pricing model                                                          |
| Assistants API                             | See decision tree below                                     | Path depends on which features are used                                          |
| Realtime API                               | No equivalent                                               | Stay on OpenAI for this                                                          |
| Codex                                      | Not verified on Bedrock — see `shared/openai-on-bedrock.md` | Do not price; re-check the OpenAI model card index first                         |
| Guardrails / KB / invocation logging       | Bedrock-native model or gpt-oss                             | Not available through the mantle GPT path                                        |

---

## Common Migration Paths

### Same model on Bedrock Runtime (Tier 0) — default smallest change

For a model/API combination supported on Runtime, the application keeps the OpenAI SDK, its
Responses or Chat Completions call shape, and the same logical model. Changes are limited to:

1. Base URL → `https://bedrock-runtime.{region}.amazonaws.com/openai/v1`
2. Credentials → an auto-refreshing short-lived Bedrock token provider, **not** an OpenAI key
3. Model ID → the current model card's Runtime or CRIS inference-profile form
4. IAM → `bedrock:InvokeModel` and streaming action when needed, scoped to the selected target

Use the matching `runtime_openai_responses` or `runtime_openai_chat` path. Mantle keeps the
same source API shape but changes the host, bare model-ID form, and IAM action family; choose it
only for a verified selector. Always run the eval harness because endpoint configuration,
supported parameters, and model versions can still differ.

### Assistants API → migration decision tree

Assistants API and Responses API are different surfaces. Do not treat all Assistants usage as a config-only change.

**1. App already uses the OpenAI Responses API** (`responses.create`)
→ Cleanest path. Base URL + credential + model ID change.

**2. App uses Assistants API only for stateful multi-turn conversation** (no hosted tools, no file search, no code
interpreter, no persistent Assistant objects, no complex run lifecycle)
→ Mantle Responses is viable. Requires migrating `threads`/`runs` to `responses.create` — a small API migration
(days), not a redesign. Not a zero-code change.

**3. App uses Assistants API with simple hosted tools** (function calling only)
→ Mantle Responses with tool use is viable. Moderate migration (1–2 weeks) to adapt tool definitions and the run
lifecycle.

**4. App uses Assistants API with file search, vector stores, code interpreter, persistent Assistant objects, or
complex run lifecycle management**
→ Do not recommend mantle. Evaluate Bedrock AgentCore (Harness sessions/memory, action groups as MCP tools via
Gateway, gateway-fronted knowledge bases) for a full agentic replacement (2–4 weeks), or app-managed orchestration
if the team prefers to own state. Never target classic Bedrock Agents (`bedrock-agent`) — it is in maintenance mode
and closed to new customers as of July 30, 2026.

### When to prefer a Bedrock-native model over the mantle GPT path

Choose a Bedrock-native model or Runtime Converse/Invoke only when the workload requires a
feature unavailable through the selected OpenAI-compatible API. Runtime Responses/Chat support,
Guardrails, logging, caching, structured outputs, and inference-profile support are model- and
API-specific. Check the current model card for GPT-5.4, GPT-5.5, GPT-5.6, or any newer model;
do not infer capability from a family-wide rule. Keep Runtime OpenAI APIs as the default when
they satisfy the requirement, and use Mantle only for a verified selector.

### High-spend tiering

Tier by task complexity: simple (60%) → Nova Micro / GPT-5.6 Luna, moderate (30%) → Nova Pro / GPT-5.6 Terra,
complex (10%) → Claude Sonnet 5 / GPT-5.6 Sol. Mixing families across tiers is fine, but note that mantle and
`bedrock-runtime` are different surfaces — a tiered router spanning both needs two client paths.

---

## Volume-Based Recommendations

**Low (<1M tokens/day):** use the best model for quality. Cost difference is immaterial.

**Medium (1–10M tokens/day):** present the cost comparison. For Tier 0 the comparison is against the cross-family
alternative, not against the source provider.

**High (10–100M tokens/day):** consider tiering. Check the selected Runtime model's combined
token quota and any model-specific RPM quota. For Mantle, check separate input/output TPM,
then use token-aware admission, bounded concurrency and queues, and caching only where the
selected model/API documents it.

**Very high (>100M tokens/day):** tiering plus the same endpoint-specific controls. Honor
`Retry-After`, use exponential backoff with jitter under a finite retry budget, and reduce
load when capacity errors persist. Request quota increases early; approval is not automatic.

---

## OpenAI Pricing Tiers

OpenAI's own API offers Batch (50% off, 24hr), Flex (30–50% off, higher latency), Standard (baseline), and Priority
(2x, lowest latency). Source-side figures in this file use Standard. Bedrock exposes Standard / Priority / Flex /
Reserved service tiers, but per-model tier support renders as empty cells in the AWS docs — verify before
recommending Flex or Reserved as a cost lever.
