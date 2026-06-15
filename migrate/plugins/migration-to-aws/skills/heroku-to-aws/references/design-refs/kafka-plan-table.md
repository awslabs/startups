# Heroku Kafka Plan → MSK Sizing Table

## Description

This table maps Apache Kafka on Heroku plan tiers to recommended Amazon MSK broker instance types and storage configurations. The Design Engine uses this table to select an MSK configuration that meets or exceeds the source plan's throughput, storage, topic, and partition capacity.

## Lookup Table

| Heroku Plan | Max Topics | Max Partitions | Storage | Throughput | Recommended MSK Broker Instance Type | Recommended Storage Per Broker |
|------------|-----------|---------------|---------|-----------|--------------------------------------|-------------------------------|
| basic-0 | 20 | 40 | 4 GB | 5 MB/s | kafka.t3.small | 10 GB |
| standard-0 | 40 | 160 | 50 GB | 20 MB/s | kafka.m5.large | 100 GB |
| standard-1 | 100 | 400 | 200 GB | 50 MB/s | kafka.m5.xlarge | 250 GB |
| standard-2 | 200 | 1600 | 1 TB | 100 MB/s | kafka.m5.2xlarge | 500 GB |
| extended-0 | 200 | 2000 | 2 TB | 150 MB/s | kafka.m5.4xlarge | 1 TB |
| extended-1 | 400 | 4000 | 4 TB | 200 MB/s | kafka.m5.8xlarge | 2 TB |
| extended-2 | 600 | 8000 | 8 TB | 300 MB/s | kafka.m5.12xlarge | 4 TB |
| private-extended-0 | 200 | 2000 | 2 TB | 150 MB/s | kafka.m5.4xlarge | 1 TB |
| private-extended-1 | 400 | 4000 | 4 TB | 200 MB/s | kafka.m5.8xlarge | 2 TB |
| private-extended-2 | 600 | 8000 | 8 TB | 300 MB/s | kafka.m5.12xlarge | 4 TB |

## Interpretation Notes

- **Matching rule**: Select the row where the Heroku Kafka plan exactly matches (case-insensitive) the source add-on's `plan` field.
- **Broker instance type**: The recommended MSK broker instance type provides throughput capacity that meets or exceeds the source plan's throughput value.
- **Storage per broker**: The recommended storage per broker, when multiplied by the number of brokers, meets or exceeds the source plan's total storage capacity.
- **Broker count and availability**:
  - All MSK clusters SHALL specify a minimum of **2 brokers** spread across at least **2 availability zones**.
  - For standard and extended plans, use **3 brokers across 3 AZs** for production resilience.
  - For basic plans, use **2 brokers across 2 AZs** as the minimum.
- **Topic and partition preservation**: The MSK configuration SHALL preserve the source plan's maximum topic count and maximum partition count. These values inform MSK cluster configuration parameters.
- **Replication factor**: Preserve the source Kafka replication factor in the MSK design. Default to replication factor of **3** for standard/extended/private plans and **2** for basic plans.
- **Private plans**: These run in Heroku Private Spaces. The MSK cluster should be deployed within the VPC referenced in the Private Space VPC design.
- **Throughput**: The source throughput value represents the aggregate write throughput the cluster must support. The recommended broker instance type meets or exceeds this when accounting for the number of brokers.

## Error Handling

If a plan tier is not found in this table, reject the mapping and report an error:

> "Unrecognized heroku-kafka plan tier: `{plan}`. Cannot determine MSK broker instance type. Deferring to specialist engagement."
