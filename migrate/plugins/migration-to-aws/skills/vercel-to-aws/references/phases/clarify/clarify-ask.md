---
_fragment: ask
_of_phase: clarify
_contributes:
  - clarify-answers.json (all question entries)
---

# Clarify Phase: Question Set

> Self-contained fragment. Implements the fixed question set (Requirement 3.1),
> consulting `tier1-signals.json` + `discovery.json` first to skip anything
> already answered (Requirement 2.3).

**Execute ALL steps in order. Do not skip or optimize.**

---

## Step 0: Present a Discovery Summary (Before Any Question)

Before asking anything, tell the founder what PreScan/Discover already
determined — this is what makes the fixed question set feel short rather than
arbitrary, and confirms out loud that nothing already answered is about to be
re-asked. Pull directly from `tier1-signals.json`/`discovery.json`/
`coupling-score.json`; do not re-derive anything, only summarize:

> "Before I ask anything — here's what I already found: Next.js
> {next_version} ({package_manager}). {If has_middleware: 'middleware.ts
> present, covering {matcher patterns}.' Else: 'No middleware.'} {N} API
> route(s) detected{: list if <=3}. {Coupling Score one-liner, e.g. 'ISR and
> edge middleware both in use.'} {If any Pre-Flight Check is HIGH severity:
> '{count} finding(s) at HIGH severity — covered in the report, not here.'}
>
> That leaves {N} question(s) only you can answer."

Keep this to 2-4 sentences — a grounding statement, not a repeat of the full
`discovery.json`. State the resulting question count so the founder knows the
scope before starting (mirrors the "just N questions" framing used elsewhere in
this plugin's Clarify phases). This summary is founder-facing output only — it
is NOT a `clarify-answers.json` entry, the same way PreScan's and Discover's own
completion messages aren't.

---

## Question Set (Requirement 3.1)

Ask the following, in order, applying the skip logic noted per question. Batch
no more than 3-4 at a time to avoid overwhelming the founder in one message,
consistent with the plugin's Mom-Test-shaped question style used elsewhere.

### Q1 — Traffic Shape

> "Roughly, is your traffic spiky (occasional bursts far above typical) or
> sustained (fairly steady load)? If you have a rough peak-to-median ratio in
> mind, share it — otherwise a general sense is fine."

Always ask (never skippable — Discover's `usage_metrics` are, at best, coarse
aggregates per Requirement 4.4, never a substitute for this answer unless a log
drain was supplied).

**Confirm-first phrasing when a log drain exists (Tier 2):** don't re-ask cold —
propose the detected value and ask the founder to confirm or correct it, the
same "detected, confirm-or-edit" pattern used for auto-extracted values
elsewhere in this plugin's Clarify phases (scaled down to a single question
here, since Q1 is the only one with a real extractable prior signal):

> "I have {N} days of log drain data showing a peak:median ratio of {X}:1,
> which reads as {spiky|sustained} — does that match your sense of it, or has
> something changed recently?"

This still counts as asking Q1 (it is never silently auto-filled — Requirement
4.4 treats even log-drain-backed traffic shape as something the founder should
confirm, not something Discover decides alone), just informed by better data
than the cold version above.

`design_consequence`: "feeds recommend phase rule 3 (traffic shape decides A vs.
B) and rule 4 (tiebreak fires if this answer is vague and no log drain exists)"

### Q2 — Migration Trigger

> "What actually triggered you to consider this migration? (bill size, bill
> variance/unpredictability, running out of credits, data locality requirements,
> hitting a platform limit, something else)"

Always ask.

`design_consequence`: "motivational context for the report's decision
traceability appendix; does not directly drive a precedence rule but frames the
recommendation's framing (e.g. variance-driven founders lean toward Outcome B's
predictability pitch); also feeds report-render.md's what-you-gain section -
a credits/funding-pressure answer here surfaces the AWS Activate eligibility
callout"

### Q3 — Team DevOps Bandwidth

> "Who owns production when something breaks? Do you have dedicated DevOps
> capacity, or is this a founder/small-team responsibility?"

Always ask.

`design_consequence`: "feeds recommend phase rule 3 (small team favors Outcome A;
a stated debuggability preference favors Outcome B) and rule 2 (an existing
separate API service, if mentioned here, feeds the Lambda-hostility check)"

