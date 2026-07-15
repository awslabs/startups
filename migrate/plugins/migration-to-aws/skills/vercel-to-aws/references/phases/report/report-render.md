---
_fragment: render
_of_phase: report
_contributes:
  - assessment-report.html (all sections)
---

# Report Phase: Render

> Self-contained fragment. Renders the full `assessment-report.html` document
> from every upstream artifact. Applies the outcome-based Pre-Flight Check
> filter/reframe, the reader-vocabulary rule, and the cost-labeling rule as
> AUTHORING discipline — `report-assemble.md`'s validator invocation is what
> actually enforces these, but getting them right here means the report passes
> on the first attempt rather than burning retries.

**Execute ALL steps in order. Do not skip or optimize.**

---

## Required Sections (per `scripts/validate-assessment-report.py`'s

`REQUIRED_SECTION_IDS`)

Render exactly these section IDs, always:

| Section ID              | Content                                                                                                                                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `exec-verdict`          | The recommendation, in plain language, with a `class="verdict"` element or a "Recommendation:" sentence                                                                         |
| `what-you-gain`         | Cost mechanics (owning the CDN means caching aggressively enough to serve FEWER origin requests, not just cheaper ones), bill predictability, AWS credits/funding applicability |
| `what-you-lose`         | Preview deployments FIRST, then skew protection, then the declining-over-time newest-feature-lag risk                                                                           |
| `coupling-score`        | Per-feature detail from `coupling-score.json`, at least 3 table rows                                                                                                            |
| `preflight-findings`    | Pre-Flight Check findings, FILTERED AND REFRAMED by the recommended outcome (see below)                                                                                         |
| `decision-traceability` | Which precedence rule fired and why (see below)                                                                                                                                 |
| `next-steps`            | An `<ol>` — never a `<ul>` or plain paragraphs                                                                                                                                  |

---

## Conditional Sections

Render these ONLY when their trigger holds — check
`recommendation.json`/`preflight-findings.json`/`tier1-signals.json` before
deciding:

| Section ID        | Trigger                                                                                                                                    |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `exec-tiebreak`   | `recommendation.tiebreak == true` — the Outcome A/B side-by-side                                                                           |
| `inputs-received` | any finding across `discovery.json`/`coupling-score.json`/`preflight-findings.json` has `confidence != "HIGH"` — confidence-upgrade offers |
| `appendix-m1`     | `tier1-signals.json.has_middleware == true`                                                                                                |
| `out-of-scope`    | `recommendation.outcome` is `"C"` or `"stay"` — the separability rationale                                                                 |

---

## Step 1: Render `exec-verdict`

State the recommendation in plain language. If `recommendation.tiebreak ==
true`, render `exec-tiebreak` alongside it presenting BOTH outcomes side by
side, naming the resolving input (`recommendation.resolving_input`) rather than
forcing a pick.

**Reader-vocabulary rule applies here (Requirement 9.7):** NEVER write "M1
fired at HIGH" — write "your middleware skips on cached pages." Never cite a
Pre-Flight Check ID, an artifact filename, a Terraform resource ID, or the term
"route disposition" in this section.

---

## Step 2: Render `what-you-gain` and `what-you-lose`

**AWS credits/funding applicability (part of `what-you-gain`'s required
content — do not omit):** read `clarify-answers.json.Q2_migration_trigger.answer`.
If it mentions running out of credits, hitting a spend/budget wall, or funding
pressure generally (judgment call — the founder's own words, not a fixed
keyword list), surface AWS Activate eligibility as part of this section:

