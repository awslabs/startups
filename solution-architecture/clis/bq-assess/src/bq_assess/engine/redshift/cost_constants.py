"""Verified AWS lakehouse pricing constants — V1 (Serverless RPU), V2 (S3 Tables) + the
V3 slot→RPU bridge ASSUMPTION (R18.7).

Confirmed 2026-06-15 against the **AWS Price List API** (machine-readable, authoritative) with a
Wayback cross-read for the RPU-hour rate. Mirrors ``core/pricing_constants.py``: dated, sourced,
overridable via module-level assignment — never hardcode a guess elsewhere.

⚠️ The module-level constants default to US East (N. Virginia) / us-east-1, USD, on-demand.
Other regions differ and are generally HIGHER. Call ``apply_aws_region(region)`` — normally
with ``bq_location_to_aws_region(detected_bq_location)`` — to re-point the constants at that
region's verified rates (AWS_REGIONAL_RATES below); the CLI/CostEstimator do this
automatically so the AWS comparison is priced in the same geography as the BigQuery side.
A live Price List API lookup (``core/price_lookup.py``, regional URL) can then override.

References:
- V1 Redshift Serverless: https://aws.amazon.com/redshift/pricing/
  (Price List API SKU USE1-Redshift:ServerlessUsage = $0.375/RPU-Hr)
- V2 S3 Tables:           https://aws.amazon.com/s3/pricing/  (S3 Tables tab; Price List API AmazonS3 us-east-1)
"""

from __future__ import annotations

AWS_CONFIRMED_DATE: str = "2026-06-24"
AWS_REGION_SCOPE: str = "US East (N. Virginia) / us-east-1"
# The AWS region the module-level constants currently reflect (set by apply_aws_region).
AWS_PRICING_REGION: str = "us-east-1"
V1_SOURCE_URL: str = "https://aws.amazon.com/redshift/pricing/"
V2_SOURCE_URL: str = "https://aws.amazon.com/s3/pricing/"

# =============================================================================
# V1 — Redshift Serverless compute, $/RPU-hour (HIGH confidence; triple-confirmed)
# =============================================================================

V1_RPU_HOUR_USD: float = 0.375
V1_RPU_GB_MEMORY: int = 16          # 1 RPU = 16 GB memory (documentary only; NOT used to size by storage)
HOURS_PER_MONTH: float = 730.0      # matches pricing_constants' hourly×730 convention

# Serverless Reservations — commitment-based discounts (launched Apr 2025 / Feb 2026).
# Unlike on-demand (pay-per-second when active), reservations bill 24/7 for the committed RPUs.
# Source: https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-billing-reserved.html
V1_SERVERLESS_RESERVATION_1YR_DISCOUNT: float = 0.24   # All Upfront, 1-year
V1_SERVERLESS_RESERVATION_3YR_DISCOUNT: float = 0.45   # No Upfront, 3-year
V1_SERVERLESS_1YR_RPU_HOUR_USD: float = round(V1_RPU_HOUR_USD * (1 - 0.24), 4)  # $0.285
V1_SERVERLESS_3YR_RPU_HOUR_USD: float = round(V1_RPU_HOUR_USD * (1 - 0.45), 4)  # $0.2063
AWS_SERVERLESS_RESERVATIONS_CONFIRMED_DATE: str = "2026-06-24"

# Break-even utilization for reservations: the active-hour fraction at which the 24/7
# reservation cost equals on-demand cost (reserved_rate / ondemand_rate).
# At utilization ABOVE this threshold, the reservation saves money vs on-demand.
V1_SERVERLESS_1YR_BREAKEVEN_UTIL: float = round(1 - V1_SERVERLESS_RESERVATION_1YR_DISCOUNT, 4)  # 0.76
V1_SERVERLESS_3YR_BREAKEVEN_UTIL: float = round(1 - V1_SERVERLESS_RESERVATION_3YR_DISCOUNT, 4)  # 0.55

# Overflow burst fraction: fraction of active hours during which peak usage exceeds
# committed RPUs. Models that overflow RPUs are transient bursts, not sustained for the
# full active period. Derived from typical query burst patterns (peak lasts ~30% of active time).
V1_OVERFLOW_BURST_FRACTION: float = 0.30