### Q4 — Preview Deployment Dependence

> "How load-bearing are PR preview deployments for your team's workflow? (e.g.
> 'we review every PR live before merge' vs. 'we barely use them')"

Always ask — this is the single highest-leverage question in the whole
assessment (Requirement 7.1 rule 1 fires on this answer FIRST, before any other
rule).

`design_consequence`: "feeds recommend phase rule 1 (preview-dependence +
separability check) - the FIRST precedence rule evaluated; a load-bearing answer
here can short-circuit the entire recommendation to Outcome C or stay-on-Vercel
before any other signal is consulted"

### Q5 — Next.js Upgrade Willingness (Confidence Upgrade Offer, Never a Gate)

Only ask if `tier1-signals.json.next_version < "16.2.0"`. If already >= 16.2,
skip this question entirely (Requirement 2.4 — phrase using the PreScan-detected
version, and if it's already current there is nothing to offer).

> "Your app is on Next.js {detected_version}. Upgrading to 16.2+ would unlock
> the Adapter API's typed build output for higher-confidence discovery, and
> positions you for the future verified AWS adapter when it reaches GA. This is
> entirely optional — my default recommendation path (migrate now on OpenNext
> v3) works regardless of your current version. Interested, or would you rather
> stick with your current version for now?"

Per Requirement 3.3-3.5: this answer NEVER gates progression to Recommend. Record
it purely as a preference signal.

`design_consequence`: "confidence-upgrade offer only, per Requirement 3.4 -
NEVER feeds a precedence rule as a gate; recorded for the report's Next Steps
section (Requirement 9.8)"

### Q6 — Current Vercel Spend

Only ask if `discovery.json.usage_metrics.billing_data` is NOT present (i.e. the
Vercel API did not return billing information). If billing data was successfully
retrieved from the API, skip this question — the estimate phase will use the
API-sourced data directly.

> "What's your approximate monthly Vercel spend? This helps me compare AWS
> costs against your current bill. (Just a ballpark is fine — $0-50, $50-200,
> $200-1000, or $1000+)"

`design_consequence`: "feeds estimate phase current_costs.vercel_monthly as the
Vercel baseline for cost comparison; when skipped, estimate derives the baseline
from Vercel API usage metrics instead"

### Q7 — Database Size (Conditional: Postgres Peripheral Detected)

Only relevant if `discovery.json.peripherals[]` contains a `"postgres"` entry
(the schema's lowercase type value — match case-insensitively; a literal
capital-P match would wrongly skip this question).
If no Postgres peripheral was detected, skip entirely.

**When Discover already measured the size, confirm — don't ask cold** (the
skip-logic principle: never ask what discovery already determined). If a
postgres entry in `discovery.json.storage_integrations[]` carries
`metadata.sizeBytes`, derive the band (A < 1 GB, B 1-10 GB, C 10-100 GB,
D > 100 GB; decimal GB — `sizeBytes / 1e9`) and present it as a confirmation
instead of the open question:

> "Your Vercel Postgres store '{name}' reports ~{X} GB, which puts it in the
> {band} band — I'll size the migration tooling and RDS instance accordingly.
> Sound right, or is the effective size different? (Store metadata can lag
> reality — e.g. pending imports or recent heavy growth.)"

Record the confirmed band as the answer, noting `"derived from
storage_integrations sizeBytes, founder-confirmed"` in the entry — or the
founder's correction when they give one (their number wins; it is Tier 3
founder-attested input).

**Only when no `sizeBytes` is available**, ask the original open question:

> "Approximately how large is your Vercel Postgres database? This determines
> which migration tool I'll set up in the scripts.
> (A) Less than 1 GB
> (B) 1-10 GB
> (C) 10-100 GB
> (D) More than 100 GB"

`design_consequence`: "feeds generate phase migration script selection — pg_dump
for < 10 GB, AWS DMS for >= 10 GB — and RDS instance sizing in the estimate
(db.t4g.micro for < 1 GB, db.t4g.small for 1-10 GB, db.r6g.large for 10-100 GB,
db.r6g.xlarge for > 100 GB)"

### Q8 — Compliance Requirements

Always ask (compliance drives the baseline.tf conditional section, which is
valuable regardless of migration outcome).

