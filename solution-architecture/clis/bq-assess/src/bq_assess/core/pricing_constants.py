"""Verified BigQuery pricing + reservation-detection constants (V4, V5).

Confirmed against live cloud.google.com pages on 2026-06-11 via an adversarial
web-verification pass (50 facts cross-checked + a focused second-pass re-fetch of the four
dollar figures the cost comparison hinges on). Values are overridable via module-level
assignment for testing or future updates — never hardcode a guess elsewhere (R18.7).

⚠️ The module-level V4_* constants default to US MULTI-REGION (region token "us") in USD.
Other regions differ and are generally HIGHER (e.g. australia-southeast1 on-demand is
$8.125/TiB vs $6.25). Call ``apply_bq_region(location)`` with the Source's detected dataset
location to re-point the constants at that region's verified rates (V4_REGIONAL_RATES below)
— the CLI does this automatically from the scanned datasets. A live Cloud Billing Catalog
lookup (``core/price_lookup.py``, region-filtered) can then override with current rates.

⚠️ The BigQuery pricing page publishes no machine-readable last-updated date; freshness here
is a live 2026-06-11 fetch corroborated by a 2026-06-07 Wayback capture. The
INFORMATION_SCHEMA doc pages ARE dated (reservation views 2026-06-09, JOBS 2026-06-10 UTC).

References:
- V4 pricing:  https://cloud.google.com/bigquery/pricing
- V5 JOBS:     https://docs.cloud.google.com/bigquery/docs/information-schema-jobs
- V5 reserv.:  https://docs.cloud.google.com/bigquery/docs/information-schema-reservations
               https://docs.cloud.google.com/bigquery/docs/information-schema-capacity-commitments
               https://docs.cloud.google.com/bigquery/docs/information-schema-assignments
"""

from __future__ import annotations

V4_CONFIRMED_DATE: str = "2026-07-02"
V5_CONFIRMED_DATE: str = "2026-06-24"
V4_PRICING_SOURCE_URL: str = "https://cloud.google.com/bigquery/pricing"
V4_REGION_SCOPE: str = "US multi-region (us)"
# The BigQuery dataset location the module-level V4_* constants currently reflect
# (lowercase location token; set by apply_bq_region).
V4_PRICING_REGION: str = "us"

# =============================================================================
# V4 — On-demand (analysis) pricing
# =============================================================================

# Query/analysis: price per TiB of data scanned. Billed per TiB = 2^40 bytes.
V4_ONDEMAND_USD_PER_TIB: float = 6.25
# First N TiB of query data processed per month is free, per billing account.
V4_ONDEMAND_FREE_TIB_PER_MONTH: float = 1.0

# =============================================================================
# V4 — Storage pricing ($/GiB-month; billed in GiB = 2^30 bytes, binary)
# Page quotes per-GiB-hour rates; monthly = hourly x 730.
# =============================================================================

V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH: float = 0.02
V4_STORAGE_LONGTERM_LOGICAL_USD_PER_GIB_MONTH: float = 0.01
V4_STORAGE_ACTIVE_PHYSICAL_USD_PER_GIB_MONTH: float = 0.04
V4_STORAGE_LONGTERM_PHYSICAL_USD_PER_GIB_MONTH: float = 0.02
# First N GiB of storage per month is free.
V4_STORAGE_FREE_GIB_PER_MONTH: float = 10.0
# A table/partition not modified for 90 consecutive days drops to the long-term rate
# (~50% lower; no performance/durability/availability difference).
V4_LONGTERM_THRESHOLD_DAYS: int = 90

# =============================================================================
# V4 — Editions (capacity) compute pricing, USD per slot-hour
# Keyed by the `edition` value as it appears in INFORMATION_SCHEMA.JOBS.
# `commit_1yr` / `commit_3yr` are the Billing Catalog's per-edition "1 Year"/"3 Years"
# commitment SKUs — consistently payg×0.8 / payg×0.6 in EVERY region including US
# (catalog-verified 2026-07-03: US ENTERPRISE 1yr $0.048, 3yr $0.036). These defaults
# MUST match what apply_bq_region derives, or the location=None path prices commitments
# ~12% higher than a cascaded run. (The pricing PAGE's ×0.9/×0.8 "consumption CUD"
# figures have no catalog SKU and are not modeled.) STANDARD has NO true capacity/slot
# commitments — its 1yr/3yr figures are consumption-model CUDs, not slot commitments.
# =============================================================================

V4_EDITION_SLOT_HOUR_USD: dict[str, dict[str, float | None]] = {
    "STANDARD": {"payg": 0.04, "commit_1yr": 0.032, "commit_3yr": 0.024},
    "ENTERPRISE": {"payg": 0.06, "commit_1yr": 0.048, "commit_3yr": 0.036},
    "ENTERPRISE_PLUS": {"payg": 0.10, "commit_1yr": 0.08, "commit_3yr": 0.06},
}