# Serverless base/step facts (HIGH; AWS mgmt docs). Used ONLY for the R18.4 no-data range floor.
SERVERLESS_MIN_RPU_FLOOR: int = 4       # minimum base capacity for Redshift Serverless
SERVERLESS_DEFAULT_BASE_RPU: int = 32   # moderate workload anchor (range high)
# Hours/month the no-data range assumes the warehouse is "on". Models a typical business-day
# usage pattern: 8 hours/day × 22 working days ≈ 176 hours/month.
RANGE_ACTIVE_HOURS_PER_MONTH: float = 176.0

# =============================================================================
# V2 — S3 Tables Standard storage, $/GB-month, us-east-1 (HIGH confidence)
# ⚠️ S3 TABLES, not plain S3 Standard ($0.023) — the managed Iceberg/compaction layer is ~15%
#    dearer and adds the monitoring/compaction lines below that plain S3 lacks.
# Marginal tiering: store tier WIDTHS, not cumulative thresholds (the audit caught a 50 TB bug).
# Billed in GB (decimal, 10^9), per AWS convention — distinct from BigQuery's binary GiB.
# =============================================================================

V2_S3_TABLES_USD_PER_GB_MONTH_TIER1: float = 0.0265   # first 50 TB
V2_S3_TABLES_USD_PER_GB_MONTH_TIER2: float = 0.0253   # next 450 TB (50–500 TB)
V2_S3_TABLES_USD_PER_GB_MONTH_TIER3: float = 0.0242   # over 500 TB
V2_TIER1_WIDTH_GB: float = 50.0 * 1000      # first 50 TB, in decimal GB
V2_TIER2_WIDTH_GB: float = 450.0 * 1000     # next 450 TB (NOT 500 — marginal width)
GB_PER_BYTE: float = 1e-9                    # AWS storage billing: bytes → decimal GB

# Physical-bytes fallback ratio: canonical value lives in core/storage_stats.py
# (collection-time concern — the collector distribution must not import the engine).
# Re-exported so cost/report call sites keep their k.ASSUMED_PHYSICAL_RATIO idiom.
from bq_assess.core.storage_stats import ASSUMED_PHYSICAL_RATIO  # noqa: E402,F401

# S3-Tables-only recurring maintenance lines (plain S3 lacks these) — the "negligible
# request/maintenance lines" R18.1 folds alongside storage.
V2_OBJECT_MONITORING_USD_PER_1K_OBJECTS_MONTH: float = 0.025
V2_COMPACTION_USD_PER_1K_OBJECTS: float = 0.002
V2_COMPACTION_USD_PER_GB_PROCESSED: float = 0.005
V2_REQUEST_TIER1_USD_PER_1K: float = 0.005      # PUT/COPY/POST/LIST
V2_REQUEST_TIER2_USD_PER_1K: float = 0.0004     # GET/other

# =============================================================================
# V3 — slot→RPU bridge.  ⚠️⚠️ LOW-CONFIDENCE ASSUMPTION, NOT A VERIFIED FACT. ⚠️⚠️
# There is NO published AWS/GCP slot↔RPU equivalence. Cross-referencing hardware specs
# (1 RPU = 2 vCPU + 16 GB; 1 BQ slot ≈ 0.5 vCPU) yields ~0.25; the Fivetran 2022 benchmark
# (300 BQ slots ≈ 18 RPU-equiv at performance parity) yields ~0.06; pure cost ratio ($0.06 vs
# $0.375 per unit-hr) yields ~0.16. We use 0.20 — deliberately ABOVE the evidence midpoint,
# toward the hardware-spec bound (~0.25) — so the projected Redshift compute errs on the
# HIGH side and quoted savings err conservative (raised from 0.15 on 2026-07-05 after the
# Montu reconciliation; understating AWS cost is the riskier direction in a customer-facing
# business case). MUST be replaced by empirical RPU-hour measurement (SYS_SERVERLESS_USAGE)
# on a representative migrated workload before quoting. Every emitted compute line carries a
# visible LOW-confidence / ASSUMPTION label (R18.7).
# =============================================================================

