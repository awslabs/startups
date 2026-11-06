# Resolve Bedrock Model ID

Migration plans can contain stale or non-invocable model IDs. Resolve the exact ID for the
selected API path and Region without substituting a different model.

## Input

- `plan_model_id`: target model ID from the migration plan
- `migration_path`: exact selected API path
- `region`: AWS Region from orchestration context
- `profile`: optional AWS profile from orchestration context

## Procedure

### Step 0: Validate endpoint intent before interpreting the ID

The model ID alone does not select Runtime versus Mantle. Require one of these exact paths:

- Runtime: `runtime_openai_responses`, `runtime_openai_chat`, `runtime_messages`,
  `runtime_converse`, `runtime_invoke`
- Mantle: `mantle_openai_responses`, `mantle_openai_chat`, `mantle_messages`

Legacy absent/`converse` values normalize to `runtime_converse`; legacy `mantle` normalizes to
`mantle_openai_responses`. Any other non-empty path fails closed. Never treat a bare proprietary
GPT ID as proof that Mantle was selected, and never treat a CRIS-looking ID as permission to
change the selected API surface.

For `runtime_openai_responses` and `runtime_openai_chat`, GPT-5.4, GPT-5.5, and GPT-5.6 use the
exact Runtime CRIS ID returned for the target account and Region, such as an available `us.` or
`global.` form. For Mantle OpenAI paths, use the exact bare catalog ID. Chat Completions remains
Chat Completions when that exact path was selected; do not force a Responses reshape during ID
resolution.

### Step 1: List live Runtime inference profiles

For a Runtime path that requires an inference profile:

```bash
aws bedrock list-inference-profiles \
  --region <region> \
  <add --profile <profile> when supplied> \
  --query 'inferenceProfileSummaries[].[inferenceProfileId,inferenceProfileName]' \
  --output json
```

Parse each `[id, name]` pair. If `plan_model_id` is an exact ID in the result, return it.

For a Mantle path, validate the exact bare ID against the public model catalog exposed to the
target account and Region:

```bash
aws bedrock list-foundation-models \
  --region <region> \
  <add --profile <profile> when supplied> \
  --query "modelSummaries[?starts_with(modelId, 'openai.')].[modelId,modelName]" \
  --output json
```

Only an exact match succeeds. Resolution success does not prove invocation authorization;
preflight still probes the selected endpoint, API, Region, and model.

For plain Runtime foundation-model IDs, use the appropriate live catalog check, then let
preflight verify account invocability. Do not attach a regional prefix that the account query
did not return.

### Step 2: Rank candidates without auto-selecting

When there is no exact match, tokenize the plan ID and each live ID on `.`, `-`, `_`, and `/`.
Drop date/version tokens matching `^v?\d{6,}` or `^v\d+$`. Rank the top three by token
intersection, preferring `us.`, then `global.`, then no prefix, then other prefixes.

Ranking only supplies choices to orchestration. It never authorizes silently swapping a model,
tier, API, endpoint, or routing option.

### Step 3: Return a blocked result when exact resolution fails

Return:

```
The migration plan references Bedrock model '<plan_model_id>' on '<migration_path>', but that
exact model/API pair is not available in <region>. Closest matches found:
  - <candidate id> (<candidate name>)
The user may select a candidate, supply a different exact ID, change the API path in Design, or
abort.
```

Use `reason: model_unresolvable`. Include fewer candidates when fewer overlap. Include the exact
CLI error when listing fails; do not guess from documentation or another Region.

## Output contract

Only an exact target-account match returns an ID. Downstream preflight invokes that exact ID in
the selected Region through `migration_path`. Unknown paths, unsupported model/API pairs, and
unresolved IDs all fail closed. The helper is idempotent for an already validated pair.
