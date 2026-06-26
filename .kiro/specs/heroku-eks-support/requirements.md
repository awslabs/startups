# Requirements Document

## Introduction

This document specifies the requirements for adding EKS (Elastic Kubernetes Service) support to the existing `heroku-to-aws` migration skill. Currently, the Heroku skill maps all Dynos exclusively to AWS Fargate. The sibling `gcp-to-aws` skill already supports EKS as a compute target via a Kubernetes preference question and a design rubric that consumes that preference. This feature adds an equivalent mechanism to the Heroku skill: a Clarify-phase question asking about Kubernetes preference, a Design-phase EKS branch that maps dyno types to EKS pod resource requests/limits, a Generate-phase EKS Terraform output (cluster, node groups, Kubernetes manifests), and updated property tests allowing EKS as a valid `aws_service` value when the user explicitly selects it.

**Compatibility note:** The existing Heroku skill philosophy states "no EB, no App Runner" but does not exclude EKS. Property test 22 validates no EB/App Runner/ECS Express Mode but does not exclude EKS, so the architecture is compatible with this addition.

## Glossary

- **Skill**: A self-contained migration workflow module within the migration-to-aws plugin that handles a specific source platform
- **Clarify_Engine**: The component that presents adaptive questions to gather migration preferences before design begins
- **Design_Engine**: The component that maps Heroku resources to AWS services and produces the architecture design artifact
- **Generate_Engine**: The component that produces Terraform configurations, migration scripts, and documentation
- **EKS**: Amazon Elastic Kubernetes Service — a managed Kubernetes control plane on AWS
- **EKS_Managed_Node_Group**: An EC2 Auto Scaling group of worker nodes managed by EKS that runs Kubernetes pods
- **Pod_Resource_Request**: The minimum CPU and memory a Kubernetes pod requires to be scheduled on a node
- **Pod_Resource_Limit**: The maximum CPU and memory a Kubernetes pod is allowed to consume before throttling or OOM-kill
- **Dyno_Type_Table**: The existing lookup table mapping Heroku dyno types to CPU/memory specifications (currently outputs Fargate task sizes)
- **EKS_Mapping_Table**: A new lookup table mapping Heroku dyno types to Kubernetes pod resource requests and limits
- **Kubernetes_Preference**: A user-expressed preference stored in `preferences.json` under `design_constraints.kubernetes` that determines whether compute workloads target EKS or ECS Fargate
- **Fast_Path_Table**: The existing deterministic lookup table mapping Heroku add-ons to AWS services
- **Specialist_Gate**: The existing deferral mechanism for resources requiring expert engagement
- **Migration_Dir**: The run-specific directory under `.migration/` storing all artifacts for a single migration session
- **Helm_Chart**: A package format for Kubernetes applications that bundles manifests, templates, and configuration values

## Requirements

### Requirement 1: Clarify Phase — Kubernetes Preference Question

**User Story:** As a migration user with Kubernetes experience, I want the skill to ask whether I prefer EKS or ECS Fargate for my containerized workloads, so that the migration targets the compute platform that best fits my team's expertise.

#### Acceptance Criteria

1. THE Clarify_Engine SHALL present a Kubernetes preference question with the following framing: "Would you prefer EKS (Kubernetes) or ECS Fargate for your containerized workloads?"
2. THE Clarify_Engine SHALL offer exactly four answer options for the Kubernetes preference question: A) EKS preferred — team has Kubernetes expertise and wants to manage clusters, B) EKS acceptable — team can operate Kubernetes but prefers managed node groups to reduce burden, C) ECS Fargate preferred — team wants simplest managed containers without Kubernetes overhead (default), D) I don't know
3. WHEN the user selects option A, THE Clarify_Engine SHALL write `design_constraints.kubernetes: "eks-managed"` to `preferences.json`
4. WHEN the user selects option B, THE Clarify_Engine SHALL write `design_constraints.kubernetes: "eks-or-ecs"` to `preferences.json`
5. WHEN the user selects option C or option D, THE Clarify_Engine SHALL write `design_constraints.kubernetes: "ecs-fargate"` to `preferences.json`
6. WHEN the user does not answer the Kubernetes preference question and defaults are applied, THE Clarify_Engine SHALL write `design_constraints.kubernetes: "ecs-fargate"` to `preferences.json` with `source: "default"`
7. THE Clarify_Engine SHALL present the Kubernetes preference question in Batch 3 (Operational) alongside the existing containerization status question, incrementing the maximum question count from 15 to 16

### Requirement 2: Design Phase — EKS Compute Branch