V3_SLOT_TO_RPU_RATIO: float = 0.20
V3_CONFIDENCE_IS_ASSUMPTION: bool = True
V3_ASSUMPTION_NOTE: str = (
    "slot→RPU 0.20 ASSUMPTION (evidence range: 0.06–0.25, set above midpoint so AWS "
    "compute errs high / savings err conservative; no published equivalence; "
    "overridable; verify with empirical RPU-hour measurement before quoting)"
)

# =============================================================================
# Plan vocabulary bridge — PricingDetection.commitment_plan → V4_EDITION_SLOT_HOUR_USD sub-key.
# PricingDetection emits {FLEX, MONTHLY, ANNUAL, THREE_YEAR}; the V4 rate table keys on
# {payg, commit_1yr, commit_3yr}. FLEX/MONTHLY have no slot commitment → payg.
# =============================================================================

COMMITMENT_PLAN_TO_RATE_KEY: dict[str, str] = {
    "FLEX": "payg",
    "MONTHLY": "payg",
    "ANNUAL": "commit_1yr",
    "THREE_YEAR": "commit_3yr",
}

# =============================================================================
# Migration one-time cost — derived from aggregate Migration Effort (R9), NOT a per-table fee
# (R18.5). $/effort-point; calibration-tunable (R9.2 weights are "subject to calibration").
# =============================================================================

MIGRATION_USD_PER_EFFORT_POINT: float = 5.0

# =============================================================================
# BigQuery on-demand scan proxy — when no query logs/slots are available, estimate monthly
# bytes scanned as a fraction of stored bytes per day (R18.2a). Labelled LOW-confidence estimate.
# =============================================================================

BQ_DAILY_SCAN_FRACTION: float = 0.10    # 10% of stored bytes scanned/day (legacy proxy, retained)
DAYS_PER_MONTH: float = 30.0

# Break-even sentinel: finite (JSON-safe) stand-in for "migration never recoups". 9999 months
# (~833 years) is semantically equivalent to "never" for any business decision.
BREAKEVEN_NEVER: float = 9999.0

# =============================================================================
# V6 — Redshift Provisioned RA3, $/node-hour, us-east-1 (HIGH confidence)
# Confirmed 2026-06-15 against the AWS Price List API.
# References: https://aws.amazon.com/redshift/pricing/
# =============================================================================

AWS_PROVISIONED_CONFIRMED_DATE: str = "2026-06-24"

# =============================================================================
# V7 — Redshift Graviton (RG) instances, $/node-hour, us-east-1 (HIGH confidence)
# GA May 12, 2026. Graviton4-powered, 30% lower price/vCPU vs RA3, eliminates
# separate Spectrum per-TB charges (built-in data lake query engine).
# Source: https://aws.amazon.com/redshift/pricing/
# Migration from RA3: 4:3 node mapping (4× ra3.4xl → 3× rg.4xl) for 25% infra savings.
# =============================================================================

V7_RG_NODE_TYPES: dict[str, dict] = {
    "rg.xlarge": {
        "vcpu": 4,
        "memory_gb": 32,
        "ondemand_usd_per_node_hour": 0.76,
        "ri_1yr_usd_per_node_hour": 0.532,
        "ri_3yr_usd_per_node_hour": 0.331,
        "min_nodes": 2,
        "max_nodes": 32,
    },
    "rg.4xlarge": {
        "vcpu": 16,
        "memory_gb": 128,
        "ondemand_usd_per_node_hour": 3.043,
        "ri_1yr_usd_per_node_hour": 2.130,
        "ri_3yr_usd_per_node_hour": 1.324,
        "min_nodes": 2,
        "max_nodes": 32,
    },
    "rg.16xlarge": {
        "vcpu": 64,
        "memory_gb": 512,
        "ondemand_usd_per_node_hour": 12.173,
        "ri_1yr_usd_per_node_hour": 8.521,
        "ri_3yr_usd_per_node_hour": 5.297,
        "min_nodes": 2,
        "max_nodes": 128,
    },
}

