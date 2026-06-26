# Implementation Plan: Heroku EKS Support

## Overview

Add EKS as an alternative compute target in the `heroku-to-aws` migration skill. When a user explicitly selects Kubernetes preference during Clarify, all dyno formations map to EKS Deployments with pod resource requests/limits instead of Fargate task definitions. The Generate phase emits EKS Terraform (cluster, node groups, IAM, LB Controller) and Kubernetes manifests (Deployments, Services, Namespace). This mirrors the existing GCP skill's EKS support pattern.

## Tasks

-
  1. [ ] Clarify phase — Kubernetes preference question
  - [ ] 1.1 Add Kubernetes preference question to clarify.md
    - Add Q12 to Batch 3 (Operational) in `references/phases/clarify/clarify.md`
    - Define 4 answer options: A) EKS preferred (K8s expert), B) EKS acceptable (managed node groups), C) ECS Fargate preferred (default), D) I don't know
    - Implement interpretation: A → `"eks-managed"`, B → `"eks-or-ecs"`, C/D → `"ecs-fargate"`
    - Set default to `"ecs-fargate"` with `source: "default"` when unanswered
    - Ensure question fires always (not conditional on inventory content)
    - Update question count documentation: full mode now supports 12–16 questions (was 12–15)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ] 1.2 Update preferences.json schema for design_constraints.kubernetes
    - Add `design_constraints` section to preferences.json output schema in clarify.md
    - Add `kubernetes` field accepting values: `"eks-managed"`, `"eks-or-ecs"`, `"ecs-fargate"`
    - Ensure field name matches GCP skill's `design_constraints.kubernetes` for consistency
    - Update fast-path mode defaults to include `kubernetes: "ecs-fargate"`
    - _Requirements: 1.3, 1.4, 1.5, 1.6_

-
  2. [ ] Design phase — EKS mapping table and branch
  - [x] 2.1 Create EKS mapping table (`design-refs/eks-mapping-table.md`)
    - Create `references/design-refs/eks-mapping-table.md` in the Heroku skill directory
    - Define pod resource requests (cpu millicores, memory MiB) for all 7 dyno types: standard-1x, standard-2x, performance-m, performance-l, private-s, private-m, private-l
    - Define pod resource limits: cpu = 2x request, memory = 1x request
    - Define recommended node instance type per dyno type (must fit ≥4 pods + 500m/512Mi system overhead)
    - Document matching rules: exact case-insensitive, error on unknown types
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 2.2 Add EKS branch to design engine (`design.md`)
    - Modify `references/phases/design/design.md` to add EKS branch
    - Add check: if `preferences.json → design_constraints.kubernetes` is `"eks-managed"` or `"eks-or-ecs"`, route formations to EKS mapping
    - Implement EKS_Mapping_Table lookup for each formation → produce EKS Deployment entry with pod requests/limits
    - Set `aws_service: "EKS"` for all formation entries when EKS selected
    - Preserve dyno quantity as `replicas` (0–100)
    - Include LoadBalancer Service for web process types, no Service for non-web
    - Add single EKS cluster entry to design: cluster name, kubernetes version, node group type, addons
    - Implement node group type selection: `"eks-managed"` → self-managed, `"eks-or-ecs"` → managed
    - Implement node group sizing: aggregate pod requests → select instance type → calculate min/max nodes
    - Ensure non-formation resources (Postgres, Redis, Kafka, add-ons) use existing mapping paths unchanged
    - Handle unrecognized dyno type: same rejection error as Fargate path
    - Ensure Fargate path remains default when `kubernetes` is `"ecs-fargate"` or absent
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 7.1, 7.2, 7.3, 7.4_

