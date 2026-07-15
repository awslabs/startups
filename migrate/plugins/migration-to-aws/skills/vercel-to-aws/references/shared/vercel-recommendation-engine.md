# Vercel Recommendation Engine

This reference defines how to compute the three-outcome migration recommendation
from Discover + Coupling Score + Pre-Flight + Clarify signals. The agent evaluates
this decision cascade when `recommend-rules.md` loads this file.

**This is a PRECEDENCE CASCADE, not a scoring engine.** Unlike
`skills/shared/org-recommendation-engine.md` (which collects every matching
reason across all its conditions and resolves confidence from how many reasons
accumulated), this engine evaluates 4 rules IN A FIXED ORDER and STOPS at the
first rule that fires (Requirement 7.1). Do not flatten this to the org engine's
collect-all-reasons style — the algorithm shape is deliberately different because
the spec requires every recommendation to be traceable to exactly ONE fired rule,
not a weighted blend of several.

The output is a `recommendation` object containing an outcome, the rule that
fired, confidence, and plain-language reasons.

---

## Signal Sources

| Signal                               | Artifact                                                                                             | Key path                                                                                                                        |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Preview dependence                   | `clarify-answers.json`                                                                               | `Q4_preview_dependence.answer`                                                                                                  |
| Separable AWS-bound surface          | `discovery.json`                                                                                     | `peripherals[]` non-empty OR `api_routes[]` non-empty OR `backend_service_detected == true`                                     |
| Lambda-hostile workload              | `discovery.json` + `clarify-answers.json`                                                            | websockets/long-running-job signals in route analysis; `Q3_devops_bandwidth.answer` mentioning an existing separate API service |
| Traffic shape                        | `clarify-answers.json` (fallback) or `discovery.json.usage_metrics` with a log drain (authoritative) | `Q1_traffic_shape.answer`; `usage_metrics.peak_to_median_ratio` when log-drain-backed                                           |
| Coupling (ISR/edge)                  | `coupling-score.json`                                                                                | `items[]` entries for `isr`, `edge_middleware`, `edge_runtime_routes`                                                           |
| Team size / debuggability preference | `clarify-answers.json`                                                                               | `Q3_devops_bandwidth.answer`                                                                                                    |

**"High ISR/edge coupling" threshold (Step 3, row 1):** at least TWO of the
three items `isr`, `edge_middleware`, `edge_runtime_routes` are `detected: true`
in `coupling-score.json`. This is a simple count threshold, not a weighted
score — `coupling-weights.json` records detection methods and rationale per
item but does not define a numeric weight to sum, so "high coupling" for THIS
engine's purposes means "more than one of these three specific items is
present," not a broader Coupling Score total (which also includes items like
`vercel_managed_stores` that don't bear on the A-vs-B compute decision this
step is making).

**Rule 2 vs. Rule 3 overlap ("sustained heavy SSR"):** Step 2's "sustained
heavy SSR" condition and Step 3's "sustained traffic" condition can describe
the same underlying app shape. This is intentional, not a bug — Rule 2 is
evaluated FIRST and wins if it matches, so a genuinely Lambda-hostile SSR
workload never reaches Step 3 to be decided on traffic shape alone. "Heavy
SSR" for Rule 2's purposes is NOT separately detected in any Discover artifact
today (no fragment computes an SSR-weight/duration signal) — until such
detection exists, Rule 2's SSR clause is satisfied only by the Clarify-reported
signals it shares with the other named conditions (websockets, long-running
jobs >15 min, an existing separate API service); do not attempt to infer
"heavy SSR" from `route_disposition`'s `dynamic` count alone, as that would
conflate ordinary dynamic rendering with the sustained-heavy-load pattern Rule
2 actually targets.

---

## Decision Steps (evaluated top-to-bottom, first match wins)

### Step 1 — Preview Dependence + Separability (Rule 1)