# Legacy RA3 types retained for reference/fallback (regions without RG availability).
V6_RA3_NODE_TYPES: dict[str, dict] = {
    "ra3.xlplus": {
        "vcpu": 4,
        "memory_gb": 32,
        "ondemand_usd_per_node_hour": 1.086,
        "ri_1yr_usd_per_node_hour": 0.760,
        "ri_3yr_usd_per_node_hour": 0.473,
        "min_nodes": 2,
        "max_nodes": 32,
    },
    "ra3.4xlarge": {
        "vcpu": 12,
        "memory_gb": 96,
        "ondemand_usd_per_node_hour": 3.26,
        "ri_1yr_usd_per_node_hour": 2.282,
        "ri_3yr_usd_per_node_hour": 1.418,
        "min_nodes": 2,
        "max_nodes": 32,
    },
    "ra3.16xlarge": {
        "vcpu": 48,
        "memory_gb": 384,
        "ondemand_usd_per_node_hour": 13.04,
        "ri_1yr_usd_per_node_hour": 9.128,
        "ri_3yr_usd_per_node_hour": 5.672,
        "min_nodes": 2,
        "max_nodes": 128,
    },
}

# Redshift Managed Storage (RMS): applies to all RA3 node types.
V6_MANAGED_STORAGE_USD_PER_GB_MONTH: float = 0.024

# Concurrency scaling: 1 free hour/day/cluster; billed at same node-hour rate beyond that.
V6_CONCURRENCY_SCALING_FREE_HOURS_PER_DAY: float = 1.0
# Fraction of base cost to add for concurrency scaling burst (workload-dependent estimate).
V6_CONCURRENCY_SCALING_OVERHEAD_FRACTION: float = 0.20

# =============================================================================
# Region cascade — BigQuery dataset location → nearest AWS region, plus verified
# per-region AWS rates. Verified 2026-07-02 against the AWS Price List API
# (AmazonRedshift + AmazonS3 regional offer files). The comparison must price both
# clouds in the same geography: an australia-southeast1 Source gets its Query Engine
# (Redshift Serverless / provisioned nodes) and storage priced in ap-southeast-2,
# not us-east-1.
# =============================================================================

# BigQuery location token (lowercase) → AWS region: canonical mapping lives in
# core/region_mapping.py (the collector distribution records aws_region in the bundle
# manifest without importing the engine). Re-exported here for existing call sites.
from bq_assess.core.region_mapping import (  # noqa: E402,F401
    BQ_LOCATION_TO_AWS_REGION,
    bq_location_to_aws_region,
)