> "AWS Activate offers eligible early-stage startups credits (Founders tier:
> up to $5,000 self-service; Portfolio tier: up to $200,000 for VC/accelerator-
> backed companies) that apply directly to the AWS services this migration
> would use. Worth checking eligibility at
> [aws.amazon.com/startups/credits](https://aws.amazon.com/startups/credits)
> before finalizing a budget."

If Q2's answer does NOT mention credits/funding pressure, still include a
one-sentence, low-key version rather than omitting the topic entirely (per the
Required Sections table, "AWS credits/funding applicability" is required
content, not conditional on Q2's wording) — e.g. "Separately, AWS Activate
credits may apply to this migration's AWS costs if you haven't already
checked eligibility." Never overstate eligibility (this skill does not verify
funding stage, prior credit usage, or Activate Provider Org ID — say
"eligible startups" and "worth checking," never "you qualify").

**Dollar figures here are credit ceilings, not cost/savings estimates —
label them accordingly, not with "estimated monthly":** the validator's
cost-labeling rule (Requirement 9.6) exempts a dollar figure specifically when
"Activate" or "credit(s)" appears nearby, since a one-time credit ceiling
being forced into "estimated monthly cost" phrasing would misdescribe it. Do
NOT write "an estimated monthly cost of $5,000" for a credit figure — that
is actively wrong, not just unlabeled. Keep the natural "up to $5,000 in AWS
Activate credits" phrasing instead.

`what-you-lose` MUST lead with preview deployments (Requirement 9.1's ordering)
— this is the single heaviest thing most founders lose, and burying it
undermines the "honest by construction" philosophy.

Same reader-vocabulary rule applies — plain language only in these
executive-flow sections.

---

## Step 3: Render `coupling-score`

Render `coupling-score.json`'s `items[]` as a table: feature, detected, weight
rationale. If `phased_migration_candidate` is flagged, render it as a
phased-migration note (Requirement 5.3) rather than a blanket stay-on-Vercel
framing.

This is an APPENDIX-equivalent section — internal identifiers (feature IDs like
`isr`, `edge_middleware`) are acceptable here since it's not in
`EXEC_SECTION_IDS`.

---

## Step 4: Render `preflight-findings` — Outcome-Filtered (Requirement 6.3-6.4)

Read `recommendation.json.outcome` (and `backend_shape` if `outcome == "C"`).
For EACH of the 10 checks in `preflight-findings.json`:

1. Check whether the recommended outcome is in the check's `applies_to` set.
   If NOT, do not surface it in the primary findings — this check was
   COMPUTED (per Discover's unconditional computation) but is not relevant to
   this founder's recommended path.
2. If it IS applicable, render it using the outcome-appropriate wording. For
   I1 specifically, use `severity_rule_by_outcome`'s A-branch wording if
   `outcome == "A"`, the B-branch wording if `outcome == "B"`.
3. M1 ALWAYS renders regardless of outcome (per its `adapter_generation:
   "independent"` tag and Requirement 6.5) — it applies to every AWS target.

**Requirement 6.4 — override support:** note in the rendered HTML (a data
attribute or comment, not visible prose) that the FULL, unfiltered
`preflight-findings.json` remains on disk — if the founder later overrides the
recommended outcome, a re-render can surface the previously-suppressed
findings without re-running Discover. Do not literally re-run anything here;
just don't destroy the source data.

**Reader vocabulary does NOT apply to this section** — it is an appendix-style
section, not in `EXEC_SECTION_IDS`, so check IDs like "M1" are acceptable here
(the validator's exec-vocabulary check only scans `exec-*`/`what-you-*`
sections).

---

## Step 5: Render `decision-traceability` (Requirement 10.1-10.4)

ALWAYS render this section, regardless of outcome. Read
`assessment-state.json.findings.recommend.fired_rule` and
`clarify_answers.*`. State:

- Which precedence rule fired (use the word "fired" or "rule" — the validator
  checks for this).
- Map AT LEAST the preview-dependence answer (`Q4`) and the traffic-shape
  answer/absence (`Q1`) to their design consequences.
- If `recommendation.tiebreak == true`: state which rule WOULD have applied
  had the log drain data been available (use the phrase "log drain" or
  "resolving" — the validator checks for this too).
- If a conflicted profile was resolved by precedence (Requirement 7.3): state
  explicitly that this was resolved by precedence, not a judgment call, citing
  which rule fired first and which would have applied to the same signals had
  an earlier rule not already won.

---

## Step 6: Render `out-of-scope` (if triggered)

Per Requirement 9.5: whenever `recommendation.outcome` is `"C"` or `"stay"`,
render the separability rationale — either "here's what's separable and why we
recommend the hybrid path" (Outcome C) or the full out-of-scope honesty
paragraph (a pre-revenue founder with a single low-traffic app and no AWS
credits is told a VPS or Cloudflare is rational and this tooling isn't for
them — Requirement 7.6). Never build a Cloudflare path; only acknowledge it.

---

## Step 7: Render `inputs-received` (if triggered)

For every finding below HIGH confidence, list which specific input would
upgrade it and the approximate effort (Requirement 9.3). This turns "missing
inputs" into a call to action, not a hidden weakness.

**Confidence-label convention (founder-facing, not the raw enum):** never print
a bare `confidence: MEDIUM`/`LOW` value to the founder in this or any
executive-flow section — translate to a plain-language phrase, the same
"technical value in a footnote, plain phrase in the visible text" pattern used
elsewhere in this plugin's reports:

| Raw confidence | Founder-facing label    |
| -------------- | ----------------------- |
| `HIGH`         | "Confirmed"             |
| `MEDIUM`       | "Best available signal" |
| `LOW`          | "Rough estimate"        |

The raw `LOW`/`MEDIUM`/`HIGH` value may still appear as a data attribute or an
HTML comment for a technical reader digging into the source — just never as
the primary visible label a founder reads.

---

## Step 8: Render `appendix-m1` (if triggered)

Per Requirement 9.4: whenever `tier1-signals.json.has_middleware == true`,
render a dedicated M1 detail section — this one IS allowed to use "M1" and
technical detail since it's an appendix section, not in `EXEC_SECTION_IDS`.

---

## Step 9: Cost-Labeling Rule (Requirement 9.6, Applies Everywhere)

EVERY dollar figure anywhere in the document — including U1's cost-driver
estimate — must be phrased as "estimated monthly cost" or "estimated monthly
savings." Never write a bare `$85`; write "an estimated monthly cost of $85."
This applies even though full cost estimation is deferred to v2 (U1 is the one
exception that still produces a number).

---

## Step 10: Render `next-steps`

An `<ol>`, always. Include: reviewing the findings, the Next.js-upgrade offer
FRAMED AS AN OFFER (Requirement 9.8 — "optionally upgrading to Next.js 16.2+
would unlock..."), and the scaffold-checkpoint opt-in.

---

## Step 11: TOC and Footer

Render `<nav class="toc">` linking every rendered section (required +
whichever conditionals fired). Render a footer containing "draft for review."

---

## Step 12: Inline CSS (Visual Consistency Across Runs)

Use a single self-contained `<style>` block — no external CDN links, no
external fonts, no images — so the report opens correctly with no network
access. Without a shared convention here, two runs of this skill can produce
reports that look nothing alike; keep this minimal (a handful of classes), not
a design system:

- `body`: system-ui/sans-serif, `max-width: 900px`, centered, readable line
  height — same "no external dependencies, works in any browser, Print to PDF
  if needed" goal as the rest of this plugin's reports.
- `.verdict`: a visually distinct banner for `exec-verdict`'s recommendation
  sentence (this is also what the validator's `_validate_verdict` check looks
  for — do not rename the class).
- `.confidence-badge`: small pill-style label for the founder-facing
  confidence phrases from Step 7 (e.g. "Confirmed" / "Best available signal" /
  "Rough estimate") — one visually consistent style per label, not a new color
  scheme per report.
- `.preflight-check-card`: the container class the validator's content-depth
  check already counts for `preflight-findings` (per
  `scripts/validate-assessment-report.py`'s `_section_content_depth`) — give
  it a simple bordered-card style so severities are visually scannable, not
  just a wall of paragraphs.
- `.callout`: a bordered/tinted box for the `out-of-scope` honesty paragraph
  and the M1 appendix's high-severity note — reuse ONE callout style for both,
  do not invent a new visual treatment per section.

Do not add a cost-tier color scheme, verdict-outcome color-coding
(A/B/C/stay), or any other visual dimension beyond what's listed above — this
skill's outcome vocabulary and confidence vocabulary are the only two things
worth a consistent visual treatment; anything more elaborate risks the report
looking "designed" in a way that undercuts the plain, honest-by-construction
tone the rest of this skill aims for.

---

## Output Contribution for Parent Orchestrator

The full `assessment-report.html` document, per the sections above. This is
handed to `report-assemble.md` for the write + validate + retry-cap loop.

---

## Error Handling

| Error Category                                                              | Behavior                                                                                                              |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| A required upstream artifact is missing a field this fragment needs         | Render the section with an honest gap note rather than fabricating content; let the validator catch structural issues |
| Ambiguity about which outcome-filter wording to use (e.g. I1 on a tiebreak) | Render BOTH branches' wording side by side, same as the `exec-tiebreak` treatment                                     |

---

## Scope Boundary

**This fragment covers rendering `assessment-report.html`'s content ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Invoking the validator (that is `report-assemble.md`'s job)
- Re-computing any finding (read from disk, never re-derive)
- Terraform/SST generation

**Your ONLY job: render the report content, correctly filtered and labeled.
Nothing else.**
