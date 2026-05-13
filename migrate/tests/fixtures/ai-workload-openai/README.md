# Fixture: ai-workload-openai

Tests AI workload detection and model mapping for OpenAI SDK usage hosted on GCP.

## Resources

| Type                                      | Classification | Purpose                  |
| ----------------------------------------- | -------------- | ------------------------ |
| `google_cloud_run_v2_service.chatbot`     | PRIMARY        | Hosts the AI chatbot app |
| `google_secret_manager_secret.openai_key` | SECONDARY      | OpenAI API key           |
| `google_service_account.chatbot_sa`       | SECONDARY      | Service account          |

## App code

- `src/chatbot.py` — Uses `openai` SDK (GPT-4o + text-embedding-3-small)
- `requirements.txt` — Lists `openai>=1.30.0`

## Key invariants tested

- AI detection fires (ai-workload-profile.json created)
- `summary.ai_source` is "openai"
- Category F questions enabled in Clarify
- Design maps OpenAI models to Bedrock equivalents
- No Legacy or Excluded AI models recommended as primary