> "Do you have compliance requirements that your AWS environment needs to
> meet? (Select all that apply, or 'None')
> (A) SOC 2
> (B) PCI DSS
> (C) HIPAA
> (D) FedRAMP
> (E) None"

`design_consequence`: "feeds generate phase baseline.tf — compliance answer
drives the conditional section (AWS Config recorder, Security Hub + standards
subscriptions) and CloudTrail log retention period (90 days default, up to 2190
for HIPAA)"

---

## Skip Logic (Requirement 2.3, Mandatory)

Before presenting ANY question, check whether PreScan/Discover already resolved
it:

- **Q1 is never skippable** by discovery alone — Discover's `usage_metrics` are
  explicitly LOW confidence without a log drain (Requirement 4.4), so this
  question always adds signal (it either confirms or supplements the log-drain
  data, or is the ONLY traffic-shape signal when no log drain exists).
- **Q6 (Vercel spend) skips** when `discovery.json.usage_metrics.billing_data`
  is present — the estimate phase uses the API-sourced billing data directly.
- **Q7 (database size) skips** when no `"postgres"` entry (case-insensitive) exists in
  `discovery.json.peripherals[]` — no database means no sizing question.
- **Q8 (compliance) is never skippable** — compliance drives baseline.tf and
  retention periods regardless of what Discover found.
- **No project-scoping question exists in this fixed set** — if it did, it would
  be skipped when `tier1-signals.json.project_scoping_needed == false` (only one
  in-scope project). This skill's Clarify does not currently ask project scoping
  as a separate question (PreScan already resolves it); this note exists so a
  future question addition remembers the skip rule.
- **A middleware-specific question is NOT part of this fixed set** — PreScan's
  `has_middleware` and Discover's `middleware_analysis.per_matcher_pattern`
  already answer "what does your middleware do" at MEDIUM-HIGH confidence via
  static analysis (Requirement 1.3's Tier 2 "one-sentence answer" input is
  optional corroboration only, not a required Clarify question). If
  `tier1-signals.json.has_middleware == false`, there is nothing to ask about
  middleware at all — this is automatically satisfied by the fixed set simply
  not containing a middleware question.

---

## Output Contribution for Parent Orchestrator

For each question actually asked (per skip logic), contribute an entry:

```json
{
  "Q1_traffic_shape": {
    "prompt": "<exact question text presented>",
    "answer": "<founder's answer>",
    "design_consequence": "<per the table above>"
  }
}
```

For Q5, if skipped because `next_version >= 16.2`, do NOT contribute an entry at
all — a skipped question has no `clarify-answers.json` entry, distinguishing it
from a question that was asked and declined. Same rule for Q6 (skipped when billing data present) and Q7 (skipped when no Postgres detected).

---

## Error Handling

| Error Category                                           | Behavior                                                                                                                                                         |
| -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Founder gives a vague/non-answer to Q1                   | Record the answer verbatim as given; `recommend-rules.md`'s fallback behavior (§3.4 of design.md) treats a vague Q1 as LOW confidence, feeding rule 4's tiebreak |
| Founder gives a vague/non-answer to Q4                   | Record verbatim; `recommend-rules.md`'s fallback treats an unanswered/ambiguous Q4 as "not load-bearing," falling through to rule 2                              |
| Founder answers Q5 with interest but doesn't upgrade now | Record the interest; this does not change ANY downstream logic — it is purely reported in Next Steps                                                             |
| Founder skips Q6 (Vercel spend)                          | Record `"answer": "skipped"` — estimate phase falls back to plan-based estimation or marks baseline as unavailable                                               |
| Founder unsure about Q7 (database size)                  | Record `"answer": "unknown"` — generate phase defaults to pg_dump (conservative) and estimate uses db.t4g.small sizing                                           |
| Founder selects "None" for Q8 (compliance)               | Record `"answer": "none"` — baseline.tf emits the always-on resources only, no compliance-conditional section                                                    |

---

## Scope Boundary

**This fragment covers presenting the fixed question set and recording answers
ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Applying the Recommendation Engine's precedence rules to these answers (that
  is `recommend-rules.md`'s job)
- Asking any question beyond the fixed set defined here
- AWS service names or recommendations

**Your ONLY job: ask the fixed question set, honoring skip logic, record
answers with prompt + design_consequence. Nothing else.**