# Per-AWS-region rates (Price List API, 2026-07-02). rg.16xlarge is not yet published in
# the regional offer files — derived as 4× rg.4xlarge, which matches us-east-1 exactly
# (12.173 ≈ 4 × 3.043).
AWS_REGIONAL_RATES: dict[str, dict] = {
    "us-east-1": {
        "label": "US East (N. Virginia)",
        "rpu_hour": 0.375, "rms": 0.024,
        "s3_tables": (0.0265, 0.0253, 0.0242),
        "rg.xlarge": (0.76, 0.532, 0.331), "rg.4xlarge": (3.043, 2.130, 1.324),
        "ra3.xlplus": (1.086, 0.760, 0.473), "ra3.4xlarge": (3.26, 2.282, 1.418), "ra3.16xlarge": (13.04, 9.128, 5.672),
    },
    "us-west-2": {
        "label": "US West (Oregon)",
        "rpu_hour": 0.36, "rms": 0.024,
        "s3_tables": (0.0265, 0.0253, 0.0242),
        "rg.xlarge": (0.7602, 0.53214, 0.33075), "rg.4xlarge": (3.04267, 2.12987, 1.32356),
        "ra3.xlplus": (1.086, 0.7602, 0.4725), "ra3.4xlarge": (3.26, 2.282, 1.4181), "ra3.16xlarge": (13.04, 9.128, 5.6724),
    },
    "ca-central-1": {
        "label": "Canada (Central)",
        "rpu_hour": 0.4125, "rms": 0.0261,
        "s3_tables": (0.0288, 0.0276, 0.0265),
        "rg.xlarge": (0.8414, 0.58898, 0.36603), "rg.4xlarge": (3.36653, 2.35723, 1.46487),
        "ra3.xlplus": (1.202, 0.8414, 0.5229), "ra3.4xlarge": (3.607, 2.5256, 1.5695), "ra3.16xlarge": (14.43, 10.101, 6.2771),
    },
    "sa-east-1": {
        "label": "South America (São Paulo)",
        "rpu_hour": 0.5976, "rms": 0.043,
        "s3_tables": (0.0466, 0.0449, 0.0426),
        "rg.xlarge": (1.2117, 0.8484, 0.5271), "rg.4xlarge": (4.84867, 3.39407, 2.10924),
        "ra3.xlplus": (1.731, 1.212, 0.753), "ra3.4xlarge": (5.195, 3.6365, 2.2599), "ra3.16xlarge": (20.78, 14.546, 9.0393),
    },
    "eu-west-1": {
        "label": "Europe (Ireland)",
        "rpu_hour": 0.387, "rms": 0.024,
        "s3_tables": (0.0265, 0.0253, 0.0242),
        "rg.xlarge": (0.8414, 0.58898, 0.36603), "rg.4xlarge": (3.3656, 2.35592, 1.46412),
        "ra3.xlplus": (1.202, 0.8414, 0.5229), "ra3.4xlarge": (3.606, 2.5242, 1.5687), "ra3.16xlarge": (14.424, 10.0968, 6.2745),
    },
    "eu-west-2": {
        "label": "Europe (London)",
        "rpu_hour": 0.467, "rms": 0.025,
        "s3_tables": (0.0276, 0.0265, 0.0253),
        "rg.xlarge": (0.8848, 0.61936, 0.38493), "rg.4xlarge": (3.54013, 2.47809, 1.54),
        "ra3.xlplus": (1.264, 0.8848, 0.5499), "ra3.4xlarge": (3.793, 2.6551, 1.65), "ra3.16xlarge": (15.174, 10.6218, 6.6007),
    },
    "eu-central-1": {
        "label": "Europe (Frankfurt)",
        "rpu_hour": 0.451, "rms": 0.0256,
        "s3_tables": (0.0282, 0.027, 0.0259),
        "rg.xlarge": (0.9086, 0.63602, 0.39529), "rg.4xlarge": (3.6344, 2.54408, 1.58097),
        "ra3.xlplus": (1.298, 0.9086, 0.5647), "ra3.4xlarge": (3.894, 2.7258, 1.6939), "ra3.16xlarge": (15.578, 10.9046, 6.7765),
    },
    "ap-southeast-2": {
        "label": "Asia Pacific (Sydney)",
        "rpu_hour": 0.419, "rms": 0.0261,
        "s3_tables": (0.0288, 0.0276, 0.0265),
        "rg.xlarge": (0.9121, 0.63847, 0.39683), "rg.4xlarge": (3.6484, 2.55388, 1.58713),
        "ra3.xlplus": (1.303, 0.9121, 0.5669), "ra3.4xlarge": (3.909, 2.7363, 1.7005), "ra3.16xlarge": (15.636, 10.9452, 6.8017),
    },
    "ap-southeast-1": {
        "label": "Asia Pacific (Singapore)",
        "rpu_hour": 0.45, "rms": 0.0261,
        "s3_tables": (0.0288, 0.0276, 0.0265),
        "rg.xlarge": (0.9121, 0.63847, 0.39683), "rg.4xlarge": (3.6484, 2.55388, 1.58713),
        "ra3.xlplus": (1.303, 0.9121, 0.5669), "ra3.4xlarge": (3.909, 2.7363, 1.7005), "ra3.16xlarge": (15.636, 10.9452, 6.8017),
    },
    "ap-northeast-1": {
        "label": "Asia Pacific (Tokyo)",
        "rpu_hour": 0.494, "rms": 0.0261,
        "s3_tables": (0.0288, 0.0276, 0.0265),
        "rg.xlarge": (0.8946, 0.62622, 0.3892), "rg.4xlarge": (3.58027, 2.50619, 1.55745),
        "ra3.xlplus": (1.278, 0.8946, 0.556), "ra3.4xlarge": (3.836, 2.6852, 1.6687), "ra3.16xlarge": (15.347, 10.7429, 6.676),
    },
    "ap-south-1": {
        "label": "Asia Pacific (Mumbai)",
        "rpu_hour": 0.4275, "rms": 0.0261,
        "s3_tables": (0.0288, 0.0276, 0.0265),
        "rg.xlarge": (0.8645, 0.60515, 0.37611), "rg.4xlarge": (3.45893, 2.42125, 1.50472),
        "ra3.xlplus": (1.235, 0.8645, 0.5373), "ra3.4xlarge": (3.706, 2.5942, 1.6122), "ra3.16xlarge": (14.827, 10.3789, 6.4498),
    },
}


