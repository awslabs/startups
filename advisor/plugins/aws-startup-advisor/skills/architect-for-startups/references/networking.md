# Networking
## VPC Design Principles

### Subnet Tiers

Always design with three tiers:

- **Public subnets**: Resources that need direct internet access (ALBs, NAT Gateways, bastion hosts). Route table has 0.0.0.0/0 -> Internet Gateway.
- **Private subnets**: Application workloads (EC2, ECS, Lambda). Route table has 0.0.0.0/0 -> NAT Gateway. Can reach the internet but are not reachable from it.
- **Isolated subnets**: Databases and sensitive workloads. No route to the internet at all. Access AWS services only through VPC endpoints.

### Availability Zones

- Minimum 2 AZs for production. 3 AZs is the standard for high availability.
- Each tier gets one subnet per AZ (e.g., 3 AZs x 3 tiers = 9 subnets)

## Security Groups vs NACLs

| Feature    | Security Groups                      | NACLs                              |
|------------|--------------------------------------|------------------------------------|
| Level      | ENI (instance)                       | Subnet                             |
| State      | Stateful                             | Stateless                          |
| Rules      | Allow only                           | Allow and Deny                     |
| Evaluation | All rules evaluated                  | Rules evaluated in order by number |
| Default    | Deny all inbound, allow all outbound | Allow all inbound and outbound     |

**Opinionated guidance:**
- Security groups are your primary network control. Use them for everything.
- NACLs are defense-in-depth only. Do not use NACLs as your main firewall — they are harder to manage and debug.
- Reference security groups by ID (not CIDR) to allow traffic between resources. This is more maintainable and self-documenting.
- One security group per logical role (e.g., `alb-sg`, `app-sg`, `db-sg`). Chain them: ALB -> App -> DB.

## VPC Endpoints

### Gateway Endpoints (free)
- **S3** and **DynamoDB** only
- Added to route tables — no ENI, no security group
- Always create these — they are free (no hourly charge, no per-GB data processing fee), they keep S3/DynamoDB traffic on the AWS backbone instead of traversing NAT Gateways (which charge $0.045/GB processed), and they reduce latency by avoiding the extra hop through NAT. The only cost is a route table entry.

### Interface Endpoints (cost per hour + data)
- All other AWS services (STS, Secrets Manager, ECR, CloudWatch, KMS, etc.)
- Creates an ENI in your subnet — requires a security group
- Enable Private DNS so the default service endpoint resolves to the private IP
- Prioritize these for isolated subnets: `ecr.api`, `ecr.dkr`, `s3` (gateway), `logs`, `sts`, `secretsmanager`, `kms`

## Transit Gateway

Use Transit Gateway when:
- You have more than 2 VPCs that need to communicate
- You need hub-and-spoke or any-to-any connectivity
- You need centralized egress or ingress through a shared services VPC

Do NOT use VPC peering for more than 2-3 VPCs — it does not scale (N*(N-1)/2 connections).

Key Transit Gateway patterns:
- **Shared Services VPC**: Central VPC with DNS, logging, security tools. All spoke VPCs route through TGW.
- **Centralized Egress**: Single NAT Gateway in a shared VPC. All private subnets route 0.0.0.0/0 through TGW to the shared VPC.
- **Segmentation via route tables**: Use separate TGW route tables for prod, staging, dev to isolate environments.

## VPC Peering

- Point-to-point only. Not transitive — if A peers with B and B peers with C, A cannot reach C.
- Works cross-region and cross-account
- Good for 2-3 VPCs. Beyond that, use Transit Gateway.
- CIDRs must not overlap

## Route53

### Hosted Zones
- **Public hosted zone**: DNS for internet-facing resources. NS records must be registered with your domain registrar.
- **Private hosted zone**: DNS for internal resources. Associated with one or more VPCs. Not resolvable from the internet.

### Health Checks
- Always attach health checks to failover and latency records
- Health checks can monitor an endpoint, a CloudWatch alarm, or other health checks (calculated)
- Health check interval: 30s standard, 10s fast (costs more)

## NAT Gateway

- One per AZ for high availability. A single NAT Gateway is a single point of failure.
- Placed in public subnets
- Costs: per-hour charge + per-GB data processing. This adds up fast.
- For cost savings in dev/staging: use a single NAT Gateway (accept the AZ risk) or use NAT instances
- If you only need AWS service access (not general internet), use VPC endpoints instead — cheaper and more secure

## Anti-Patterns

- **Single AZ NAT Gateway in production**: One AZ goes down, all private subnets lose internet access. Use one NAT per AZ.
- **Using NACLs as primary firewall**: Stateless rules are error-prone. Use security groups. NACLs are backup only.
- **Overly permissive security groups**: 0.0.0.0/0 on port 22 or 3389 is never acceptable in production. Use Systems Manager Session Manager instead.
- **No VPC endpoints for S3/DynamoDB**: Gateway endpoints are free. Always create them.
- **Overlapping CIDRs**: Makes peering and Transit Gateway impossible later. Plan CIDR allocation upfront.
- **Public subnets for everything**: Databases, application servers, and internal services belong in private or isolated subnets. Only load balancers and NAT Gateways need public subnets.
- **Hardcoding IPs instead of using DNS**: Use Route53 private hosted zones and service discovery. IPs change; DNS names persist.
- **Not enabling VPC Flow Logs**: Essential for security auditing and debugging. Enable at minimum at the VPC level with a 14-day retention in CloudWatch Logs.
- **Using VPC peering for 5+ VPCs**: The mesh becomes unmanageable. Switch to Transit Gateway.
