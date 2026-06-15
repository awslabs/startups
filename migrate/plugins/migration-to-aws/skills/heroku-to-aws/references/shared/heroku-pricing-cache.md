# Heroku Pricing Cache

**Last updated:** 2026-06-15
**Source:** https://devcenter.heroku.com/articles/dyno-sizes, https://elements.heroku.com/addons/heroku-postgresql, https://elements.heroku.com/addons/heroku-redis, https://devcenter.heroku.com/articles/kafka-on-heroku
**Currency:** USD
**Accuracy:** ±5% (Heroku pricing is flat-rate and rarely changes; platform is in KTLO)

> Use this cache to derive current Heroku monthly costs when billing data is unavailable. Look up each discovered resource's plan in the tables below, multiply by quantity, and sum. If a plan is not found in this cache, set `heroku_cost_source: "unavailable"` for that resource and exclude from total.

---

## Dynos (Cedar Common Runtime)

| Plan | $/month (per dyno) |
| ---- | ------------------- |
| Eco | 5 (flat, shared pool) |
| Basic | 7 |
| Standard-1X | 25 |
| Standard-2X | 50 |
| Performance-M | 250 |
| Performance-L | 500 |
| Performance-L-RAM | 500 |
| Performance-XL | 750 |
| Performance-2XL | 1500 |

## Dynos (Cedar Private Spaces)

| Plan | $/month (per dyno) |
| ---- | ------------------- |
| Private-S | 125 |
| Private-M | 250 |
| Private-L | 500 |
| Private-L-RAM | 500 |
| Private-XL | 750 |
| Private-2XL | 1500 |

## Dynos (Cedar Shield Spaces)

| Plan | $/month (per dyno) |
| ---- | ------------------- |
| Shield-S | 150 |
| Shield-M | 300 |
| Shield-L | 600 |
| Shield-L-RAM | 600 |
| Shield-XL | 900 |
| Shield-2XL | 1800 |

## Heroku Postgres (Essential Tier)

| Plan | $/month | RAM | Storage | Connections |
| ---- | ------- | --- | ------- | ----------- |
| essential-0 | 5 | shared | 1 GB | 20 |
| essential-1 | 9 | shared | 10 GB | 20 |
| essential-2 | 15 | shared | 32 GB | 40 |

## Heroku Postgres (Standard Tier)

| Plan | $/month | RAM | Storage | Connections |
| ---- | ------- | --- | ------- | ----------- |
| standard-0 | 50 | 4 GB | 64 GB | 200 |
| standard-2 | 200 | 8 GB | 256 GB | 500 |
| standard-3 | 400 | 15 GB | 512 GB | 500 |
| standard-4 | 750 | 30 GB | 768 GB | 500 |
| standard-5 | 1200 | 61 GB | 1 TB | 500 |
| standard-6 | 2500 | 122 GB | 1.5 TB | 500 |
| standard-7 | 3500 | 244 GB | 2 TB | 500 |

## Heroku Postgres (Premium Tier)

| Plan | $/month | RAM | Storage | Connections |
| ---- | ------- | --- | ------- | ----------- |
| premium-0 | 200 | 4 GB | 64 GB | 200 |
| premium-2 | 400 | 8 GB | 256 GB | 500 |
| premium-3 | 750 | 15 GB | 512 GB | 500 |
| premium-4 | 1200 | 30 GB | 768 GB | 500 |
| premium-5 | 2500 | 61 GB | 1 TB | 500 |
| premium-6 | 3500 | 122 GB | 1.5 TB | 500 |
| premium-7 | 6000 | 244 GB | 2 TB | 500 |

## Heroku Key-Value Store (Redis)

| Plan | $/month | RAM | Connections |
| ---- | ------- | --- | ----------- |
| mini | 3 | 25 MB | 20 |
| premium-0 | 15 | 50 MB | 40 |
| premium-1 | 30 | 100 MB | 80 |
| premium-2 | 60 | 250 MB | 200 |
| premium-3 | 100 | 500 MB | 400 |
| premium-5 | 200 | 1 GB | 1000 |
| premium-7 | 500 | 7 GB | 10000 |
| premium-9 | 750 | 10 GB | 25000 |
| premium-10 | 1500 | 25 GB | 40000 |
| premium-12 | 3500 | 50 GB | 65000 |
| premium-14 | 7000 | 100 GB | 65000 |

## Apache Kafka on Heroku

| Plan | $/month | Partitions | Topics | Throughput |
| ---- | ------- | ---------- | ------ | ---------- |
| basic-0 | 100 | 20 | 20 | 5 MB/s |
| standard-0 | 175 | 40 | 40 | 10 MB/s |
| standard-1 | 350 | 120 | 60 | 20 MB/s |
| standard-2 | 700 | 240 | 120 | 40 MB/s |
| extended-0 | 1500 | 500 | 250 | 80 MB/s |
| extended-1 | 3000 | 1000 | 500 | 150 MB/s |
| extended-2 | 5000 | 2000 | 1000 | 300 MB/s |

## Common Add-ons (Fast-Path)

| Add-on | Plan | $/month |
| ------ | ---- | ------- |
| Heroku Scheduler | standard | 0 (free) |
| Papertrail | various | 0–230 |
| SendGrid | starter | 0 (free) |
| SendGrid | bronze | 10 |
| Mailgun | starter | 0 (free) |
| New Relic APM | various | 0–749 |
| Scout APM | various | 0–299 |
| Bonsai Elasticsearch | sandbox | 0 (free) |
| Bonsai Elasticsearch | standard | 50 |
| CloudAMQP | little-lemur | 0 (free) |
| CloudAMQP | tough-tiger | 19 |
| Memcachier | dev | 0 (free) |
| Memcachier | 100 | 15 |

## Private Space Base Fee

| Plan | $/month |
| ---- | ------- |
| Private Space | 1000 |
| Shield Space | 3000 |

---

## Usage Rules

1. **Lookup by plan name** (case-insensitive exact match from `heroku-resource-inventory.json`)
2. **Multiply by quantity** (from `formation.quantity` for dynos)
3. **Sum all resources** to get `heroku_monthly_estimated`
4. **Set `heroku_cost_source: "pricing_cache"`** in `estimation-infra.json`
5. **Accuracy band:** ±5% (flat-rate pricing, no usage-based variance except Eco dyno pool sharing)
6. **Not found:** If a plan is not in this cache, mark as `"unpriced_heroku"` and exclude from Heroku total. Add to warnings.
