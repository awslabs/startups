# EKS Generate Phase

**Applies when:** `aws-design.json` contains `aws_service: "EKS"` for one or more services.

**Skip when:** No EKS services in design → existing Fargate generation path applies.

---

## Generated Artifacts

### 1. `terraform/eks.tf`

Generate EKS cluster Terraform:

```hcl
# EKS Cluster
resource "aws_eks_cluster" "main" {
  name     = "<cluster_name>"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "<kubernetes_version>"

  vpc_config {
    subnet_ids         = [<subnet references from VPC design>]
    security_group_ids = [aws_security_group.eks_cluster.id]
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
  ]
}

# IAM Role for EKS Cluster
resource "aws_iam_role" "eks_cluster" {
  name = "<cluster_name>-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

# IAM Role for Node Group
resource "aws_iam_role" "eks_nodes" {
  name = "<cluster_name>-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_container_registry" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# Managed Node Group (when node_group_type = "managed")
resource "aws_eks_node_group" "general" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "general"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = [<subnet references>]

  instance_types = [<from design>]

  scaling_config {
    desired_size = <from design>
    max_size     = <from design>
    min_size     = <from design>
  }
}

# OIDC Provider for IRSA
data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

# AWS Load Balancer Controller
resource "helm_release" "aws_lb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"
  version    = "1.8.0"

  set {
    name  = "clusterName"
    value = aws_eks_cluster.main.name
  }

  set {
    name  = "serviceAccount.create"
    value = "true"
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.aws_lb_controller.arn
  }
}

# Security Group for EKS cluster
resource "aws_security_group" "eks_cluster" {
  name_prefix = "<cluster_name>-cluster-"
  vpc_id      = <vpc_id reference>

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

**If data stores exist in the design**, add security group rules for pod-to-service communication:
- Pod → RDS: port 5432
- Pod → ElastiCache: port 6379
- Pod → MSK: port 9092

### 2. `kubernetes/` Directory

Generate Kubernetes manifests:

**`kubernetes/namespace.yaml`** (one per unique heroku_app):
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: <heroku-app-name>
  labels:
    app.kubernetes.io/managed-by: heroku-migration
```

**`kubernetes/<app>-<process-type>-deployment.yaml`** (one per formation):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <process-type>
  namespace: <heroku-app-name>
  labels:
    app: <process-type>
    app.kubernetes.io/name: <process-type>
    app.kubernetes.io/part-of: <heroku-app-name>
spec:
  replicas: <quantity>
  selector:
    matchLabels:
      app: <process-type>
  template:
    metadata:
      labels:
        app: <process-type>
    spec:
      containers:
      - name: <process-type>
        image: <placeholder-image>
        resources:
          requests:
            cpu: "<from-eks-mapping-table>"
            memory: "<from-eks-mapping-table>"
          limits:
            cpu: "<from-eks-mapping-table>"
            memory: "<from-eks-mapping-table>"
        ports:
        - containerPort: <app-port>  # Only for web processes
```

**`kubernetes/<app>-web-service.yaml`** (only for web process types):
```yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: <heroku-app-name>
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "external"
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: "ip"
    service.beta.kubernetes.io/aws-load-balancer-scheme: "internet-facing"
spec:
  type: LoadBalancer
  selector:
    app: web
  ports:
  - port: 80
    targetPort: <app-port>
    protocol: TCP
```

### 3. MIGRATION_GUIDE.md — EKS Sections

Add these sections after Prerequisites, before Data Migration:

```markdown
## EKS Cluster Setup

1. Apply EKS Terraform:
   ```bash
   cd terraform/
   terraform init
   terraform apply
   ```

2. Configure kubectl access:
   ```bash
   aws eks update-kubeconfig --name heroku-migration-cluster --region <region>
   ```

3. Verify node group readiness:
   ```bash
   kubectl get nodes
   # All nodes should show STATUS: Ready
   ```

4. Verify AWS Load Balancer Controller:
   ```bash
   kubectl get deployment -n kube-system aws-load-balancer-controller
   # Should show AVAILABLE: 1+
   ```

## Deploy Workloads to EKS

1. Create namespace:
   ```bash
   kubectl apply -f kubernetes/namespace.yaml
   ```

2. Deploy all workloads:
   ```bash
   kubectl apply -f kubernetes/
   ```

3. Verify pods are running:
   ```bash
   kubectl get pods -n <namespace>
   # All pods should show STATUS: Running
   ```

4. Verify load balancer (web services):
   ```bash
   kubectl get svc -n <namespace>
   # EXTERNAL-IP should be provisioned within 2–5 minutes
   ```

## Configure Pod-to-Service Access

> Include this section ONLY when EKS services coexist with data stores (RDS, ElastiCache, MSK).

1. **IAM Roles for Service Accounts (IRSA):**
   ```bash
   # The OIDC provider was created by Terraform. Create a service account:
   kubectl create serviceaccount <app>-sa -n <namespace>
   kubectl annotate serviceaccount <app>-sa -n <namespace> \
     eks.amazonaws.com/role-arn=arn:aws:iam::<account>:role/<app>-pod-role
   ```

2. **Verify security group rules** (created by Terraform):
   - Pods → RDS on port 5432
   - Pods → ElastiCache on port 6379
   - Pods → MSK on port 9092

3. **Store connection strings in Kubernetes Secrets:**
   ```bash
   kubectl create secret generic db-credentials -n <namespace> \
     --from-literal=DATABASE_URL='postgres://user:pass@rds-endpoint:5432/db'
   ```

4. **Reference secrets in Deployments** (update container env):
   ```yaml
   env:
   - name: DATABASE_URL
     valueFrom:
       secretKeyRef:
         name: db-credentials
         key: DATABASE_URL
   ```
```

**Omit all EKS sections** when the design contains only Fargate services.

---

## Terraform Validation

After generating `eks.tf`, the combined Terraform in `terraform/` must pass `terraform validate`. If validation fails, log the error to `generation-warnings.json` and continue.

## Helm Provider Requirement

When `eks.tf` is generated, add the Helm provider to `main.tf`:

```hcl
terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }
}

provider "helm" {
  kubernetes {
    host                   = aws_eks_cluster.main.endpoint
    cluster_ca_certificate = base64decode(aws_eks_cluster.main.certificate_authority[0].data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      args        = ["eks", "get-token", "--cluster-name", aws_eks_cluster.main.name]
      command     = "aws"
    }
  }
}
```
