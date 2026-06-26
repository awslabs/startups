# Migration web experience: data-first intake + adaptive questioning + iterative refinement

## Problem

The web flow asks 14 questions before requesting the user's GCP bill, IaC, or app code. This is a drop-off risk, and several of those questions ask for things we could infer from the data itself — so we effectively ask twice. Generation is also one-shot (questions → upload → chat box → full plan), which doesn't fit the iterative, refine-as-you-go nature of real migrations.

## Change

Reorder to data-first and minimize questions:

1. Ask for data first — IaC, GCP bill, app code, Kubernetes manifests (at least one required).
2. Auto-detect services/resources and infer answers from that data.
3. Show detected services + inferred settings (with sources); let the user confirm or correct.
4. Ask only the questions we couldn't infer; offer a fast path for simple stacks.
5. Replace one-shot generation with a resumable flow where users refine inputs and regenerate affected artifacts.

## Reference: `migration-to-aws` plugin (`gcp-to-aws` skill) already does this

- Discover phase scans Terraform/app code/billing before any questions.
- "Extract known information" pulls region, DB HA/size, traffic tier, spend band, AI model/modalities from the data.
- A mandatory "Confirm Detected Settings" gate shows detected values + sources and blocks until confirmed/corrected.
- Adaptive firing + early-exit rules skip already-known questions; fast-path (3 Qs) and simple-hybrid (~6 Qs) modes replace the full ~22.
- Progressive batches with saves make it resumable; phased state machine (discover → clarify → design → estimate → generate) is the seam for iterative refinement.

## Workstreams (for task breakdown)

1. Data-first intake UI
2. Detection/inference service
3. Confirm-detected-services step
4. Adaptive questionnaire + fast path
5. Iterative refinement / phased state model

## Done when

- Data is requested before questions; ≥1 source required.
- Anything inferable from data is auto-filled, not asked.
- User confirms/corrects detected services before continuing.
- Only un-inferred questions are shown; count drops for data-rich stacks.
- Plans can be refined and regenerated without starting over.
