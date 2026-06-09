# DynamoDB
## Process

## Key Design Principles

### Partition Key Selection
- **High cardinality is mandatory.** A partition key with few distinct values creates hot partitions.
- Good partition keys: `userId`, `orderId`, `deviceId`, `tenantId`
- Bad partition keys: `status`, `date`, `region`, `type`
- If you must query by a low-cardinality attribute, use it as a sort key or GSI sort key — never as the partition key.

### Sort Key Design
- Use composite sort keys to enable flexible queries: `STATUS#TIMESTAMP`, `TYPE#2024-01-15`
- Sort keys enable `begins_with`, `between`, and range queries — design them for your query patterns
- Hierarchical sort keys work well: `COUNTRY#STATE#CITY` lets you query at any level with `begins_with`

### Single-Table Design
Use single-table design when:
- You need transactions across entity types
- You want to minimize the number of DynamoDB tables to manage
- Your entities share the same partition key (e.g., all items for a tenant)

Avoid single-table design when:
- Access patterns are simple and don't cross entity boundaries
- Team members are unfamiliar with the pattern (readability matters)
- You need different table-level settings per entity type (encryption, capacity, TTL)

Generic key names (`PK`, `SK`, `GSI1PK`, `GSI1SK`) are standard for single-table design.

**Prefer GSIs over LSIs unless you need strong consistency on the alternate sort key**

## Capacity Modes

### On-Demand
- Use for: unpredictable traffic, new workloads, spiky patterns, dev/test
- More expensive per-request than provisioned at sustained volume
- Scales instantly (within previously reached traffic levels; new peaks may take minutes)

### Provisioned
- Use for: predictable, steady-state production workloads
- Enable auto-scaling — never set a fixed capacity without it
- Set target utilization to 70% for auto-scaling
- Reserved capacity available for further savings on committed throughput
- Provisioned is typically 5-7x cheaper than on-demand at sustained load

## DynamoDB Streams
- Use for: event-driven architectures, cross-region replication, materialized views, analytics pipelines
- Stream records are available for 24 hours
- Pair with Lambda for real-time processing — use event source mapping with batch size tuning

## TTL (Time to Live)

- Set a TTL attribute (epoch seconds) to auto-expire items at no cost
- Deletion is eventual — items may persist up to 48 hours past expiry
- TTL deletions appear in Streams (useful for cleanup triggers)
- Use for: session data, temporary tokens, audit logs with retention policies
- Filter expired items in queries with a condition: `#ttl > :now`

## DAX (DynamoDB Accelerator)

- In-memory cache in front of DynamoDB — microsecond read latency
- Use for: read-heavy workloads with repeated access to the same items
- **Do not use DAX when:** writes are heavy, data changes constantly, or you need strongly consistent reads (DAX serves eventually consistent by default)
- DAX cluster runs in your VPC — factor in the instance cost
- Item cache and query cache are separate — both cache misses hit DynamoDB

## Anti-Patterns

- **Scan for queries.** If you're scanning with a filter, you need a GSI or a redesigned key schema.
- **Hot partition keys.** A single partition key that receives disproportionate traffic (e.g., `status=ACTIVE`) throttles the entire table.
- **Large items.** DynamoDB max item size is 400 KB. Store large blobs in S3 and keep a pointer in DynamoDB.
- **Relational modeling.** Don't normalize into many tables with joins — DynamoDB has no joins. Denormalize and use single-table design or composite keys.
- **Over-indexing.** Each GSI duplicates data and consumes write capacity. Only create indexes for access patterns you actually need.
- **Using Scan in production code paths.** Scans read the entire table and are expensive. Use Query with a well-designed key schema instead.
- **Ignoring pagination.** Query and Scan return max 1 MB per call. Always handle `LastEvaluatedKey` for pagination.
- **Not using condition expressions.** Without conditions on writes, concurrent updates silently overwrite each other. Use `attribute_not_exists` or version counters for optimistic locking.