**User Story:** As a migration user who selected EKS, I want my Heroku dynos mapped to appropriately-sized EKS pods with resource requests and limits, so that my compute workloads run on equivalent Kubernetes capacity.

#### Acceptance Criteria

1. WHEN `preferences.json` contains `design_constraints.kubernetes` set to `"eks-managed"` or `"eks-or-ecs"`, THE Design_Engine SHALL map each Heroku Formation (dyno process type) to an EKS Deployment with pod resource requests and limits instead of a Fargate task definition
2. THE Design_Engine SHALL use the EKS_Mapping_Table to translate Heroku dyno types (standard-1x, standard-2x, performance-m, performance-l, private-s, private-m, private-l) to Kubernetes pod resource requests (cpu, memory) and resource limits (cpu, memory)
3. WHEN `design_constraints.kubernetes` is `"eks-managed"`, THE Design_Engine SHALL include a self-managed node group configuration in the EKS cluster design with instance types sized to accommodate the aggregate pod resource requests across all formations
4. WHEN `design_constraints.kubernetes` is `"eks-or-ecs"`, THE Design_Engine SHALL include a managed node group configuration in the EKS cluster design, selecting instance types that accommodate pod resource requests while minimizing operational complexity
5. THE Design_Engine SHALL set `aws_service` to `"EKS"` in the `aws-design.json` services array for each formation mapped to EKS
6. THE Design_Engine SHALL preserve the dyno quantity as the Kubernetes Deployment `replicas` value, accepting values from 0 to 100 inclusive
7. WHEN a Procfile declares a `web` process type and EKS is selected, THE Design_Engine SHALL include a Kubernetes Service of type LoadBalancer backed by an Application Load Balancer in the design for that Deployment
8. WHEN a Procfile declares a process type whose name is not `web` and EKS is selected, THE Design_Engine SHALL design that process type as a Kubernetes Deployment without a Service of type LoadBalancer
9. IF a dyno type is not present in the EKS_Mapping_Table, THEN THE Design_Engine SHALL reject the mapping and report an error message indicating the unsupported dyno type name
10. WHEN `preferences.json` does not contain `design_constraints.kubernetes` or it is set to `"ecs-fargate"`, THE Design_Engine SHALL continue to map formations to Fargate task definitions using the existing Dyno_Type_Table

### Requirement 3: EKS Mapping Table

**User Story:** As a plugin developer, I want a deterministic lookup table that converts Heroku dyno types to Kubernetes pod resource specifications, so that EKS sizing is consistent and predictable.

#### Acceptance Criteria

1. THE EKS_Mapping_Table SHALL define pod resource requests and limits for all seven recognized Heroku dyno types: standard-1x, standard-2x, performance-m, performance-l, private-s, private-m, private-l
2. THE EKS_Mapping_Table SHALL specify resource requests with cpu in millicores and memory in MiB for each dyno type, where the request values are equal to or greater than the dyno's documented capacity
3. THE EKS_Mapping_Table SHALL specify resource limits with cpu in millicores and memory in MiB for each dyno type, where limits are set to 2x the request value for cpu (to allow bursting) and 1x the request value for memory (to prevent OOM from over-allocation)
4. THE EKS_Mapping_Table SHALL recommend a node instance type for each dyno type that can accommodate at least 4 pods of that type on a single node, accounting for Kubernetes system overhead (kubelet, kube-proxy, AWS VPC CNI)
5. THE EKS_Mapping_Table SHALL use exact case-insensitive matching for dyno type lookup, consistent with the existing Dyno_Type_Table behavior

### Requirement 4: Generate Phase — EKS Terraform Output

**User Story:** As a migration user who selected EKS, I want production-ready Terraform for the EKS cluster and Kubernetes manifests for my workloads, so that I can deploy my migrated applications to Kubernetes.

#### Acceptance Criteria

1. WHEN the design contains `aws_service: "EKS"` for one or more services, THE Generate_Engine SHALL produce an `eks.tf` file in the `terraform/` directory within the Migration_Dir containing the EKS cluster resource, IAM roles for the cluster and node groups, and the selected node group configuration (managed or self-managed based on the kubernetes preference)
2. WHEN the design contains `aws_service: "EKS"` for one or more services, THE Generate_Engine SHALL produce a `kubernetes/` directory within the Migration_Dir containing one Kubernetes Deployment manifest per formation, with container resource requests and limits matching the EKS_Mapping_Table values
3. WHEN a web process type is mapped to EKS, THE Generate_Engine SHALL produce a Kubernetes Service manifest of type LoadBalancer with AWS Load Balancer Controller annotations targeting an Application Load Balancer
4. THE Generate_Engine SHALL produce a Kubernetes Namespace manifest that groups all migrated workloads into a single namespace named after the Heroku app
5. THE Generate_Engine SHALL include in the generated EKS Terraform: VPC integration (referencing the existing VPC design from the skill — either existing VPC or newly generated VPC), security group rules for node-to-pod and pod-to-RDS/ElastiCache communication, and OIDC provider configuration for IAM Roles for Service Accounts
6. WHEN the EKS cluster Terraform is generated, THE Generate_Engine SHALL include the AWS Load Balancer Controller add-on as a Helm release resource in the Terraform configuration
7. THE Generate_Engine SHALL ensure all generated EKS Terraform passes `terraform validate` without errors
8. IF the design contains a mix of EKS services and non-EKS services (e.g., RDS, ElastiCache), THE Generate_Engine SHALL produce both `eks.tf` and the existing service-specific Terraform files, with security group rules allowing pod-to-service communication

