# RDS and Aurora

## Engine Selection Decision Matrix

| Requirement                                               | Recommendation                                              | Why                                                           |
|-----------------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------------------|
| MySQL/PostgreSQL, predictable workload, cost-sensitive    | RDS for MySQL/PostgreSQL                                    | Simpler, cheaper for small-medium workloads                   |
| MySQL/PostgreSQL, high availability, auto-scaling storage | Aurora (MySQL/PostgreSQL)                                   | 6-way replicated storage, up to 128 TB auto-grow              |
| Spiky or unpredictable traffic                            | Aurora Serverless v2                                        | Scales ACUs in 0.5 increments, optional scale-to-zero support |
| Oracle or SQL Server licensing                            | RDS for Oracle / SQL Server                                 | Only option for these engines on managed AWS                  |
| Very small dev/test database                              | RDS with `db.t4g.micro` or Aurora Serverless v2 min 0.5 ACU | Lowest cost entry points                                      |
| High write throughput, global                             | Aurora Global Database                                      | Sub-second cross-region replication, write forwarding         |
| Existing on-prem PostgreSQL migration                     | Aurora PostgreSQL + DMS                                     | Wire-compatible, minimal app changes                          |

## Cost Comparison
- Aurora instances cost ~20% more than equivalent RDS instances
- Aurora eliminates separate EBS costs — storage is included in the Aurora pricing model
- For read-heavy workloads, Aurora's shared storage makes replicas cheaper (no storage duplication)
- Aurora Serverless v2 can be more cost-effective for variable workloads than provisioned instances sitting idle

### When to Use Serverless v2
- Development and staging environments
- Applications with idle periods (nights, weekends)
- Spiky read workloads (reporting, batch queries)
- New applications where traffic patterns are unknown

### When to Avoid Serverless v2
- Sustained high-throughput production writers — provisioned is cheaper at steady state
- Latency-sensitive workloads during scale-up (scaling from minimum takes seconds, not instant)

## High Availability Configurations

### RDS Multi-AZ (Instance)
- Synchronous standby in a different AZ — automatic failover
- Standby is not readable (unlike Aurora replicas)
- Use for: production databases that need simple HA without read scaling

### RDS Multi-AZ (Cluster) — db.r6gd Only
- One writer + two readable standbys across 3 AZs
- Uses local NVMe + synchronous replication
- Sub-35-second failover
- Limited to specific instance classes

### Aurora Multi-AZ
- Create at least one read replica in a different AZ for HA
- All replicas share storage, so failover has zero data loss
- For production: minimum 2 replicas across 2 AZs (writer + 2 readers = 3 AZs)

### Aurora Global Database
- Cross-region replication with <1 second typical lag
- Managed RPO/RTO with automated failover
- Write forwarding lets readers in secondary regions redirect writes to the primary
- Use for: disaster recovery, low-latency global reads

## RDS Proxy

- Fully managed connection pooler sitting between applications and the database
- Multiplexes thousands of application connections to a smaller pool of database connections
- Reduces failover time by maintaining open connections to standby
- Essential for Lambda → RDS/Aurora (Lambda creates many short-lived connections)

### When to Use RDS Proxy
- Lambda functions connecting to RDS/Aurora (connection exhaustion risk)
- Applications with many short-lived connections
- Reducing failover disruption (proxy pins to new primary automatically)

### When to Skip RDS Proxy
- Applications with persistent connection pools (like traditional app servers with HikariCP/pgBouncer)
- Workloads requiring session-level features (prepared statements, temp tables — proxy may pin connections)

## Security

### Encryption
- **At rest**: Enable at creation time (cannot be enabled later without snapshot-restore). Use AWS KMS CMK for key control.
- **In transit**: Enforce SSL via parameter group (`rds.force_ssl = 1` for PostgreSQL, `require_secure_transport = ON` for MySQL)

### Network Isolation
- Deploy in private subnets only — never assign a public IP
- Use security groups to restrict ingress to application subnets
- Use VPC endpoints for API calls (`rds` and `rds-data` endpoints)

### Authentication
- **IAM database authentication**: Token-based, no passwords stored — good for Lambda and automated access
- **Secrets Manager rotation**: Automatic password rotation on a schedule — use for traditional username/password auth
- **Kerberos/Active Directory**: Available for SQL Server and Oracle via AWS Directory Service

## Blue/Green Deployments

- Create a "green" copy of the production database with changes applied (engine upgrade, parameter changes, schema changes)
- RDS keeps the green environment in sync via logical replication
- Switchover takes ~1 minute with minimal downtime
- Automatic rollback if health checks fail

### Supported Changes
- Major engine version upgrades
- Parameter group changes
- Schema changes on the green environment
- Instance class changes

### Limitations
- Not available for Aurora Serverless v1 (v2 supported)
- Requires enough capacity for both environments during the transition

## Anti-Patterns

- **Public subnets for databases.** Never place RDS/Aurora in a public subnet. Use private subnets and access through application layer, VPN, or bastion.
- **Default parameter groups.** Always create custom parameter groups — default ones cannot be modified and make tuning impossible.
- **Unencrypted instances.** Encryption must be enabled at creation. Retrofitting requires snapshot → copy-encrypted → restore, which means downtime and new endpoints.
- **Lambda without RDS Proxy.** Lambda creates new connections per invocation. Without a connection pooler, concurrent Lambdas exhaust `max_connections` within seconds.
- **Single-AZ production databases.** No HA means any AZ failure takes down the database until manual intervention.
- **Oversized instances "just in case".** Start with Performance Insights data, right-size based on actual db.load, not guesswork. Graviton (r7g) instances offer better price-performance.
- **Ignoring storage IOPS limits.** gp3 default is 3,000 IOPS — if the workload exceeds this, provision higher IOPS or move to io2 before hitting throttling.
- **Manual password management.** Use `--manage-master-user-password` (Secrets Manager integration) or IAM authentication. Hardcoded passwords in application config are a security incident waiting to happen.
- **Not enabling deletion protection on production.** A single `delete-db-instance` call without deletion protection can destroy the production database.

### Common Migration Paths
- **Self-managed MySQL/PostgreSQL → Aurora**: Use AWS DMS for minimal-downtime migration with CDC
- **Oracle/SQL Server → Aurora PostgreSQL**: Use AWS SCT (Schema Conversion Tool) + DMS
- **RDS MySQL → Aurora MySQL**: Use snapshot restore (fastest) or create Aurora read replica of RDS instance then promote

### Key Considerations
- Always run SCT assessment report before cross-engine migrations — it quantifies conversion effort
- Test with DMS validation tasks to verify data integrity post-migration
- Plan for endpoint changes — Aurora uses cluster endpoints (writer) and reader endpoints