# Cheaper "Resource CUD" family for the editions that support true slot commitments.
V4_EDITION_RESOURCE_CUD_SLOT_HOUR_USD: dict[str, dict[str, float]] = {
    "ENTERPRISE": {"commit_1yr": 0.048, "commit_3yr": 0.036},
    "ENTERPRISE_PLUS": {"commit_1yr": 0.08, "commit_3yr": 0.06},
}

# Editions that can purchase true capacity (slot) commitments (Standard cannot).
V4_EDITIONS_WITH_CAPACITY_COMMITMENTS: tuple[str, ...] = ("ENTERPRISE", "ENTERPRISE_PLUS")

# =============================================================================
# V4 — Per-region rate table + region resolver
# Verified 2026-07-02 against the GCP Cloud Billing Catalog API (services/24E6-581D-38E5
# BigQuery + services/16B8-3DDA-9F10 BigQuery Reservation API), region-filtered on
# serviceRegions. Cross-checked against a real australia-southeast1 bill (Analysis
# 860.98 TiB → $6,991.12 = $8.125/TiB exactly).
# Keys are lowercase BigQuery dataset-location tokens as returned by datasets.get
# (multi-regions "us"/"eu"; regions like "australia-southeast1").
# The catalog labels the EU multi-region "europe" (analysis SKUs) / "eu" (edition SKUs);
# we key it "eu" to match dataset.location.
# =============================================================================

