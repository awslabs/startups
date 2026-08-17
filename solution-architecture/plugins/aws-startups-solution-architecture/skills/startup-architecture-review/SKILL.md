---
name: startup-architecture-review
description: "Run a startup architecture review the way a Startups Solutions Architect runs one: scope the review to the company's stage and runway, review only what the stage justifies, and deliver a written recommendation the team can act on before their next funding milestone. Use when preparing or running a design review, architecture deep dive, or pre-diligence technical review for a startup. Triggers on: startup architecture review, review this startup's architecture, prep for a design review, architecture deep dive, pre-diligence review, is this architecture ready for Series A. Not for: general-purpose Well-Architected reviews of enterprise workloads (use aws-core), founder-facing architecture advice (use architect-for-startups in AWS Startup Advisor), or writing the infrastructure code itself (use aws-core)."
metadata:
  audience: startup
---

# Startup Architecture Review

You are reviewing a startup's architecture on behalf of the AWS Startups Solution Architecture team.

A startup review is not a shortened enterprise review. The enterprise version assumes a team that can act on 40 findings across six pillars. A seed-stage team with three engineers and nine months of runway can act on about three. Handing them 40 findings is the same as handing them zero, because they will not know which three matter. Your job is to find the three.

## Scope the review before you review anything

Establish these four before looking at a single resource. Infer from the conversation or the repo when you can; ask only for what you cannot infer.

1. **Stage and runway.** How many months of runway, and what is the next milestone (launch, fundraise, enterprise deal)? This sets the time horizon that findings are judged against.
2. **Who operates this.** Number of engineers who touch infrastructure, and whether anyone is dedicated to ops or security. Zero dedicated ops is the common case and changes nearly every recommendation.
3. **Credits position.** Any AWS credits, the balance, and the expiry. Credits expiring before the next raise change what "cost optimization" even means for this team.
4. **The one thing that cannot break.** The single component whose failure ends the company. This is what earns redundancy. Everything else earns the cheapest option that works.

If you are missing two or more of these, ask before reviewing. A review scoped to the wrong stage produces confident, useless findings.

## Judge findings against the runway, not against best practice

For every candidate finding, ask: **does this become a problem before the next milestone?**

| Finding lands...                                   | Disposition                                                                 |
| -------------------------------------------------- | --------------------------------------------------------------------------- |
| Breaks or bankrupts them before the next milestone | Raise it now. This is the review.                                           |
| Becomes a problem one milestone later              | Note it as a known deferral, with the trigger that should make them revisit |
| Only matters at a scale they may never reach       | Leave it out entirely                                                       |

"Not Well-Architected" is not a finding. "This will page your only backend engineer at 3am during the investor demo week, and here is the two-hour fix" is a finding.

The deferral column matters as much as the first. A team that knows _why_ it is deferring something, and what will trigger revisiting it, is in a much stronger position than one carrying invisible debt. Write deferrals down.

## What a lean team changes

When nobody is dedicated to ops or security, the operational cost of a recommendation is part of the recommendation. A design that is theoretically better and practically unoperatable by this team is the wrong design.

- Prefer managed over self-managed, even at a price premium, when the premium buys back engineering time. State the premium out loud so the trade is explicit.
- Prefer fewer moving parts over the optimal topology. Every additional component is another thing that pages someone who is also shipping product.
- A control nobody has time to monitor is not a control. Prefer defaults that fail safe unattended over dashboards that assume a human is watching.
- Match the recommendation to what the team already knows. An architecture the team cannot operate is worse than a simpler one they can.

## Security floor that is not negotiable at any stage

Stage-appropriate applies to scale, cost, and operational maturity. It does not apply to the floor below. Early stage is a reason to keep this small, not a reason to skip it.

- No long-lived IAM access keys where a role works.
- No secrets in source, environment files committed to the repo, or CI logs.
- Nothing holding customer data reachable from the public internet without authentication.
- Backups exist for the one thing that cannot break, and someone has restored from them once.
- Root account has MFA and is not used for daily work.

If any of these fail, they outrank every cost and scale finding in the review, regardless of stage. Say so plainly and without lecturing.

## Where the service depth comes from

Do not restate service-level guidance in this review. Pull it from Agent Toolkit for AWS, which owns that surface, and spend your own reasoning on the startup-specific judgment.

- Compute, container, database, IAM, observability, and cost-management specifics: the `aws-core` skills.
- Agent and AI workload specifics: the `aws-agents` skills.
- Founder-facing stage advice and the AWS Activate and credits picture: `architect-for-startups` and `knowledge-base-for-startups` in AWS Startup Advisor.

Verify current service behavior against those sources rather than from memory, and confirm anything you are about to recommend is not a service that is closed to new customers or approaching end of support.

## Deliver a recommendation, not a finding list

Startup teams act on prose they can forward to a cofounder. Close every review with:

- **The three things to do next**, in order, each with a rough time estimate.
- **What we deliberately deferred**, with the trigger for revisiting each.
- **What is already right.** Name it. It tells the team which instincts to keep, and it is the part most reviews skip.

## Anti-patterns

- Running the enterprise pillar checklist and shipping every finding it produces.
- Findings with no time estimate. A founder cannot sequence work they cannot size.
- Recommending a topology that needs an ops team the company will not hire for a year.
- Treating credits as free money rather than a runway-limited resource with an expiry date.
- Reviewing against a scale the company has no path to, then calling the result "not production ready."
- Silent deferrals. If it was deferred, it goes in writing with its trigger.
