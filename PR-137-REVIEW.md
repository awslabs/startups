# Review Notes: PR #137 — "feat(heroku-to-aws): add elastic beanstalk compute target"

**PR:** https://github.com/awslabs/startups/pull/137\
**Branch:** `amjadsy:feat/heroku-elastic-beanstalk-review-feedback`\
**Head (re-reviewed):** `f1b1b6b` (force-push after initial review)\
**Cross-check:** [`PR-106-REVIEW.md`](./PR-106-REVIEW.md)

**Overall take (as of `f1b1b6b`):** The force-push fixed the original merge blockers — fail-closed gates, worker hard-route to Fargate, path-aware app SG, GitHub Actions as default deploy (Q12d), multi-env deploy coverage, and EB estimate defaults. **What is still required before merge: PR-106 §4 (compute recommendation / per-formation routing) and the related Q12c UX.** Design-time hard-routing of scaled workers is necessary but not sufficient; Clarify still presents a blind global menu and does not recommend a best fit.

---

## Remaining must-fix: §4 (and related Q12c)

### Why §2 alone is not enough

`design-mapping.md` now hard-routes persistent non-web formations with `quantity > 1` to Fargate. That stops silent capacity loss. It does **not** fulfill §4:

- Users still answer Q12c as a **global** preference with no formation-aware recommendation.
- “I don’t know” still silently becomes EB (`chosen_by: "default"`).
- There is no `compute_target.default` + `overrides[]` schema, no confidence/reasons surface, and no reuse of the existing recommendation-engine pattern.
- The user may never see _why_ workers landed on Fargate until they read design warnings — Clarify should present that up front.

### Required §4 work

Modeled on the existing org-recommendation pattern already used elsewhere in this plugin:

1. **Add a compute-target recommendation engine** that evaluates per formation:
   - `quantity > 1` on a non-web formation → hard-routes that formation to Fargate (already in Design; must also drive Clarify presentation)
   - dyno tier + traffic pattern (Q10) → weights EB (sustained/steady, lower tiers) vs Fargate (bursty / already-containerized)
   - `containerization_status` (Q12b) → already-containerized apps have lower activation cost for Fargate

2. **Make compute target a per-formation setting** with a global default and explicit overrides, e.g.:

   ```json
   "design_constraints": {
     "compute_target": {
       "default": "elastic_beanstalk",
       "overrides": [
         {
           "formation": "worker",
           "value": "ecs-fargate",
           "reason": "quantity=3 requires horizontal scaling EB cannot provide",
           "chosen_by": "system_forced"
         }
       ],
       "recommendation": {
         "value": "mixed",
         "confidence": "high",
         "reasons": ["..."]
       }
     }
   }
   ```

3. **Present the computed recommendation at Q12c** instead of a blind menu:

   ```
   Based on your formations, here's what I'd recommend:
     web        → Elastic Beanstalk (low traffic, managed platform experience)
     worker ×3  → ECS Fargate (EB can't horizontally scale workers)
   [A] Use this recommendation (default)
   [B] Everything on EB anyway
   [C] Everything on Fargate
   [D] Set per-formation myself
   ```

4. **Wire Design to the per-formation lookup** (default → override), not only a single global branch plus an ad-hoc quantity guard.

5. **Fix Q12c copy consistency:** Design impact text still describes non-web → SingleInstance without mentioning the quantity>1 Fargate route that Design already performs.

### Related remaining item (PR-106 §3)

- **Restore a short ECS Express Mode forward-look** on the Fargate override path (still fully removed in `generate-docs.md` / SKILL.md).

---

## Status after force-push `f1b1b6b`

### Fixed (do not re-raise as open)

| #  | Issue                                          | Notes                                                                     |
| -- | ---------------------------------------------- | ------------------------------------------------------------------------- |
| 1  | Fail-closed design gate rejects EB             | `design-assemble.md` now accepts EB / Fargate / EKS                       |
| 2  | Generate gate missing EB                       | `generate.md` + `generate-assemble.md` assert beanstalk + deploy artifact |
| 3  | Multi-instance workers degrade (PR-106 §2)     | Design hard-routes `quantity > 1` non-web → Fargate                       |
| 5  | App SG / ALB dangling ref (PR-106 §1 residual) | ALB ingress gated with `{{IF has_fargate}}`                               |
| 6  | CodePipeline wrong default                     | Q12d; GHA default; CodePipeline optional                                  |
| 7  | Pipeline only updates web                      | GHA + CodePipeline update all EB environments                             |
| 8  | Underspecified `pipeline.tf` condition         | Gated on `eb_deploy_method`                                               |
| 11 | Estimate defaults incomplete                   | `eb_environment` log volume; compute SP includes EB                       |
| 12 | EB vs Fargate cost comparability               | Balanced uses `min_instances` steady-state                                |

Also already done from earlier PR-106 §5: `kubernetes` → `compute_target` rename; dynamic solution-stack data source.

### Still open

| #      | Issue                                                          | Priority            | Notes                                                      |
| ------ | -------------------------------------------------------------- | ------------------- | ---------------------------------------------------------- |
| **4**  | **Compute recommendation / per-formation routing (PR-106 §4)** | **P0 — must fix**   | Design hard-route ≠ Clarify recommendation engine + schema |
| **10** | **Q12c still not recommendation-shaped**                       | **P0 — part of §4** | “I don’t know” → EB with no formation-aware recommendation |
| 9      | ECS Express Mode forward-look (PR-106 §3)                      | P1                  | Still absent                                               |
| 13–15  | Release / dual `app` SG / worker caveat in docs                | P2                  | Mostly ok; verify only                                     |

---

## PR-106 Review Item Status (updated)

| Item                                     | Status                  | Notes                                                                          |
| ---------------------------------------- | ----------------------- | ------------------------------------------------------------------------------ |
| §1 Fargate SG → VPC CIDR                 | **Fixed**               | ALB-SG ingress retained; EB-only omits that ingress via `has_fargate` gate     |
| §2 Worker horizontal scaling             | **Fixed (Design)**      | Hard-route to Fargate when `quantity > 1` on non-web                           |
| §3 Philosophy + Express Mode             | **Partial**             | Philosophy rationale present; Express Mode still removed                       |
| §4 Recommendation engine / per-formation | **Not done — must fix** | Blind global Q12c remains; no overrides schema; no recommendation presentation |
| §5 `compute_target` rename               | Done                    |                                                                                |
| §5 Solution stack data source            | Done                    |                                                                                |
| §5 / deploy UX (GHA vs CodePipeline)     | **Fixed**               | Q12d + GHA default + generated workflow                                        |

---

## Suggested path to merge

1. **Implement §4** (recommendation engine + per-formation `compute_target` schema + recommendation-shaped Q12c) — **required**.
2. Update Design to consume `default` / `overrides` rather than only global value + ad-hoc guard.
3. Restore a short **ECS Express Mode** forward-reference on the Fargate path.
4. Align Q12c Design-impact / defaults copy with the mixed EB+Fargate reality.

Until §4 lands, do not treat the worker hard-route as closing the PR-106 recommendation gap.
