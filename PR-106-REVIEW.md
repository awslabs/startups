# Review Notes: PR #106 — "Feat/elastic beanstalk heroku"

**Reviewer context:** Read the full diff against `main` (Heroku-to-AWS skill: SKILL.md, clarify, design, estimate, generate-terraform, generate-docs). This document consolidates feedback into one place for discussion before merge.

**Overall take:** The core idea — treating Elastic Beanstalk as a PaaS-to-PaaS match for Heroku users — is sound and well-researched. EB is actively maintained (monthly AL2023 platform releases through mid-2026) and is meaningfully easier to operate than ECS for teams coming from a "just push code" mental model. AWS killing App Runner in April 2026 makes the "give Heroku users a managed-platform option" gap real. Structurally, the PR follows existing plugin conventions well (sizing data in `knowledge/design/`, `_knowledge` frontmatter, phase-file conventions).

That said, there are two correctness/security issues that should block merge as-is, one design-principle reversal that needs an explicit decision (not a silent change), and one architectural gap (no actual recommendation logic) worth addressing before this becomes the default experience for all Heroku migrations.

---

## 1. Blocking: Security group regression on the Fargate override path

**Where:** `generate-terraform.md`, the security groups section.

**What changed:** The Fargate task security group previously scoped ingress to the ALB security group only:

```hcl
ingress {
  security_groups = [aws_security_group.alb.id]
  description     = "Traffic from ALB"
}
```

The PR replaces this with a shared "app" security group (used by EB, Fargate, and EKS alike) that opens ingress from the entire VPC CIDR:

```hcl
ingress {
  from_port   = 0
  to_port     = 65535
  cidr_blocks = [var.vpc_cidr]
  description = "Traffic from within VPC (covers EB-managed ALB and direct service communication)"
}
```

**Why this matters:** For EB, this is a defensible trade-off — EB provisions its own ALB internally and Terraform has no direct handle on that ALB's security group, so VPC-CIDR-scoped ingress is a reasonable compromise (and should be called out as such in a comment). But this same widened rule is applied to the **Fargate override path too**, where the ALB security group _is_ available and referenceable in Terraform. That means choosing Fargate — supposedly the "more control" option — actually ships with a wider-open security posture than before this PR, and wider than the EB path needs to justify.

**Ask:** Keep two distinct app security groups (or a conditional block):

- EB path → VPC CIDR ingress (documented trade-off, comment explaining why)
- Fargate override path → retain ALB-SG-scoped ingress (the pre-PR behavior)

This also affects the `security.tf` design rubric's stated hard rule elsewhere in the plugin ("start with no access and add only what is needed" — least privilege by default). The Fargate path should continue to honor that.

---

## 2. Blocking: Worker horizontal scaling silently degrades on the default path

**Where:** `design-mapping.md` (Elastic Beanstalk Branch, non-web process types) and `dyno-eb-sizing.json` (`_scaling.non_web`).

**What happens today:** Any Heroku `worker`/`clock`/`release` formation maps to an EB **SingleInstance** environment, which is hard-capped at 1 instance. If the source Heroku formation has `quantity > 1` (very common for Sidekiq/Celery-style worker fleets), the PR adds a warning string to `warnings[]` inside `aws-design.json` and proceeds with `max_instances: 1`.

**Why this matters:** This is a real capability loss, not a sizing rounding error — an app running 3 worker dynos today will silently end up with 1 worker instance after migration unless the user (a) reads `aws-design.json` directly, which most users never do, and (b) understands EB's tier model well enough to recognize the implication. Given that EB is the _default_ path (no explicit user action required to land here), this means a meaningful fraction of production Heroku apps will get a functionally degraded architecture out of the box.

**Ask, in order of preference:**

1. **Best:** Route any formation with `quantity > 1` to the Fargate branch automatically (regardless of the global Q12c answer), and say so plainly: _"Your `worker` formation runs 3 instances — Elastic Beanstalk can't scale workers horizontally, so this formation will use Fargate instead. Your `web` formation will still use Elastic Beanstalk."_ This requires per-formation compute routing rather than one global switch (see §4 below).
2. **Acceptable minimum:** Surface this as a **Clarify-phase** question/confirmation the moment `quantity > 1` is detected in discovery — before Design runs — rather than only as a post-hoc warning buried in a JSON artifact. Don't let a user complete Design/Generate without having seen and acknowledged the trade-off.

---

## 3. Needs an explicit decision: reversal of the "no legacy-to-legacy" philosophy

**Where:** `SKILL.md`, Philosophy section.

**What changed:** Pre-PR:

> "No legacy-to-legacy: Do not recommend Elastic Beanstalk or AWS App Runner... as migration targets. Fargate is the sole compute target."

Post-PR:

> "PaaS-to-PaaS by default: Elastic Beanstalk... is the default compute target."

This isn't a bug, but it is a straight reversal of a documented design principle, and the PR changes it in-place rather than discussing the trade-off. Some grounding, for the discussion:

- EB is not deprecated or in maintenance mode — it gets regular platform updates and AWS has made no availability-change announcement (unlike App Runner).
- The public perception of EB skews toward "AWS's aging, less-loved answer to Heroku" (long-running HN sentiment, teams that migrated _off_ EB to ECS for more control). That perception isn't fully deserved technically, but it's the water the plugin's target audience swims in — worth being aware of.
- AWS's own guidance for "give me an App-Runner-like experience" is trending toward **ECS Express Mode**, not EB — that's the service AWS pointed App-Runner customers to. Express Mode is very new, so it's reasonable that this PR doesn't build on it yet, but the original SKILL.md's one-line mention of Express Mode as a future path got deleted rather than preserved/updated.