Read `clarify-answers.json.Q4_preview_dependence.answer`.

| Condition                                                                                                                                                                                                                                                      | Result                                                                                                                                                                                                               |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Previews are load-bearing (the answer indicates the team relies on them for review/merge workflow) AND a separable AWS-bound surface exists (`discovery.json`'s `peripherals[]` non-empty, OR `api_routes[]` non-empty, OR `backend_service_detected == true`) | `outcome: "C"`, `fired_rule: 1`, `separable: true` — recurse into Steps 2-4 below (see the Step-1 Recursion note directly after this table) using ONLY the backend-relevant subset of signals to set `backend_shape` |
| Previews are load-bearing AND NO separable surface exists                                                                                                                                                                                                      | `outcome: "stay"`, `fired_rule: 1`, `separable: false` — a thin carve-out of whatever peripheral does exist may still be offered in the report, but the primary recommendation is to stay on Vercel                  |
| Previews are NOT load-bearing                                                                                                                                                                                                                                  | Fall through to Step 2                                                                                                                                                                                               |

**The Step-1 Recursion (critical — do not skip):** When Step 1 resolves to
Outcome C, re-evaluate Steps 2-4 below (yes, including Step 4 — the backend's
own traffic shape can be ambiguous even when the outer decision to recommend
Outcome C was not) using ONLY the backend-relevant subset of signals (route
analysis for websockets/long-running jobs, DB/queue peripherals, traffic shape
as it applies to the backend surface specifically) to determine `backend_shape`
as `"A-shaped"`, `"B-shaped"`, or (if the recursion itself reaches Step 4) an
unresolved backend tiebreak — see that step's own recursion note below for the
exact field shape. This recursion NEVER re-runs against the full Next.js app,
because under Outcome C the Next.js app itself never leaves Vercel (Requirement
7.2). A rule-2 "B-shaped" result means Fargate in Terraform for the backend; a
rule-3 "A-shaped" result means serverless backend compute (API Gateway +
Lambda) in Terraform — and CRITICALLY, this recursion NEVER emits a partial
OpenNext/SST scaffold. `backend_shape: "A-shaped"` describes serverless
COMPUTE SHAPE only, never SST/OpenNext tooling.

**Critical field-shape rule:** the recursion determines `backend_shape` (and,
if it reaches Step 4, `backend_tiebreak`/`backend_resolving_input` — see Step
4) ONLY. It NEVER changes the OUTER `outcome` (which stays `"C"`), the OUTER
`fired_rule` (which stays `1`, since Rule 1 is what actually fired at the top
level), or the OUTER `tiebreak` (which stays `false` unless Step 4 ALSO
independently fires for the outer decision — which cannot happen here, since
Step 1 already fired and stopped the outer cascade). A backend-level tiebreak
uses its OWN `backend_tiebreak`/`backend_resolving_input` fields, never the
outer `tiebreak`/`resolving_input` fields — mixing the two levels would make
`fired_rule == 4 iff tiebreak == true` (see Constraints) impossible to satisfy
when Rule 1 fired at the outer level but the backend recursion's Step 4 fired
internally.

---

### Step 2 — Lambda-Hostile Workload (Rule 2)

| Condition                                                                                                                       | Result                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Websockets present, long-running jobs (>15 min), sustained heavy SSR, OR an existing separate API service is detected/mentioned | `outcome: "B"`, `fired_rule: 2` (or, if reached via the Step-1 recursion, `backend_shape: "B-shaped"` — the outer `outcome` stays `"C"` in that case, only `backend_shape` is set here) |
| None of the above detected                                                                                                      | Fall through to Step 3                                                                                                                                                                  |

---

### Step 3 — Traffic Shape + Coupling (Rule 3)

Evaluate the two rows below IN ORDER — row order matters when a profile could
plausibly match both (e.g. a small team with high coupling that ALSO states an
explicit debuggability preference): the spiky/coupling/small-team row is
evaluated FIRST, and only if it does NOT match do you evaluate the
sustained/debuggability row. This means an explicit, stated debuggability
preference does NOT override a clear spiky+high-coupling+small-team signal —
a founder can prefer debuggability in the abstract and still be better served
by Outcome A if their actual traffic/coupling profile is a clean Outcome-A
fit; Q3's preference only becomes the deciding signal once row 1 doesn't
apply.

**Traffic-shape classification (closed rule, applies everywhere "spiky"/
"sustained" is used in this Step):** when a numeric peak:median ratio is
available (log-drain-backed, or a specific number in Q1's answer), classify
`< 3.0` as sustained and `>= 3.0` as spiky — a ratio of exactly 3.0 reads as
spiky, closing the boundary unambiguously. When no numeric ratio is available,
classify from Q1's descriptive language using ordinary judgment (e.g. "steady,"
"pretty flat" → sustained; "bursty," "occasional huge spikes" → spiky) — see
the Non-Binary Traffic Shape paragraph below for the case where even
descriptive judgment can't produce a spiky/sustained call.

| Condition                                                                                                                                                                                                                                                                                                                                                                      | Result                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Spiky traffic AND high ISR/edge coupling (per `coupling-score.json`) AND a small team (per Q3)                                                                                                                                                                                                                                                                                 | `outcome: "A"`, `fired_rule: 3` (or `backend_shape: "A-shaped"` if reached via the Step-1 recursion)                                                                                                                                                                                                                                                   |
| Sustained traffic OR the team states a debuggability preference (Q3)                                                                                                                                                                                                                                                                                                           | `outcome: "B"`, `fired_rule: 3` (or `backend_shape: "B-shaped"` if reached via the Step-1 recursion) — this row's `OR` means a stated debuggability preference alone is sufficient to match here even when traffic reads as spiky; see the Row Interaction note below for why this means a spiky-plus-debuggability profile never reaches the Residual |
| Neither row above matched, AND traffic-shape confidence is LOW (no log drain AND a vague/non-committal Q1 answer, OR Q1's answer is clear-sounding but genuinely non-binary — see Non-Binary Traffic Shape below)                                                                                                                                                              | Fall through to Step 4                                                                                                                                                                                                                                                                                                                                 |
| Neither row above matched, BUT traffic shape classifies cleanly as spiky or sustained per the rule above, AND the row it should have matched didn't (spiky classification without high coupling or without a small team; note that a clean SUSTAINED classification always satisfies row 2's `OR` and therefore can never reach this row — this row is spiky-only in practice) | Apply the **Step 3 Residual** below — do NOT fall through to Step 4, since Step 4 exists for LOW traffic-shape confidence, not for "a clean classification whose secondary condition didn't line up"                                                                                                                                                   |

**Row Interaction (spiky + stated debuggability preference):** rows are still
evaluated in order — row 1 first, row 2 only if row 1 doesn't match. Because
row 2 is an `OR`, if row 1's spiky+coupling+small-team condition is NOT
satisfied (e.g. team isn't small, or coupling is low) but the founder ALSO
stated an explicit debuggability preference in Q3, row 2 matches on the
debuggability clause alone → `outcome: "B"` at `high` confidence. This is a
genuine row-2 match, not a Residual case, and must never be mislabeled as
"residual defaulted to B." The Residual below is reached ONLY when BOTH rows
fail outright — including row 2's `OR` finding neither sustained traffic NOR a
stated debuggability preference. Concretely: a spiky profile with an EXPLICIT
debuggability preference always resolves via row 2's `high`-confidence match,
never via the Residual's `medium`-confidence default to A — the Residual only
ever fires for a spiky profile where debuggability was NOT stated at all.

**Non-Binary Traffic Shape:** if Q1's answer (or the log-drain data) is
specific and clear but genuinely does not classify as either spiky or
sustained under the rule above (e.g. "bimodal — flat most of the year, then a
4:1 spike for two weeks at tax season," or "depends entirely on the day, no
real pattern"), treat this the SAME as a LOW-confidence traffic-shape signal —
fall through to Step 4's tiebreak, do NOT invent a third Residual branch and do
NOT force a spiky/sustained pick. The signal is "clear" in the sense that the
founder gave a specific, non-vague answer, but it is not clear in the sense
Step 3's binary rows need — Step 4's framing ("present both paths, name the
resolving input") is the correct behavior for this case, not a failure to
apply Residual. Note in `reasons` that the traffic shape was non-binary/mixed,
distinct from Example 5's "vague/non-committal" tiebreak framing, so the
decision traceability appendix doesn't conflate "founder didn't know" with
"founder gave a specific but bimodal answer."

**Step 3 Residual (closes the "no legal outcome" gap):** when traffic shape
classifies CLEANLY as spiky or sustained (per the rule above — this
precondition rules out the non-binary case, which goes to Step 4 instead) but
the SECONDARY conditions (coupling level, team size, debuggability preference)
don't cleanly complete either row, decide using traffic shape ALONE as the
tie-break signal, at `medium` confidence (not `high`, since a secondary
condition was expected but didn't fully support the match, and NOT `low` —
see the Confidence Levels table's explicit carve-out for Residual): spiky
traffic without sufficient coupling/team-size support defaults to
`outcome: "A"`, `fired_rule: 3`. (As established in the Row Interaction note,
a clean sustained classification always satisfies row 2's `OR` outright and
therefore never reaches this Residual — there is no sustained-side Residual
case in practice; the Residual is spiky-only.) Record in `reasons` explicitly
which secondary condition was inconclusive (e.g. "coupling data was unreadable"
or "team size didn't clearly read as small") so the decision traceability
appendix can show this was a residual default, not a clean row-1 match.

---

### Step 4 — Tiebreak (Rule 4)

| Condition                                                                                                                                                                                                                                                       | Result                                                                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Traffic-shape confidence is LOW (no log drain AND a vague/non-committal Q1 answer), OR the traffic-shape signal is specific/clear but genuinely non-binary (see Step 3's Non-Binary Traffic Shape note) — i.e. Step 3's row 3 was reached, not its Residual row | `outcome: ["A", "B"]`, `fired_rule: 4`, `tiebreak: true`, `resolving_input: "14 days of log drain data"` — present BOTH outcomes side by side in the report rather than forcing a pick |

**If this rule is reached via the Step-1 recursion** (i.e. the backend's own
traffic shape specifically is LOW confidence): this is a BACKEND-LEVEL
tiebreak, not an outer one. Set `backend_shape: ["A-shaped", "B-shaped"]`,
`backend_tiebreak: true`, and `backend_resolving_input: "14 days of log drain
data (scoped to the separable backend's traffic)"`. The OUTER `outcome`
remains `"C"`, the OUTER `fired_rule` remains `1` (Rule 1 is what fired at the
top level — see the Step-1 Recursion's field-shape rule above), and the OUTER
`tiebreak` stays `false` — there is no "outer tiebreak" in this case, only a
backend-scoped one. This is why `backend_tiebreak`/`backend_resolving_input`
are DISTINCT fields from `tiebreak`/`resolving_input`, never the same fields
reused at a different level — reusing them would make the Constraints section's
`fired_rule == 4 iff tiebreak == true` rule impossible to satisfy whenever Rule
1 fires outer and Step 4 fires inner.

---

## Conflicted Profiles (Requirement 7.3)

A conflicted profile — e.g. heavy ISR coupling + sustained traffic + load-bearing
previews — is resolved DETERMINISTICALLY by the rule order: Rule 1 fires first
(previews are load-bearing), so the outcome is `"C"` (assuming separability),
regardless of what Rule 3 would have said about the ISR/traffic-shape
combination. When this happens, the report MUST state explicitly that this is a
conflicted profile resolved by precedence, not a judgment call — cite which
rule fired and which rule(s) would have applied to the SAME signals had an
earlier rule not already resolved the outcome. This is exactly what the decision
traceability appendix (Requirement 10) renders.

---

## EKS and Amplify — Never Engine Outputs (Requirement 7.4-7.5)

`outcome` and `backend_shape` are a closed vocabulary: `{"A", "B", "C", "stay"}`
(or a 2-element array of `{"A","B"}` for a tiebreak) for `outcome`, and
`{"A-shaped", "B-shaped", null}` for `backend_shape`. **EKS and Amplify are NEVER
valid values for either field.** They are report-prose callouts computed
separately from this engine:

- **EKS**: never recommended unless the team already operates Kubernetes
  elsewhere (a fact, if true, surfaced via Q3's answer — but even then, EKS is
  NOT an `outcome` value; if the team runs K8s elsewhere, note this in the
  report as a "you may prefer to route through your existing EKS operations"
  aside, without changing `recommendation.outcome`). Note the existence of
  funded Vercel-to-EKS marketplace offerings as the anti-pattern this
  assessment differentiates against, while separately noting AWS migration
  funding programs are a legitimate line item regardless of target.
- **Amplify**: not a default path. Cite the rationale in the report (shared CDN
  owned by the Amplify team, resources outside the founder's account,
  closed-source — sourced from the OpenNext team's own assessment, flagged for
  periodic re-check since Amplify is in the working group) without ever setting
  `recommendation.outcome` to anything Amplify-related.

---

## Output Schema (`recommendation.json`)

```json
{
  "outcome": "A" | "B" | "C" | "stay" | ["A", "B"],
  "fired_rule": 1 | 2 | 3 | 4,
  "tiebreak": false,
  "separable": true,
  "backend_shape": "A-shaped" | "B-shaped" | ["A-shaped", "B-shaped"] | null,
  "backend_tiebreak": false,
  "backend_resolving_input": null,
  "confidence": "high" | "medium" | "low",
  "reasons": [
    "Plain-language explanation string 1",
    "Plain-language explanation string 2"
  ],
  "resolving_input": null
}
```

### Constraints

- `outcome` is a 2-element array `["A","B"]` **only if** `tiebreak == true`;
  otherwise it is a single string from `{"A", "B", "C", "stay"}`.
- `backend_shape` is non-null **only if** `outcome == "C"`.
- `separable` is present **only if** `outcome` is `"C"` or `"stay"`.
- `fired_rule` names EXACTLY the rule that fired at the OUTER (top-level)
  decision — this is ALWAYS `1` when `outcome == "C"` or `outcome == "stay"`,
  since only Rule 1 produces those two outcomes. `fired_rule == 4` **if and
  only if** `tiebreak == true` (the OUTER tiebreak field — see next bullet).
  `backend_tiebreak` firing during the Step-1 recursion does NOT change
  `fired_rule`; it is tracked entirely separately (see `backend_tiebreak`
  below), specifically so this constraint never has to account for a
  recursion-internal tiebreak.
- `tiebreak` refers to the OUTER decision ONLY (Step 4 firing at the top level,
  which can only happen when `outcome` is the 2-element `["A","B"]` array —
  i.e. `outcome` is never `"C"` when `tiebreak == true`, since Rule 1 already
  resolved to `"C"` before Step 4 could run at the outer level).
  `resolving_input` is non-null **only if** `tiebreak == true`.
- `backend_tiebreak` is present and meaningful **only if** `outcome == "C"` —
  it is `true` when the Step-1 recursion's OWN Step 4 fired while determining
  `backend_shape` (the backend's traffic shape was itself LOW confidence).
  When `backend_tiebreak == true`, `backend_shape` is the 2-element array
  `["A-shaped", "B-shaped"]` and `backend_resolving_input` is non-null (mirrors
  `tiebreak`/`resolving_input`'s relationship, but scoped one level down — see
  the Step-1 Recursion's field-shape rule). `backend_tiebreak` and `tiebreak`
  are never both `true` in the same recommendation, since reaching the Step-1
  recursion at all means Rule 1 already fired outer, which precludes the outer
  Step 4 from ever running.
- `reasons` MUST contain at least one entry, naming the specific signals that
  drove the decision (cite the actual Clarify answer, the actual Coupling Score
  item, the actual traffic-shape data — never a generic placeholder).
- `outcome` and `backend_shape` are NEVER `"EKS"` or `"Amplify"` — see the
  section above.

### Confidence Levels

| Level    | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | When it applies                                                                                                                                                                                                           |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `high`   | Rule 1, 2, or 3 fired on a clear, unambiguous signal (e.g. websockets definitively present; Q4's answer unambiguously load-bearing; Step 3's row 1 or row 2 matched cleanly on both its primary and secondary conditions)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Most single-signal-driven outcomes                                                                                                                                                                                        |
| `medium` | The firing rule's signal was present but not unambiguous (e.g. Q3's debuggability preference was implied rather than stated outright), OR the **Step 3 Residual** fired (traffic shape itself was clean, only a secondary condition was inconclusive — this is EXPLICITLY `medium`, never `low`, since the Residual is not a fallback-default guess, it is a deliberate decision rule using a confirmed signal)                                                                                                                                                                                                                                                                                                                                                                     | Partial signal support; Step 3 Residual (always `medium`, by definition — never reclassify a Residual firing as `low`)                                                                                                    |
| `low`    | Rule 4 (the outer OR backend-scoped tiebreak) fired, OR a rule fired using a TRUE fallback default because a required signal was missing/unreadable entirely (e.g. `discovery.json.peripherals` unreadable → conservative `"stay"` fallback under Step 1; Q1's traffic-shape answer was vague/absent AND no log drain existed, forcing Step 4). Do NOT cite `coupling-score.json` unreadable as a `low` example — per the Fallback Behavior table, that scenario still checks row 2 (which can match at `high` on a stated debuggability preference) before falling to the Step 3 Residual at `medium`; it only reaches `low` in the further sub-case where traffic-shape confidence is ALSO independently LOW, which is really the row above firing, not the coupling read itself. | Vague/absent answers, missing log drain, missing/unreadable artifacts that block a rule's own condition outright — NOT the Step 3 Residual, which has its own confirmed (if incomplete) signal set and is always `medium` |

---

## Fallback Behavior (Never Block on Missing Signals)

Same principle as `org-recommendation-engine.md`: never fail or block Recommend
due to missing signals. Always produce a valid recommendation object.

| Scenario                                                                                                                               | Behavior                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Q4_preview_dependence` unanswered or declined                                                                                         | Treat as "not load-bearing," fall through to Step 2. Note in `reasons`: "preview dependence unanswered — assumed not load-bearing by default."                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| No log drain AND a vague Q1 answer                                                                                                     | Confidence `low`, proceed to Step 4's tiebreak rather than guessing between A and B.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Q1's answer (or log-drain data) is specific/clear but genuinely non-binary (e.g. bimodal, "depends on the day," no consistent pattern) | Same destination as the row above (Step 4's tiebreak, confidence `low`) but for a DIFFERENT reason — see Step 3's Non-Binary Traffic Shape note. Do not conflate this with the Step 3 Residual, which requires a CLEAN spiky/sustained classification and is always `medium`.                                                                                                                                                                                                                                                                                                                                    |
| `discovery.json.peripherals` unreadable/missing (key absent from the JSON entirely, distinct from a present-but-empty array)           | Treat separability as `false` — fail toward the MORE CONSERVATIVE `"stay"` outcome, never toward silently assuming a separable surface exists when it cannot be confirmed.                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `discovery.json.api_routes` is a present, empty array (`[]`)                                                                           | This is a CONFIRMED fact, not a missing signal — Discover genuinely found zero API routes. Treat identically to `peripherals` being empty: this alone does not satisfy separability, but does NOT trigger the "unreadable/missing" fallback above (that fallback is for when the KEY itself is absent, meaning Discover could not determine the fact at all).                                                                                                                                                                                                                                                    |
| `coupling-score.json` unreadable                                                                                                       | Treat coupling as "unknown," which removes it as a Step 3 discriminator — row 1 cannot match without a confirmed coupling read. Row 2 can still match cleanly (at `high` confidence) if the team stated a debuggability preference, regardless of the coupling read — check row 2 BEFORE falling to the Residual. Only when row 2 also doesn't match (no debuggability preference stated, and traffic doesn't classify as sustained) does this fall to the Step 3 Residual (confidence `medium`, coupling named as the inconclusive secondary condition) or, if traffic-shape confidence is ALSO LOW, to Step 4. |

---

## Mapping to `backend_shape`'s Scaffold Consumption

`scaffold-opennext.md` / `scaffold-fargate.md` read `recommendation.json`
directly:

| `outcome`                             | `backend_shape`                                       | Scaffold behavior                                                                                                                                                                                                                                       |
| ------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `"A"`                                 | `null`                                                | Full Next.js app surface via SST/OpenNext + Terraform peripherals                                                                                                                                                                                       |
| `"B"`                                 | `null`                                                | Full Next.js app surface via Terraform-only Fargate                                                                                                                                                                                                     |
| `"C"`                                 | `"A-shaped"`                                          | NO Next.js scaffold; Terraform-only serverless backend (API Gateway + Lambda)                                                                                                                                                                           |
| `"C"`                                 | `"B-shaped"`                                          | NO Next.js scaffold; Terraform-only Fargate backend                                                                                                                                                                                                     |
| `"C"`                                 | `["A-shaped", "B-shaped"]` (`backend_tiebreak: true`) | Backend-level tiebreak unresolved — Scaffold cannot emit both; ask the founder to pick `A-shaped` or `B-shaped` before proceeding, or if declined, run `scaffold-peripherals.md` only (see `scaffold.md` Step 1's own trigger table for this exact row) |
| `["A", "B"]` (outer `tiebreak: true`) | n/a                                                   | Outer tiebreak unresolved — same treatment: ask the founder to pick `A` or `B` before proceeding, or if declined, no compute fragment fires                                                                                                             |
| `"stay"`                              | n/a                                                   | No scaffold offered (or a thin peripheral-only carve-out, per the report's honesty paragraph)                                                                                                                                                           |

---

## Worked Examples

### Example 1: Load-bearing previews, separable backend

**Signals:** Q4 answer = "we review every PR live before merge, can't lose
this"; `discovery.json.api_routes` = `["/api/orders", "/api/webhooks"]`
(non-empty).

**Evaluation:** Step 1 — previews load-bearing AND separable surface exists →
`outcome: "C"`, `fired_rule: 1`, `separable: true`. Recurse: backend signals show
no websockets/long-running jobs (Step 2 no match), traffic sustained (Step 3
matches Outcome B) → `backend_shape: "B-shaped"`.

**Result:** `{outcome: "C", fired_rule: 1, separable: true, backend_shape:
"B-shaped", confidence: "high", reasons: ["PR previews are load-bearing for the
team's review workflow", "A separable API surface exists (/api/orders,
/api/webhooks)", "Backend traffic is sustained, favoring Fargate for the
peeled-off backend"]}`

### Example 2: Load-bearing previews, no separable surface

**Signals:** Q4 answer = "yes very important"; `discovery.json.peripherals` =
`[]`, `api_routes` = `[]`, `backend_service_detected: false`.

**Evaluation:** Step 1 — previews load-bearing AND NOT separable →
`outcome: "stay"`, `fired_rule: 1`, `separable: false`.

**Result:** `{outcome: "stay", fired_rule: 1, separable: false, confidence:
"high", reasons: ["PR previews are load-bearing", "No separable AWS-bound
surface was found - this is a monolith Next.js app with nothing meaningful to
peel off"]}`

### Example 3: Websockets present

**Signals:** Q4 = "we barely use previews"; Discover's route analysis flags a
websocket route.

**Evaluation:** Step 1 — not load-bearing, fall through. Step 2 — websockets
detected → `outcome: "B"`, `fired_rule: 2`.

**Result:** `{outcome: "B", fired_rule: 2, confidence: "high", reasons: ["A
websocket route was detected, which Lambda cannot support"]}`

### Example 4: Spiky traffic, high coupling, small team

**Signals:** Q4 = "rarely use previews"; no websockets; Q1 = "very spiky, maybe
10:1 peak to median"; coupling-score.json shows ISR + edge middleware both
present; Q3 = "just me and one other engineer."

**Evaluation:** Step 1 no match, Step 2 no match, Step 3 — spiky traffic and
high coupling and a small team → `outcome: "A"`, `fired_rule: 3`.

**Result:** `{outcome: "A", fired_rule: 3, confidence: "high", reasons: ["Spiky
traffic (~10:1 peak:median)", "High ISR and edge-middleware coupling", "Small
team (2 engineers) favors minimal operational overhead"]}`

### Example 5: Tiebreak

**Signals:** Q4 = "not really"; no websockets; Q1 = "hard to say, kind of
varies"; no log drain supplied.

**Evaluation:** Step 1 no match, Step 2 no match, Step 3 — traffic-shape
confidence LOW (no log drain, vague Q1) → fall through. Step 4 — tiebreak fires.

**Result:** `{outcome: ["A", "B"], fired_rule: 4, tiebreak: true, confidence:
"low", reasons: ["Traffic shape answer was vague and no log drain was
supplied - presenting both paths rather than guessing"], resolving_input: "14
days of log drain data"}`

### Example 6: Load-bearing previews, separable backend, backend traffic ambiguous (backend-level tiebreak)

**Signals:** Q4 = "we review every PR live before merge"; `api_routes` =
`["/api/reports"]` (non-empty, separable); no websockets/long-running jobs on
the backend; Q1 (asked with the backend surface specifically in mind during
the recursion) = "honestly not sure how that one endpoint gets hit, we don't
have great visibility into it"; no log drain.

**Evaluation:** Step 1 (outer) — previews load-bearing AND separable → outer
`outcome: "C"`, outer `fired_rule: 1`, `separable: true`. Recurse: Step 2 no
match (no websockets/long-running jobs on the backend), Step 3 no match
(backend traffic shape itself is too vague to read as clearly spiky OR
sustained, and coupling doesn't apply to a bare API route) → recursion reaches
its own Step 4 — backend traffic-shape confidence is LOW → backend-level
tiebreak fires.

**Result:** `{outcome: "C", fired_rule: 1, separable: true, backend_shape:
["A-shaped", "B-shaped"], backend_tiebreak: true, backend_resolving_input: "14
days of log drain data (scoped to the separable backend's traffic)",
tiebreak: false, resolving_input: null, confidence: "low", reasons: ["PR
previews are load-bearing for the team's review workflow", "A separable API
surface exists (/api/reports)", "The backend's own traffic shape is too
uncertain to pick between a serverless or container backend without more
data - presenting both shapes rather than guessing"]}`

Note: the OUTER `fired_rule` stays `1` and the OUTER `tiebreak` stays `false`
even though a tiebreak genuinely occurred — it occurred one level down, inside
the backend-shape recursion, and is recorded entirely in the
`backend_tiebreak`/`backend_shape`/`backend_resolving_input` fields instead.
