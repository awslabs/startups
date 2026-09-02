# Support-bot fixture — migration requirements

Existing OpenAI customer-support bot.

- `src/support_bot/agent.py`: classifies tickets with GPT-4o (Chat Completions) and
  deep-reasons with GPT-5.4 (Responses API).
- `src/support_bot/extras.py`: audio transcription (whisper-1), embeddings
  (text-embedding-3-large), hosted file search (gpt-5.4 + file_search).
- Sessions last 10-20 minutes; traffic is bursty.
- Low operational overhead preferred; no Kubernetes requirement.

## Requirements (authoritative)

- **API continuity: required** — preserve the OpenAI SDK and API surface.
- **Priority: balanced** (cost vs capability).
- **Governance: none** — no Bedrock Guardrails, invocation logging, or
  multi-model Converse requirement.
- **Target region: us-east-2.**
- No AWS account yet; live verification = not_run.
