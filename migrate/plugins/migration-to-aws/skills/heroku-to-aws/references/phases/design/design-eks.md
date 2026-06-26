# EKS Design Branch

**Applies when:** `preferences.json → design_constraints.kubernetes` is `"eks-managed"` or `"eks-or-ecs"`.

**Skip when:** `design_constraints.kubernetes` is `"ecs-fargate"` or absent → use existing Fargate path (dyno-type-table.md).

---

## EKS Branch Logic

When the Kubernetes preference indicates EKS:

1. **For EACH formation resource** in the inventory:
   - Look up dyno type in `design-refs/eks-mapping-table.md`
   - Produce an EKS Deployment entry with pod resource requests and limits
   - Set `aws_service: "EKS"` 
   - Preserve dyno quantity as `replicas` (0–100)
   - If process type is `web` → include Kubernetes Service (type: LoadBalancer) with AWS LB Controller annotations
   - If process type is NOT `web` → Deployment only (no Service)

2. **Produce single EKS cluster entry:**
   - `cluster_name`: `"heroku-migration-cluster"`
   - `kubernetes_version`: `"1.30"`
   - Node group type based on preference:
     - `"eks-managed"` → `"self-managed"` node groups (more control)
     - `"eks-or-ecs"` → `"managed"` node groups (less operational burden)
   - Addons: `["vpc-cni", "coredns", "kube-proxy", "aws-load-balancer-controller"]`

3. **Node group sizing:**
   - Aggregate total pod CPU/memory requests across all formations
   - Select instance type using **largest-pod-class-wins** rule: pick the recommended node type for the largest dyno type present in the inventory. This ensures all pods can schedule (smaller pods fit on larger nodes, but not vice versa).
   - If formations span multiple size classes (e.g., standard-1x web + performance-l workers), use the node type recommended for the largest class. All pods from smaller classes will fit on those nodes with room to spare.
   - Calculate: min_size = 2 (HA), max_size = ceil(total_pods / 4) + 2, desired_size = ceil(total_pods / 4)
   - System overhead per node: 500m CPU, 512Mi memory

4. **Non-formation resources unchanged:**
   - Postgres → RDS/Aurora (existing path)
   - Redis → ElastiCache (existing path)
   - Kafka → MSK (existing path)
   - Add-ons → Fast-Path Table (existing path)

---

## All-or-Nothing Rule

When EKS is selected, ALL formation-type resources map to EKS. No mixing of Fargate and EKS for formations within the same migration. This avoids operational complexity of two container orchestrators.

---

## EKS Service Entry in aws-design.json

```json
{
  "service_id": "eks:<heroku-app>:<process-type>",
  "source_resource_id": "formation:<heroku-app>:<process-type>",
  "heroku_app": "<heroku-app>",
  "aws_service": "EKS",
  "confidence": "deterministic",
  "aws_config": {
    "region": "<target-region>",
    "cluster_name": "heroku-migration-cluster",
    "namespace": "<heroku-app>",
    "deployment_name": "<process-type>",
    "replicas": <quantity>,
    "container_image": "placeholder:<heroku-app>-<process-type>",
    "process_type": "<process-type>",
    "resources": {
      "requests": { "cpu": "<from-table>", "memory": "<from-table>" },
      "limits": { "cpu": "<from-table>", "memory": "<from-table>" }
    },
    "load_balancer": <true if web, false otherwise>,
    "node_group_type": "<managed|self-managed>"
  }
}
```

## EKS Cluster Entry in aws-design.json

```json
{
  "eks_cluster": {
    "cluster_name": "heroku-migration-cluster",
    "kubernetes_version": "1.30",
    "node_group_type": "<managed|self-managed>",
    "node_groups": [
      {
        "name": "general",
        "instance_types": ["<recommended-from-table>"],
        "min_size": 2,
        "max_size": <calculated>,
        "desired_size": <calculated>
      }
    ],
    "addons": ["vpc-cni", "coredns", "kube-proxy", "aws-load-balancer-controller"]
  }
}
```

## Error Handling

- **Unrecognized dyno type**: Same rejection as Fargate path — halt with error message naming the unsupported type
- **Empty Procfile**: Same rejection as Fargate path — at least one process type required
- **Node sizing overflow**: If no single instance type fits the aggregate, use the largest recommended type and increase node count
