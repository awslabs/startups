# Heroku Kafka Plan → MSK Sizing Table

## Description

This table maps Apache Kafka on Heroku plan tiers to recommended Amazon MSK broker instance types and storage configurations. The Design Engine uses this table to select an MSK configuration that meets or exceeds the source plan's throughput, storage, topic, and partition capacity.

## Lookup Table

> **Data:** [`knowledge/design/kafka-msk-sizing.json`](../../knowledge/design/kafka-msk-sizing.json)
>
> The Heroku Kafka plan → MSK sizing rows are maintained as structured data in
> that JSON file. Read the `rows` map keyed by Heroku plan; each row carries
> `broker_instance_type`, `storage_per_broker_gb`, `max_topics`, `max_partitions`,
> and `default_replication_factor`. The `throughput` and `storage` fields are
> provenance only.

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
