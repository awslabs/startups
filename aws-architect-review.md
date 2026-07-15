# Review: `aws-architect.md` — Startup-Specific Guidance

## Summary

Issues are categorized as:

- **Factual errors** — contradicts known service status
- **Inverted defaults** — guidance is backwards relative to what most startups actually prefer
- **Missing guidance** — important warnings absent
- **Internal contradictions** — the document disagrees with itself

---

## Factual Errors

### F-1: App Runner recommended but KTLO / not taking new customers

| Section                 | What it says                                                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Compute table, Seed row | "Lambda OR App Runner — App Runner if you need WebSockets or >15min processing"                                        |
| Bold callout            | "App Runner is often better than Fargate for seed-stage startups... That's 2-3 days of engineering time you get back." |

**Problem:** App Runner is in keep-the-lights-on mode and is not onboarding new customers.

**Fix:** Remove App Runner from the seed-stage row. For the WebSocket / long-running use case, recommend ECS Fargate with a note that the ALB setup cost is worth it to avoid a forced re-platform later. Alternatively, Lambda function URLs + response streaming cover some of the gap.

---

## Inverted Defaults

### I-1: DynamoDB as the default MVP database

| Section                 | What it says                                                     |
| ----------------------- | ---------------------------------------------------------------- |
| Database table, MVP row | "DynamoDB on-demand — $0 at zero traffic"                        |
| PostgreSQL rows         | Only appear for "relational needs" or "cost-sensitive" scenarios |

**Problem:** Most startups are comfortable with PostgreSQL and actively prefer it. DynamoDB is fine for startups that specifically need key-value/document access patterns at scale, but making it the universal MVP default steers startups away from the flexibility of SQL, joins, and ad-hoc queries — things they almost always need as they iterate on product.

**Fix:** Flip the default. PostgreSQL (RDS t4g.micro at $12/mo, or Aurora Serverless v2 if scaling matters) should be the default for most startups. DynamoDB should be the recommendation only when the startup has confirmed key-value access patterns and doesn't need relational queries.

---

## Missing Guidance

### M-1: "Always use Graviton" lacks caveats

| Section             | What it says                                               |
| ------------------- | ---------------------------------------------------------- |
| Credits-Aware table | "Always use Graviton. 20% cheaper AND credits last longer" |

**Problem:** "Always" is incorrect. Graviton is ARM64. It doesn't work for:

- Native dependencies compiled only for x86_64 (proprietary .so files, some older native Node addons, vendor SDKs shipping only amd64 binaries)
- .NET Framework workloads (Windows-only, no ARM support)
- Code with x86 inline assembly or SSE/AVX SIMD intrinsics

And it requires rebuild/retest for:

- Docker images built only for `linux/amd64` (need multi-arch CI)
- Native compilation targets (Rust, Go with CGO, C extensions in Python/Ruby)

For the typical startup running Node/Python/Go in containers with no native deps, Graviton is correct. But "always" will send someone with legacy native dependencies into a deploy failure.

**Fix:** Change to "Prefer Graviton unless you have native x86 dependencies. 20% cheaper AND credits last longer. Test your container on ARM before committing."

---

## Internal Contradictions

### C-1: "Always managed services" vs. EKS at Series B+

| Section                  | What it says                                                                 |
| ------------------------ | ---------------------------------------------------------------------------- |
| Credits-Aware table      | "Always managed. Credits expire; the engineering time you save is permanent" |
| Compute table, Series B+ | "EKS only if team already knows it"                                          |

EKS is one of the least "managed" AWS services — you still own node groups, cluster upgrades, networking plugins, RBAC, and the Kubernetes control plane lifecycle. The blanket "always managed" statement contradicts the EKS recommendation. This sentiment contradicts the migration plugin which only recommends EKS if you have multi cloud needs and like running Kubernetes.

**Fix:** Qualify the managed-services stance: "Always prefer managed services. EKS is the exception — only adopt it if your team already has Kubernetes expertise, and understand you're taking on significant operational overhead. "

### C-2: DynamoDB — "don't worry about access patterns" vs. "medium risk, can spike fast"

| Section          | What it says                                                                     |
| ---------------- | -------------------------------------------------------------------------------- |
| Database section | "Use one table per entity, worry about access patterns later"                    |
| 10x Cost Test    | "DynamoDB on-demand: 10x reads/writes = ~10x cost. Medium risk — can spike fast" |

If you tell startups not to think about access patterns, they're more likely to build inefficient query patterns that trigger the exact cost spikes the 10x section warns about. The two sections give advice that leads to the problem the other section flags.

**Fix:** Connect them: "DynamoDB on-demand is $0 at zero traffic, but costs scale linearly with reads/writes — design your access patterns early enough to avoid surprise bills at traction."

### C-4: Single-AZ guidance has three different thresholds

| Source              | Trigger for Multi-AZ                                    |
| ------------------- | ------------------------------------------------------- |
| Database section    | "until you have SLA customers"                          |
| Gotchas table       | "until you have paying customers with SLA expectations" |
| Credits-Aware table | "Enable if credits cover it AND you're past MVP"        |

The credits row suggests enabling Multi-AZ earlier (past MVP + credits available), while the other two sections say wait for SLA customers specifically. A startup past MVP with credits but no SLA customers gets contradictory guidance depending on which section they read.

**Fix:** Unify to one threshold. Suggested: "Single-AZ until you have paying customers with uptime commitments (SLA or contractual). If credits cover the cost and you're already past MVP, enabling Multi-AZ early is fine as insurance — but don't let it become a hard dependency before you need it."

### C-5: "Monolith" recommendation vs. Lambda as default compute

| Section                     | What it says                                         |
| --------------------------- | ---------------------------------------------------- |
| Differs from Best Practices | "Monolith or modular monolith. Split at pain points" |
| Compute table, Pre-seed     | "Lambda + API Gateway — Ship in hours, not days"     |

Lambda + API Gateway inherently pushes toward function-per-endpoint decomposition — the opposite of a monolith. If you actually want a monolith at early stage, the compute recommendation should be a single container service, not Lambda. These two sections advise incompatible architectures without acknowledging the tension.

**Fix:** Either qualify the monolith advice ("if you're on containers, prefer a monolith; if you're on Lambda, a well-organized single-repo with shared layers achieves the same cohesion") or restructure the compute table to distinguish between "I want a monolith" and "I want serverless functions" paths.
