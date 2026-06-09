# EC2
## Process

## Instance Type Selection

Follow this decision tree:

- **General purpose (M family)**: Default choice. M7i, M7g (Graviton, 20-30% better price-performance), M7a (AMD).
- **Compute optimized (C family)**: CPU-bound workloads -- batch processing, media encoding, HPC, ML inference. C7g for best price-performance.
- **Memory optimized (R/X family)**: In-memory databases, large caches, real-time analytics. R7g for most cases, X2idn for extreme memory (up to 4 TB).
- **Storage optimized (I/D family)**: High sequential I/O, data warehousing, distributed file systems. I4i for NVMe, D3 for dense HDD.
- **Accelerated (P/G/Inf/Trn family)**: P5 for ML training, G5 for graphics/inference, Inf2 for cost-efficient inference, Trn1 for training on Trainium.

**Always prefer Graviton (arm64)** unless the workload requires x86. Graviton instances (suffix `g`) deliver 20-30% better price-performance.

**Right-sizing**: Start with CloudWatch metrics or Compute Optimizer recommendations. Target 40-70% average CPU utilization. If consistently below 40%, downsize.

## Launch Templates

- **Always use launch templates**, never launch configurations (deprecated).
- Pin the AMI ID in the template. Use SSM Parameter Store to resolve the latest AMI at deploy time:
  ```
  /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64
  ```
- Set `InstanceInitiatedShutdownBehavior: terminate` for ephemeral workloads.
- Use `MetadataOptions` to enforce IMDSv2: `HttpTokens: required`, `HttpPutResponseHopLimit: 1`.
- Configure `TagSpecifications` to tag instances, volumes, and ENIs at launch for cost allocation.
- Use launch template **versions** and set the ASG to `$Latest` or `$Default` to control rollouts.

## Auto Scaling Groups

- **Target tracking** is the right default: scale on `ASGAverageCPUUtilization` at 60-70%.
- For request-driven workloads, use `ALBRequestCountPerTarget`.
- **Predictive scaling**: Enable for workloads with predictable daily/weekly patterns. It pre-provisions capacity 5-10 minutes ahead.
- Use **mixed instances policy** with multiple instance types (same family, different sizes) to improve Spot availability and reduce costs.
- Set `HealthCheckType: ELB` when behind a load balancer (default is EC2, which only catches instance failures).
- Configure `DefaultInstanceWarmup` (e.g., 300s) to prevent premature scale-in while instances are still warming up.
- Use **instance refresh** for AMI updates: `MinHealthyPercentage: 90`, `InstanceWarmup: 300`.

## Spot Instances

Use Spot for fault-tolerant, stateless, or flexible-schedule workloads. Up to 90% savings.

- **Spot Fleet / Mixed Instances Policy**: Diversify across at least 6-10 instance types and all AZs. The broader the pool, the lower the interruption rate.
- **Allocation strategy**: `capacity-optimized` (default, best for reducing interruptions) or `price-capacity-optimized` (balances price and capacity). Avoid `lowest-price` — it concentrates instances on the cheapest instance type in a single pool, which means higher interruption rates (AWS reclaims the cheapest capacity first) and lower fleet diversity. The few cents saved per hour are wiped out by the disruption cost of frequent interruptions.
- **Spot interruption handling**: Use EC2 metadata service or EventBridge to catch the 2-minute warning. Drain connections and save state.
- **Spot placement score**: Use `aws ec2 get-spot-placement-scores` to find regions/AZs with best capacity before launching.
- **Spot with ASG**: Use mixed instances policy with `OnDemandBaseCapacity: 1` or `2` and `SpotAllocationStrategy: capacity-optimized` for a baseline of on-demand with Spot overflow.
- Never use Spot for: databases, single-instance workloads, or anything that cannot tolerate interruption.

## Placement Groups

- **Cluster**: Low-latency, high-throughput between instances (HPC, tightly coupled). Same AZ, same rack.
- **Spread**: Maximum resilience. Each instance on distinct hardware. Max 7 per AZ. Use for small critical workloads.
- **Partition**: Large distributed workloads (HDFS, Cassandra, Kafka). Instances in same partition share hardware, different partitions don't.

## Storage: EBS vs Instance Store

**Default to EBS** unless you need maximum IOPS.

### Instance Store
- Ephemeral NVMe attached to the host. Data lost on stop/terminate/hardware failure.
- Use for: caches, buffers, scratch data, temporary storage. I4i instances deliver up to 2.5M IOPS.
- Never store data you cannot afford to lose.

## Output Format

| Field | Details |
|-------|---------|
| **Instance type** | Family, size, and architecture (e.g., m7g.large / arm64) |
| **AMI** | AMI source (AL2023, custom), resolution method (SSM parameter) |
| **Storage (EBS type/size)** | Volume type (gp3, io2), size, IOPS, throughput |
| **ASG config** | Min/max/desired, health check type, instance warmup |
| **Spot strategy** | On-demand base capacity, Spot allocation strategy, instance diversity |
| **Key pair / SSM** | SSM Session Manager (preferred) or key pair for access |
| **Security group** | Inbound/outbound rules, referenced SG IDs |
| **Monitoring** | CloudWatch agent config, detailed monitoring, custom metrics |

## Anti-Patterns

- **Using SSH keys**: Use SSM Session Manager instead. No need to manage key pairs, open port 22, or maintain bastion hosts. SSM provides audit logging and IAM-based access control.
- **IMDSv1 still enabled**: Enforce IMDSv2 (`HttpTokens: required`) in launch templates. IMDSv1 is vulnerable to SSRF attacks that can steal instance credentials.
- **Manually launching instances**: Everything should go through launch templates and ASGs, even "temporary" instances. Manual instances become untracked snowflakes.
- **Single instance type in ASG**: Use mixed instances policy with 3+ instance types from the same family. This improves Spot availability and on-demand capacity during shortages.
- **gp2 volumes**: gp2 ties IOPS to volume size. gp3 is cheaper, with independently configurable IOPS and throughput. Migrate all gp2 volumes to gp3.
- **Oversized instances**: Running m5.4xlarge at 5% CPU because "we might need it." Use Compute Optimizer, right-size, and scale horizontally instead.
- **No EBS encryption**: Enable default encryption at the account level. There is no performance penalty on current generation instances and it satisfies most compliance requirements.
- **Using public IPs when not needed**: Place instances in private subnets behind a load balancer or NAT Gateway. Use VPC endpoints for AWS service access.
- **Ignoring Graviton**: Arm64 (Graviton) instances are 20-30% better price-performance for most workloads. Test compatibility and migrate -- most Linux workloads run without changes.