**Ask:** Not a blocker on its own, but this reversal should get an explicit thumbs-up from whoever owns the philosophy section, with the rationale written into the PR description (or better, into the SKILL.md philosophy bullet itself) — not just inferred from the diff. Also suggest restoring a short forward-looking note about ECS Express Mode as a "watch this space" option for the Fargate override path.

**Related inconsistency confirmed in the diff:** the ECS Express Mode content block in `generate-docs.md` was fully deleted (not just re-gated behind `has_fargate`), but the file's own Step-0 verification checklist still says "If has_fargate: Contains 'ECS Express Mode' informational paragraph." As written, the generator's self-check expects output content that no longer exists anywhere in the template — that checklist line needs to be removed or the paragraph needs to be restored, otherwise this is a latent self-contradiction in the generation logic, independent of whether the philosophy question above gets resolved one way or the other.

---

## 4. Design gap: Q12c is a blind preference menu, not a recommendation

**Where:** `clarify-interview.md`, Q12c.

**What happens today:** The compute target choice is a single global question with no signal-driven logic:

```
A) Elastic Beanstalk (default)
B) ECS Fargate
C) EKS
D) I don't know — recommend the best fit
```

Option D just defaults to A. There's no actual "recommend the best fit" happening — and the choice applies globally to every formation in the app, even though real Heroku apps commonly mix a low-traffic web dyno with a multi-instance worker fleet that need different treatment (see §2).

**Suggested approach**, modeled directly on the existing `org-recommendation-engine.md` pattern already used for Q7.5 (organization structure) elsewhere in this plugin — signals → decision table → confidence → plain-language reasons → user confirms or overrides:

1. **Add a compute-target recommendation engine** that evaluates, per formation:
   - `quantity > 1` on a non-web formation → hard-routes that formation to Fargate (see §2, this is a correctness fix, not just a UX nicety)
   - dyno type tier (eco/basic/standard vs performance-*) + traffic pattern (Q10) → weights EB (sustained/steady, lower tiers) vs Fargate (bursty, already-containerized)
   - `containerization_status` (Q12b) → already-containerized apps have a lower activation cost for Fargate
2. **Make compute target a per-formation setting** with a global default and explicit overrides, e.g.:

   ```json
   "design_constraints": {
     "compute_target": {
       "default": "elastic_beanstalk",
       "overrides": [
         { "formation": "worker", "value": "ecs-fargate", "reason": "quantity=3 requires horizontal scaling EB cannot provide", "chosen_by": "system_forced" }
       ],
       "recommendation": { "value": "mixed", "confidence": "high", "reasons": [ "..." ] }
     }
   }
   ```

   This replaces the single global `design_constraints.kubernetes.value` fork in `design-mapping.md` with a per-formation lookup (default → override), which is a moderate but contained change to the Design phase's control flow.
3. **Present the computed recommendation at Q12c** instead of a blind menu:

   ```
   Based on your formations, here's what I'd recommend:
     web        → Elastic Beanstalk (low traffic, managed platform experience)
     worker ×3  → ECS Fargate (EB can't horizontally scale workers)
   [A] Use this recommendation (default)  [B] Everything on EB anyway  [C] Everything on Fargate  [D] Set per-formation myself
   ```

This is a bigger lift than the PR as submitted (new recommendation-engine file, schema change, per-formation Design loop instead of a single branch), but it directly fixes the §2 correctness bug instead of just documenting it as a known limitation, and it reuses a pattern the codebase already has precedent for — so it shouldn't read as a foreign addition to reviewers familiar with the org-recommendation work.

**Ask:** Doesn't need to land in this PR necessarily, but at minimum the worker hard-block from §2 should be pulled out of "nice to have" and into this PR, since it's the one piece that's a functional regression rather than a design preference.

---

## 5. Minor / non-blocking

- **`design_constraints.kubernetes` holding `"elastic_beanstalk"` as a value.** Acknowledged in the PR as awkward, with a rename to `compute_target` planned as follow-up. Agree with the plan — just flagging that this should be prioritized soon after merge, since every migration run between now and the rename will have "kubernetes" fields with non-Kubernetes values in its `preferences.json`, which is confusing for debugging and for anyone reading a real migration's artifacts.
- **Hardcoded `solution_stack_name` (`v4.4.0`).** Documented as a known limitation. Given how frequently EB platform versions rev (multiple times a year per the release notes), consider swapping to a `data "aws_elastic_beanstalk_solution_stack"` lookup with a regex now rather than as a later follow-up — it's a small change and avoids generating Terraform that references a stale platform version within a few months.
- **CodePipeline requires manual GitHub connection setup.** Fine as documented in MIGRATION_GUIDE — just flagging this as the one step in the "git push to deploy" pitch that isn't actually zero-touch on first run.

---

## Suggested path to merge

1. Fix the security group scoping so the Fargate override path keeps ALB-SG-scoped ingress (§1) — should be a small, contained diff.
2. Either hard-route `quantity > 1` non-web formations to Fargate automatically, or surface the trade-off during Clarify before Design runs (§2) — this is the one item I'd consider a merge blocker on correctness grounds.
3. Get explicit sign-off on the philosophy reversal (§3) and restore a short ECS Express Mode forward-reference.
4. §4 (recommendation engine) can reasonably be a fast-follow PR rather than blocking this one, provided §2's hard-block logic is pulled forward into this PR.
