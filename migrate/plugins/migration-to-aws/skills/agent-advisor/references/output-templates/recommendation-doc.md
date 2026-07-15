<!-- recommendation-doc.md — fill all sections; business summary first, technical detail after -->

# AWS Agent Architecture Recommendation

## 1. Executive summary

<2–3 plain-language sentences: recommended runtime + why, for a non-technical reader.>

## 2. Your profile

`<bulleted summary of the answers that drove the decision.>`

## 3. Recommendation: `<Runtime>` <+ deployment model if AgentCore>

<rationale + the top scoring signals; business framing then technical specifics.>

## 4. Architecture diagram

<INSERT the Mermaid block + ASCII fallback produced by the Generate diagram step (Plan 3).>

## 5. Alternatives considered

<eliminated/lower-scored runtimes and why.>

## 6. Comparison

`<relevant rows from the runtime service cards.>`

## 7. Six dimensions

<Identity, Observability, Guardrails, Scaling, Tool/Gateway, Protocols — from the service card.>

## 8. AgentCore services to enable

<final service list from confirm.json, with why each; note which are free.>

## 9. Bedrock model

<model default + reasoning; for migrate, coarse family mapping + "see migration-to-aws for pricing".>

## 10. Cost magnitude

<Build paths (estimate.json exists): the band + assumptions + "order-of-magnitude" disclaimer.
Migrate (no estimate.json — Estimate is skipped): write "Detailed cost and TCO are produced by
the migration plugins" plus an optional one-line directional note. Do NOT invent a dollar band.>

## 11. Next steps

<scaffolding pointers; handoff pointers if applicable. For AgentCore Build paths, point to the
deployment plan at `plan.md` (the staged idea → **plan** → deploy steps) and the generated POC at
`poc/` — agent code + deploy.sh + README — and note the user runs `./deploy.sh` themselves (it
creates real, billable AWS resources).>

## 12. Freshness footer

<from freshness.md template: date, MCP-verified vs cached fields, verify disclaimer.>
