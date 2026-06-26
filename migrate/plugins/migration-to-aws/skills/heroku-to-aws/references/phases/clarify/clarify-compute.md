# Category C — Compute Model (Kubernetes Preference)

_Fire when:_ Always (all Heroku stacks with formations/dynos).

---

## Q — Would you prefer EKS or ECS Fargate for your containerized workloads?

_Fire when:_ Always. This is a subjective team-expertise question that determines the compute orchestration target.

**Rationale:** Heroku dynos always require containerization for AWS. The user's Kubernetes expertise and preference determines whether we target EKS (more control, requires K8s ops) or ECS Fargate (simpler, fully managed).

**Context for user:** Frame practically so the user gives an honest answer:

- **EKS preferred** — team writes Helm charts, manages clusters, and actively wants Kubernetes
- **EKS acceptable** — team can operate K8s but would prefer managed node groups to minimize burden
- **ECS Fargate preferred** — team wants simplest managed containers, no cluster management

> Your choice determines whether we deploy containers to EKS (Kubernetes) or ECS Fargate (simpler managed containers). EKS gives you more control but requires Kubernetes operational expertise. Fargate eliminates cluster management entirely.
>
> A) EKS preferred — team has Kubernetes expertise, wants full K8s control
> B) EKS acceptable — team can operate K8s, prefers managed node groups
> C) ECS Fargate preferred — simplest managed containers (default)
> D) I don't know

| Answer | Recommendation Impact |
| --- | --- |
| EKS preferred | EKS with self-managed node groups — full K8s control, preserves team expertise |
| EKS acceptable | EKS with managed node groups — reduces operational burden while keeping K8s |
| ECS Fargate preferred | ECS Fargate — eliminates Kubernetes management entirely; simplest operational model |

Interpret:

```
A -> design_constraints.kubernetes: "eks-managed" — EKS with self-managed node groups
B -> design_constraints.kubernetes: "eks-or-ecs" — EKS with managed node groups  
C -> design_constraints.kubernetes: "ecs-fargate" — ECS Fargate (default)
D -> design_constraints.kubernetes: "ecs-fargate" (same as default)
```

**Default:** C → `design_constraints.kubernetes: "ecs-fargate"` with `source: "default"`

**preferences.json output:**

```json
{
  "design_constraints": {
    "kubernetes": "eks-managed | eks-or-ecs | ecs-fargate"
  }
}
```

This field name and values are intentionally identical to the GCP skill's `design_constraints.kubernetes` for cross-skill consistency.

---

## Fast-Path Mode Behavior

In fast-path mode (< 5 apps, no Private Spaces, no Kafka), this question is still presented — it is not skipped. Kubernetes preference cannot be safely inferred and affects the entire compute architecture.
