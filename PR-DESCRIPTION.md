## Description

### Problem

The `ai-model-lifecycle.md` table was last refreshed May 26, 2026 — 19 days stale. During that window:

- **2 models passed EOL** (Claude Opus 4, Claude 3.5 Haiku) but were still listed, creating confusion
- **Claude 3.5 Sonnet v2 and Command R/R+** crossed the 90-day exclusion boundary but were still marked `legacy`, meaning the agent could recommend them as migration targets despite being too close to EOL for a production migration
- **Claude Sonnet 4** entered Legacy (EOL Oct 14) with no tracking — users migrating to it would not see the sunset warning
- **No Active image-gen model existed** in the lifecycle data. The only tracked image model (Nova Canvas) is Legacy, yet the replacement column said "—". An agent following lifecycle rules would correctly refuse to recommend Nova Canvas but have nothing to offer instead — while Stability AI models (Active, no EOL) are available on Bedrock

The `pricing-cache.md` had matching gaps: Jamba 1.5 models still marked `active` (went Legacy May 26), no Stability AI pricing section, and a stale refresh date triggering the 30-day staleness warning.

### Changes

**ai-model-lifecycle.md:**

- Remove past-EOL rows (Claude Opus 4, Claude 3.5 Haiku)
- Reclassify Claude 3.5 Sonnet v2 (`legacy` → `excluded`, 46 days) and Command R/R+ (`legacy` → `excluded`, 66 days)
- Add 7 newly-tracked models: Claude 3 Sonnet, Claude 3.5 Sonnet v1, Claude Sonnet 4, Claude 3 Haiku, Jamba 1.5 Large/Mini, Nova Reel v1:1
- Add Stability AI image generation guidance block with model table, tiered recommendations, and per-image pricing note
- Update Titan Image Gen v2 and Nova Canvas replacement columns to `Stability AI (see note)`

**pricing-cache.md:**

- Add Claude Sonnet 4 row (`legacy, EOL Oct 14, 2026`)
- Fix Jamba 1.5 Large/Mini: `active` → `legacy (EOL Nov 26, 2026)`, add model IDs
- Add Stability AI image generation pricing section with cost comparison note vs DALL-E/Imagen
- Update `Last updated` to 2026-06-14

### Testing

- All EOL dates verified against [Bedrock model lifecycle page](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html) (Jun 14, 2026)
- Days-to-EOL recomputed from today's date
- No behavioral logic changes — data table and reference updates only

### Known follow-up (separate PR)

Five phase-specific files (`design-ai.md`, `discover-preview.md`, `ai-openai-to-bedrock.md`, `ai-gemini-to-bedrock.md`, `clarify-ai.md`) still default `image_generation` → Nova Canvas. This PR establishes the authoritative lifecycle rule; the follow-up propagates it into design-time defaults and adds an image-gen costing path in `estimate-ai.md`.

## Type of Change

- [ ] New plugin/power/tool
- [ ] Bug fix
- [x] Enhancement to existing content
- [ ] Documentation update
- [ ] Guardrail/CI update

## Team Folder

- [x] `migrate/`
- [ ] Other: ___

## Checklist

- [x] I have read the [CONTRIBUTING.md](../CONTRIBUTING.md) guidelines
- [x] My changes do not include hardcoded secrets, credentials, or internal-only content
- [ ] I have run `mise run build` locally and it passes
- [x] I have updated documentation if needed
- [x] My changes are scoped to my team's folder only