def apply_aws_region(region: str) -> bool:
    """Re-point the module-level AWS rate constants at ``region``'s verified rates.

    Returns True when the region is in the verified table (constants updated), False when
    unknown (constants left at us-east-1 so callers can attach a caveat). Same
    overridable-module-assignment contract as apply_live_rates (R18.7).
    """
    global V1_RPU_HOUR_USD, V1_SERVERLESS_1YR_RPU_HOUR_USD, V1_SERVERLESS_3YR_RPU_HOUR_USD
    global V2_S3_TABLES_USD_PER_GB_MONTH_TIER1, V2_S3_TABLES_USD_PER_GB_MONTH_TIER2
    global V2_S3_TABLES_USD_PER_GB_MONTH_TIER3, V6_MANAGED_STORAGE_USD_PER_GB_MONTH
    global AWS_PRICING_REGION, AWS_REGION_SCOPE

    rates = AWS_REGIONAL_RATES.get(region)
    if rates is None:
        return False

    V1_RPU_HOUR_USD = rates["rpu_hour"]
    V1_SERVERLESS_1YR_RPU_HOUR_USD = round(
        V1_RPU_HOUR_USD * (1 - V1_SERVERLESS_RESERVATION_1YR_DISCOUNT), 4
    )
    V1_SERVERLESS_3YR_RPU_HOUR_USD = round(
        V1_RPU_HOUR_USD * (1 - V1_SERVERLESS_RESERVATION_3YR_DISCOUNT), 4
    )
    t1, t2, t3 = rates["s3_tables"]
    V2_S3_TABLES_USD_PER_GB_MONTH_TIER1 = t1
    V2_S3_TABLES_USD_PER_GB_MONTH_TIER2 = t2
    V2_S3_TABLES_USD_PER_GB_MONTH_TIER3 = t3
    V6_MANAGED_STORAGE_USD_PER_GB_MONTH = rates["rms"]

    for node_type, table in (("rg.xlarge", V7_RG_NODE_TYPES), ("rg.4xlarge", V7_RG_NODE_TYPES),
                             ("ra3.xlplus", V6_RA3_NODE_TYPES), ("ra3.4xlarge", V6_RA3_NODE_TYPES),
                             ("ra3.16xlarge", V6_RA3_NODE_TYPES)):
        od, ri1, ri3 = rates[node_type]
        table[node_type]["ondemand_usd_per_node_hour"] = od
        table[node_type]["ri_1yr_usd_per_node_hour"] = ri1
        table[node_type]["ri_3yr_usd_per_node_hour"] = ri3
    # rg.16xlarge is not in the regional Price List offers — derive as 4× rg.4xlarge
    # (matches us-east-1's published rate).
    od4, ri1_4, ri3_4 = rates["rg.4xlarge"]
    V7_RG_NODE_TYPES["rg.16xlarge"]["ondemand_usd_per_node_hour"] = round(od4 * 4, 4)
    V7_RG_NODE_TYPES["rg.16xlarge"]["ri_1yr_usd_per_node_hour"] = round(ri1_4 * 4, 4)
    V7_RG_NODE_TYPES["rg.16xlarge"]["ri_3yr_usd_per_node_hour"] = round(ri3_4 * 4, 4)

    AWS_PRICING_REGION = region
    AWS_REGION_SCOPE = f"{rates['label']} / {region}"
    return True


# =============================================================================
# V6 — Cluster sizing heuristics (from workload metrics)
# =============================================================================

# Queries/day thresholds that determine node type.
V6_QUERIES_PER_DAY_XLPLUS_MAX: int = 50_000
V6_QUERIES_PER_DAY_4XL_MAX: int = 500_000

# vCPUs needed per concurrent query slot (heuristic; BQ on-demand typically runs
# queries with 1-4 effective slot equivalents for small scans, more for large scans).
V6_VCPU_PER_CONCURRENT_QUERY: float = 1.5

# Assumed average query duration in seconds (for concurrency estimation from QPD).
V6_AVG_QUERY_DURATION_SECONDS: float = 7.0
# Peak-to-average ratio for query concurrency (business-hour burst factor).
V6_PEAK_TO_AVG_CONCURRENCY_RATIO: float = 3.0