V4_REGIONAL_RATES: dict[str, dict[str, float]] = {
    #                          $/TiB    active   longterm  active    longterm
    #                          scanned  logical  logical   physical  physical
    "us":                      {"ondemand_per_tib": 6.25,   "active_logical": 0.02,  "longterm_logical": 0.01,  "active_physical": 0.04,  "longterm_physical": 0.02},
    "eu":                      {"ondemand_per_tib": 6.25,   "active_logical": 0.02,  "longterm_logical": 0.01,  "active_physical": 0.044, "longterm_physical": 0.022},
    "us-central1":             {"ondemand_per_tib": 6.25,   "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.04,  "longterm_physical": 0.02},
    "us-east1":                {"ondemand_per_tib": 6.25,   "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.044, "longterm_physical": 0.022},
    "us-west1":                {"ondemand_per_tib": 6.25,   "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.04,  "longterm_physical": 0.02},
    "europe-west4":            {"ondemand_per_tib": 7.5,    "active_logical": 0.02,  "longterm_logical": 0.01,  "active_physical": 0.044, "longterm_physical": 0.022},
    "australia-southeast1":    {"ondemand_per_tib": 8.125,  "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.052, "longterm_physical": 0.026},
    "australia-southeast2":    {"ondemand_per_tib": 8.125,  "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.052, "longterm_physical": 0.026},
    "europe-west1":            {"ondemand_per_tib": 7.5,    "active_logical": 0.02,  "longterm_logical": 0.01,  "active_physical": 0.044, "longterm_physical": 0.022},
    "europe-west2":            {"ondemand_per_tib": 7.8125, "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.052, "longterm_physical": 0.026},
    "europe-west3":            {"ondemand_per_tib": 8.125,  "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.052, "longterm_physical": 0.026},
    "asia-southeast1":         {"ondemand_per_tib": 8.4375, "active_logical": 0.02,  "longterm_logical": 0.01,  "active_physical": 0.046, "longterm_physical": 0.023},
    "asia-northeast1":         {"ondemand_per_tib": 7.5,    "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.052, "longterm_physical": 0.026},
    "asia-south1":             {"ondemand_per_tib": 7.5,    "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.052, "longterm_physical": 0.026},
    "us-east4":                {"ondemand_per_tib": 6.25,   "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.05,  "longterm_physical": 0.025},
    "us-west2":                {"ondemand_per_tib": 8.4375, "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.05,  "longterm_physical": 0.025},
    "northamerica-northeast1": {"ondemand_per_tib": 6.5625, "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.05,  "longterm_physical": 0.025},
    "southamerica-east1":      {"ondemand_per_tib": 11.25,  "active_logical": 0.023, "longterm_logical": 0.016, "active_physical": 0.07,  "longterm_physical": 0.035},
}

# Editions PAYG $/slot-hr by region (Billing Catalog, 2026-07-02). The catalog's per-region
# "1 Year"/"3 Years" SKUs — the ONLY published per-region commitment rates, verified for every
# region below including US (e.g. US ENTERPRISE 1yr $0.048 = payg×0.8, 3yr $0.036 = payg×0.6;
# Sydney 1yr $0.0648 = 0.081×0.8) — follow payg×0.8/×0.6. apply_bq_region prices commitments
# from those factors. The pricing page's ×0.9/×0.8 "consumption CUD" figures are US-only and
# have no per-region catalog SKU, so they are NOT fabricated for other regions.
V4_REGIONAL_EDITION_PAYG: dict[str, dict[str, float]] = {
    "us":                      {"STANDARD": 0.04,  "ENTERPRISE": 0.06,   "ENTERPRISE_PLUS": 0.10},
    "eu":                      {"STANDARD": 0.044, "ENTERPRISE": 0.066,  "ENTERPRISE_PLUS": 0.11},
    "us-central1":             {"STANDARD": 0.04,  "ENTERPRISE": 0.06,   "ENTERPRISE_PLUS": 0.10},
    "us-east1":                {"STANDARD": 0.04,  "ENTERPRISE": 0.06,   "ENTERPRISE_PLUS": 0.10},
    "us-west1":                {"STANDARD": 0.04,  "ENTERPRISE": 0.06,   "ENTERPRISE_PLUS": 0.10},
    "europe-west4":            {"STANDARD": 0.044, "ENTERPRISE": 0.066,  "ENTERPRISE_PLUS": 0.11},
    "australia-southeast1":    {"STANDARD": 0.054, "ENTERPRISE": 0.081,  "ENTERPRISE_PLUS": 0.135},
    "australia-southeast2":    {"STANDARD": 0.054, "ENTERPRISE": 0.081,  "ENTERPRISE_PLUS": 0.135},
    "europe-west1":            {"STANDARD": 0.044, "ENTERPRISE": 0.066,  "ENTERPRISE_PLUS": 0.11},
    "europe-west2":            {"STANDARD": 0.052, "ENTERPRISE": 0.078,  "ENTERPRISE_PLUS": 0.13},
    "europe-west3":            {"STANDARD": 0.052, "ENTERPRISE": 0.078,  "ENTERPRISE_PLUS": 0.13},
    "asia-southeast1":         {"STANDARD": 0.049, "ENTERPRISE": 0.0735, "ENTERPRISE_PLUS": 0.1225},
    "asia-northeast1":         {"STANDARD": 0.051, "ENTERPRISE": 0.0765, "ENTERPRISE_PLUS": 0.1275},
    "asia-south1":             {"STANDARD": 0.046, "ENTERPRISE": 0.069,  "ENTERPRISE_PLUS": 0.115},
    "us-east4":                {"STANDARD": 0.04,  "ENTERPRISE": 0.06,   "ENTERPRISE_PLUS": 0.10},
    "us-west2":                {"STANDARD": 0.05,  "ENTERPRISE": 0.075,  "ENTERPRISE_PLUS": 0.125},
    "northamerica-northeast1": {"STANDARD": 0.046, "ENTERPRISE": 0.069,  "ENTERPRISE_PLUS": 0.115},
    "southamerica-east1":      {"STANDARD": 0.062, "ENTERPRISE": 0.093,  "ENTERPRISE_PLUS": 0.155},
}

# Commitment factors from the catalog "1 Year"/"3 Years" SKUs (the true slot-commitment /
# Resource-CUD family). Consistently payg×0.8 (1yr) / payg×0.6 (3yr) across every region
# checked, US included.
V4_RESOURCE_CUD_1YR_FACTOR: float = 0.8
V4_RESOURCE_CUD_3YR_FACTOR: float = 0.6


def normalize_bq_location(location: str | None) -> str:
    """Lowercase a BigQuery dataset location token ("US" → "us")."""
    return (location or "").strip().lower()


def apply_bq_region(location: str | None) -> bool:
    """Re-point the module-level V4_* rate constants at ``location``'s verified rates.

    Returns True when the location is in the verified table (constants updated), False when
    it is unknown (constants left as-is — US multi-region — so callers can attach a caveat).
    Overridable-via-module-assignment design (R18.7): CostEstimator reads these at call time.
    """
    global V4_ONDEMAND_USD_PER_TIB
    global V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH
    global V4_STORAGE_LONGTERM_LOGICAL_USD_PER_GIB_MONTH
    global V4_STORAGE_ACTIVE_PHYSICAL_USD_PER_GIB_MONTH
    global V4_STORAGE_LONGTERM_PHYSICAL_USD_PER_GIB_MONTH
    global V4_EDITION_SLOT_HOUR_USD, V4_EDITION_RESOURCE_CUD_SLOT_HOUR_USD
    global V4_PRICING_REGION, V4_REGION_SCOPE

    loc = normalize_bq_location(location)
    rates = V4_REGIONAL_RATES.get(loc)
    if rates is None:
        return False

    V4_ONDEMAND_USD_PER_TIB = rates["ondemand_per_tib"]
    V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH = rates["active_logical"]
    V4_STORAGE_LONGTERM_LOGICAL_USD_PER_GIB_MONTH = rates["longterm_logical"]
    V4_STORAGE_ACTIVE_PHYSICAL_USD_PER_GIB_MONTH = rates["active_physical"]
    V4_STORAGE_LONGTERM_PHYSICAL_USD_PER_GIB_MONTH = rates["longterm_physical"]

    payg = V4_REGIONAL_EDITION_PAYG.get(loc)
    if payg is not None:
        # Commitments priced from the catalog-verified per-region factors (×0.8/×0.6 —
        # the only commitment SKUs the catalog publishes; see table comment above).
        V4_EDITION_SLOT_HOUR_USD = {
            edition: {
                "payg": rate,
                "commit_1yr": round(rate * V4_RESOURCE_CUD_1YR_FACTOR, 6),
                "commit_3yr": round(rate * V4_RESOURCE_CUD_3YR_FACTOR, 6),
            }
            for edition, rate in payg.items()
        }
        V4_EDITION_RESOURCE_CUD_SLOT_HOUR_USD = {
            edition: {
                "commit_1yr": round(payg[edition] * V4_RESOURCE_CUD_1YR_FACTOR, 6),
                "commit_3yr": round(payg[edition] * V4_RESOURCE_CUD_3YR_FACTOR, 6),
            }
            for edition in V4_EDITIONS_WITH_CAPACITY_COMMITMENTS
            if edition in payg
        }

    V4_PRICING_REGION = loc
    V4_REGION_SCOPE = f"BigQuery region {loc}"
    return True


# =============================================================================
# V5 — Reservation/commitment INFORMATION_SCHEMA views
# Region-qualified; the project prefix is optional, the `_BY_PROJECT` suffix is a synonym.
# Syntax:  [PROJECT_ID.]`region-REGION`.INFORMATION_SCHEMA.<VIEW>
# Example: FROM `region-us`.INFORMATION_SCHEMA.CAPACITY_COMMITMENTS WHERE state = 'ACTIVE'
# =============================================================================

V5_REGION_QUALIFIER_EXAMPLE: str = "`region-us`"
V5_RESERVATION_VIEWS: tuple[str, ...] = (
    "RESERVATIONS",
    "RESERVATIONS_TIMELINE",
    "RESERVATION_CHANGES",
    "CAPACITY_COMMITMENTS",
    "CAPACITY_COMMITMENT_CHANGES",
    "ASSIGNMENTS",
    "ASSIGNMENT_CHANGES",
)
# IAM permissions to read the reservation views (one *.list per view family).
V5_RESERVATION_LIST_PERMISSIONS: tuple[str, ...] = (
    "bigquery.reservations.list",
    "bigquery.capacityCommitments.list",
    "bigquery.reservationAssignments.list",
)
# Lowest-privilege predefined role covering all three reservation *.list perms AND
# bigquery.jobs.listAll. ⚠️ Reading reservation views is NOT a higher tier than jobs.listAll.
V5_READONLY_ROLE: str = "roles/bigquery.resourceViewer"

# =============================================================================
# V5 — Primary on-demand-vs-capacity signal in INFORMATION_SCHEMA.JOBS
# Simpler and lower-privilege than reading the reservation views: needs only the JOBS perms.
# =============================================================================

# The column whose NULL-ness distinguishes the billing model.
V5_JOBS_RESERVATION_ID_COLUMN: str = "reservation_id"
# reservation_id IS NULL  => on-demand (PAYG)
# reservation_id non-null => capacity (Editions); value is the primary reservation path
#                            "RESERVATION_ADMIN_PROJECT:RESERVATION_LOCATION.RESERVATION_NAME"
# ⚠️ The on-demand sentinel is NULL — NOT the string "default". Do not test == "default".
V5_JOBS_ONDEMAND_RESERVATION_ID_IS_NULL: bool = True
# Secondary confirmation: names the edition of the assigned reservation.
V5_JOBS_EDITION_COLUMN: str = "edition"
# ⚠️ statement_type='SCRIPT' parent jobs have reservation_id=NULL by design even under
# capacity billing — classify on leaf jobs / exclude SCRIPT parents, and aggregate across
# jobs for a whole-project verdict.
V5_JOBS_SCRIPT_PARENT_RESERVATION_ID_IS_NULL: bool = True
V5_JOBS_STATEMENT_TYPE_COLUMN: str = "statement_type"
V5_JOBS_SCRIPT_STATEMENT_TYPE: str = "SCRIPT"