### Requirement 5: Generate Phase — EKS Migration Guide Content

**User Story:** As a migration user who selected EKS, I want the MIGRATION_GUIDE.md to include EKS-specific deployment instructions, so that I know how to deploy my workloads to the cluster.

#### Acceptance Criteria

1. WHEN the design contains `aws_service: "EKS"` services, THE Generate_Engine SHALL include an "EKS Cluster Setup" section in the MIGRATION_GUIDE.md with instructions for: applying the EKS Terraform, configuring `kubectl` access via `aws eks update-kubeconfig`, verifying node group readiness, and installing the AWS Load Balancer Controller
2. WHEN the design contains `aws_service: "EKS"` services, THE Generate_Engine SHALL include a "Deploy Workloads to EKS" section in the MIGRATION_GUIDE.md with instructions for: applying Kubernetes manifests via `kubectl apply`, verifying pod scheduling and readiness, and confirming load balancer provisioning for web services
3. WHEN the design contains EKS services alongside data stores (RDS, ElastiCache, MSK), THE Generate_Engine SHALL include a "Configure Pod-to-Service Access" section documenting IAM Roles for Service Accounts setup, security group rules, and connection string configuration via Kubernetes Secrets or external-secrets-operator
4. THE Generate_Engine SHALL omit the EKS-specific sections from the MIGRATION_GUIDE.md when the design contains only Fargate services and no EKS services

### Requirement 6: Property Test Update — EKS as Valid aws_service

**User Story:** As a plugin developer, I want the property tests to accept EKS as a valid `aws_service` value when the user explicitly selects Kubernetes, so that the test suite validates the new compute path without false failures.

#### Acceptance Criteria

1. WHEN `preferences.json` contains `design_constraints.kubernetes` set to `"eks-managed"` or `"eks-or-ecs"`, THE property tests SHALL accept `"EKS"` as a valid `aws_service` value for formation-type resources in the `aws-design.json` services array
2. WHEN `preferences.json` does not contain `design_constraints.kubernetes` or it is set to `"ecs-fargate"`, THE property tests SHALL NOT accept `"EKS"` as a valid `aws_service` value for formation-type resources, enforcing that EKS only appears when explicitly selected
3. THE property tests SHALL continue to reject `"Elastic Beanstalk"`, `"App Runner"`, and `"ECS Express Mode"` as `aws_service` values regardless of any preference setting
4. THE property tests SHALL validate that when EKS is selected, every formation-type resource in `aws-design.json` uses `aws_service: "EKS"` (no mixing of EKS and Fargate for formation resources within the same migration)
5. THE property tests SHALL validate that the EKS_Mapping_Table produces pod resource requests where cpu (millicores) and memory (MiB) meet or exceed the dyno type's documented capacity for all seven recognized dyno types

### Requirement 7: Design Consistency — EKS Selection is All-or-Nothing for Formations

**User Story:** As a migration user, I want EKS selection to apply uniformly to all my dyno formations, so that I don't end up with a split compute architecture that is harder to operate.

#### Acceptance Criteria

1. WHEN `design_constraints.kubernetes` is set to `"eks-managed"` or `"eks-or-ecs"`, THE Design_Engine SHALL map ALL formation-type resources in the inventory to EKS, not a subset
2. THE Design_Engine SHALL NOT produce a design where some formations use `aws_service: "Fargate"` and others use `aws_service: "EKS"` within the same migration run
3. WHEN EKS is selected, THE Design_Engine SHALL design a single EKS cluster that hosts all formation workloads, rather than creating multiple clusters
4. THE Design_Engine SHALL continue to map non-formation resources (Postgres, Redis, Kafka, add-ons) to their existing AWS targets (RDS, ElastiCache, MSK, Fast-Path Table) regardless of the Kubernetes preference — EKS selection applies only to compute (formation) resources