-
  3. [ ] Generate phase — EKS Terraform and Kubernetes manifests
  - [ ] 3.1 Implement EKS Terraform generation (`generate-terraform.md`)
    - Modify `references/phases/generate/generate-terraform.md` to add EKS generation logic
    - Generate `eks.tf` containing: `aws_eks_cluster`, `aws_iam_role` (cluster + nodes), `aws_iam_openid_connect_provider` (OIDC for IRSA)
    - Generate node group: `aws_eks_node_group` (managed) or `aws_autoscaling_group` + `aws_launch_template` (self-managed) based on design
    - Generate `helm_release` for AWS Load Balancer Controller addon
    - Include VPC integration: reference VPC design (existing VPC data source or new VPC from skill's VPC generation)
    - Include security group rules: node-to-pod communication, pod-to-RDS (5432), pod-to-ElastiCache (6379), pod-to-MSK (9092) when those services exist in design
    - Ensure generated Terraform passes `terraform validate`
    - _Requirements: 4.1, 4.5, 4.6, 4.7, 4.8_

  - [ ] 3.2 Implement Kubernetes manifest generation
    - Create manifest generation logic (can be in `generate-terraform.md` or separate `generate-kubernetes.md`)
    - Generate `kubernetes/namespace.yaml` — one Namespace per unique `heroku_app` in design
    - Generate `kubernetes/<app>-<process-type>-deployment.yaml` per formation: Deployment with replicas, container image placeholder, resource requests/limits from design
    - Generate `kubernetes/<app>-<process-type>-service.yaml` for web process types only: Service type LoadBalancer with AWS LB Controller annotations
    - Ensure manifests reference correct namespace, labels, and selectors
    - _Requirements: 4.2, 4.3, 4.4_

  - [ ] 3.3 Add EKS sections to MIGRATION_GUIDE.md (`generate-docs.md`)
    - Modify `references/phases/generate/generate-docs.md` to add EKS guide sections
    - Add "EKS Cluster Setup" section: terraform apply, aws eks update-kubeconfig, verify nodes, verify LB Controller
    - Add "Deploy Workloads to EKS" section: kubectl apply namespace, kubectl apply manifests, verify pods, verify LB
    - Add "Configure Pod-to-Service Access" section (when EKS + data stores): IRSA setup, security groups, connection strings via K8s Secrets
    - Ensure EKS sections are omitted when design contains only Fargate services
    - Insert EKS sections after Prerequisites, before Data Migration procedures
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

-
  4. [ ] Property tests
  - [ ] 4.1 Write Property 23: EKS mapping preserves dyno specifications
    - Generate random formations with recognized dyno types × kubernetes preference ∈ {"eks-managed", "eks-or-ecs"}
    - Assert: pod request cpu ≥ dyno CPU share, request memory = dyno memory, limit cpu = 2x request, limit memory = request
    - Assert: replicas = source quantity (0–100), LoadBalancer Service iff web, aws_service = "EKS" for all formations
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 2.8, 3.2, 3.3_

  - [ ] 4.2 Write Property 24: EKS selection is all-or-nothing for formations
    - Generate random inventories (1–10 formations, 0–5 add-ons) × kubernetes preference ∈ {"eks-managed", "eks-or-ecs"}
    - Assert: every formation has aws_service "EKS", no formation has "Fargate"
    - Assert: non-formation resources retain existing targets (RDS, ElastiCache, MSK)
    - Assert: exactly one eks_cluster entry, node group type matches preference
    - _Requirements: 2.3, 2.4, 7.1, 7.2, 7.3, 7.4_

  - [ ] 4.3 Modify Property 22: No EB/App Runner — EKS conditionally valid
    - Update existing property test to accept "EKS" as valid aws_service for formations ONLY when design_constraints.kubernetes is "eks-managed" or "eks-or-ecs"
    - Continue rejecting "Elastic Beanstalk", "App Runner", "ECS Express Mode" unconditionally
    - When kubernetes is "ecs-fargate" or absent, reject "EKS" for formation resources
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 4.4 Write Property 25: Kubernetes preference question fires and defaults correctly
    - Generate random inventories (fast-path and full mode)
    - Assert: kubernetes preference question always presented
    - Assert: default is "ecs-fargate" with source "default"
    - Assert: A → "eks-managed", B → "eks-or-ecs", C/D → "ecs-fargate"
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6_

  - [ ] 4.5 Write Property 26: EKS Terraform generation matches design
    - Generate random EKS designs (1–10 formations, web/non-web mix, managed/self-managed)
    - Assert: eks.tf contains cluster, IAM roles, node group matching design type
    - Assert: kubernetes/ has one Deployment per formation, Service only for web, Namespace per app
    - Assert: pod resources in manifests match design aws_config.resources
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 4.6 Write Property 27: Migration guide EKS sections conditional on design
    - Generate random designs alternating Fargate-only vs EKS-containing
    - Assert: EKS design → "EKS Cluster Setup" and "Deploy Workloads" sections present
    - Assert: EKS + data stores → "Pod-to-Service Access" section present
    - Assert: Fargate-only → no EKS sections present
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

-
  5. [ ] Integration tests
  - [ ] 5.1 Write integration test for end-to-end EKS path
    - Mock inventory with 2+ formations → set kubernetes preference to "eks-managed"
    - Verify: design produces EKS entries for all formations
    - Verify: generate produces eks.tf + kubernetes/ manifests
    - Verify: MIGRATION_GUIDE.md includes EKS sections
    - _Requirements: 2.1, 4.1, 5.1_

  - [ ] 5.2 Write integration test for Fargate path unchanged
    - Mock inventory with formations → set kubernetes preference to "ecs-fargate" (or omit)
    - Verify: design produces Fargate entries (existing behavior)
    - Verify: no eks.tf or kubernetes/ directory generated
    - Verify: no EKS sections in MIGRATION_GUIDE.md
    - _Requirements: 2.10, 5.4_

  - [ ] 5.3 Write integration test for mixed resource types
    - Mock inventory with formations + Postgres + Redis → set kubernetes to "eks-or-ecs"
    - Verify: formations → EKS, Postgres → RDS, Redis → ElastiCache
    - Verify: both eks.tf and database.tf / elasticache.tf generated
    - Verify: security groups allow pod-to-service communication
    - _Requirements: 4.8, 7.4_

  - [ ] 5.4 Write integration test for EKS Terraform validation
    - Generate EKS Terraform from a representative design
    - Run `terraform validate` on generated output
    - Verify: no validation errors
    - _Requirements: 4.7_

-
  6. [ ] Final checkpoint
  - Ensure all property tests pass
  - Ensure all integration tests pass
  - Verify existing Fargate-path tests still pass (no regressions)
  - Verify Property 22 modification doesn't break existing test cases

## Notes

- Implementation language: JavaScript (ESM modules, Node.js built-in test runner, fast-check 3.22.0)
- Test files go in `migrate/plugins/migration-to-aws/tests/property/heroku/` and `migrate/plugins/migration-to-aws/tests/integration/heroku/`
- Skill reference files go in `migrate/plugins/migration-to-aws/skills/heroku-to-aws/references/`
- The EKS mapping table file goes in `references/design-refs/eks-mapping-table.md`
- Kubernetes manifest templates can be inline in generate-terraform.md or in a separate generate-kubernetes.md (developer's choice)
- The `design_constraints.kubernetes` field name intentionally matches the GCP skill for cross-skill consistency

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"] }
  ]
}
```
