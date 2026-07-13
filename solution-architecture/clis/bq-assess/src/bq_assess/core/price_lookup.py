"""Live pricing lookup — AWS Price List API + GCP Cloud Billing Catalog.

Queries public/authenticated pricing APIs at runtime to ensure cost estimates use
current rates. Falls back to hardcoded constants (with staleness warning) when APIs
are unreachable.

Architecture:
- AWS: Public Price List Bulk JSON API (no auth, ~2MB download per service, cached).
  Regional offer files — the URL embeds ``aws_region`` so rates match the Source's geography.
- GCP: Cloud Billing Catalog API via ADC (same auth the scanner uses). SKUs are matched on
  ``serviceRegions`` against ``bq_location`` — the catalog returns every region's SKUs in one
  list, so an unfiltered description match silently returns an arbitrary region's rate
  (the bug behind the Montu Sydney-priced-as-US underestimate, fixed 2026-07-02).
- Cache: JSON file in user's home dir, 24h TTL, keyed by (aws_region, bq_location)
- Fallback: hardcoded constants in pricing_constants.py / cost_constants.py (which the
  region cascade has already pointed at the right region before this lookup runs)

The lookup returns a PricingRates dataclass that the CostEstimator consumes directly,
replacing the module-level constants for the current run.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".bq-assess"
_CACHE_FILE = _CACHE_DIR / "pricing-cache.json"
_CACHE_TTL_SECONDS = 86_400  # 24 hours

# Aggregate wall-clock budget for a full live lookup (AWS Redshift + AWS S3 + paginated
# GCP catalog). Each individual HTTP call already has a 30s socket timeout, but a paginated
# GCP fetch can chain several of those — this bounds the TOTAL so the CLI never stalls for
# minutes on a slow API. On expiry we fall back to the region-cascaded hardcoded rates.
_LIVE_FETCH_BUDGET_SECONDS = 45.0

# AWS Price List API endpoint template (public, no auth). The pricing.us-east-1 host serves
# ALL regions' offer files; the path segment selects the region.
_AWS_OFFER_URL_TEMPLATE = (
    "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{service}/current/{region}/index.json"
)

# GCP Cloud Billing Catalog API
_GCP_BILLING_CATALOG_URL = "https://cloudbilling.googleapis.com/v1/services"
_GCP_BQ_SERVICE_NAME = "services/24E6-581D-38E5"  # BigQuery service ID


@dataclass
class AWSRates:
    """Live AWS pricing rates for Redshift + S3."""
    rpu_hour_usd: float = 0.0
    managed_storage_usd_per_gb: float = 0.0
    ra3_xlplus_ondemand: float = 0.0
    ra3_xlplus_1yr: float = 0.0
    ra3_xlplus_3yr: float = 0.0
    ra3_4xl_ondemand: float = 0.0
    ra3_4xl_1yr: float = 0.0
    ra3_4xl_3yr: float = 0.0
    ra3_16xl_ondemand: float = 0.0
    ra3_16xl_1yr: float = 0.0
    ra3_16xl_3yr: float = 0.0
    # RG Graviton4 instances
    rg_xl_ondemand: float = 0.0
    rg_xl_1yr: float = 0.0
    rg_xl_3yr: float = 0.0
    rg_4xl_ondemand: float = 0.0
    rg_4xl_1yr: float = 0.0
    rg_4xl_3yr: float = 0.0
    rg_16xl_ondemand: float = 0.0
    rg_16xl_1yr: float = 0.0
    rg_16xl_3yr: float = 0.0
    s3_tables_tier1: float = 0.0
    s3_tables_tier2: float = 0.0
    s3_tables_tier3: float = 0.0
    fetched_at: str = ""
    source: str = "hardcoded"


@dataclass
class GCPRates:
    """Live GCP pricing rates for BigQuery."""
    ondemand_usd_per_tib: float = 0.0
    storage_active_logical_usd_per_gib: float = 0.0
    storage_longterm_logical_usd_per_gib: float = 0.0
    fetched_at: str = ""
    source: str = "hardcoded"


@dataclass
class PricingRates:
    """Combined live pricing rates from both clouds.

    ``aws_region`` / ``bq_location`` record WHICH geography the rates were fetched for —
    apply_live_rates stamps the module region tags from them so the tags stay a true
    invariant ("tag == region the constants reflect") across all writers.
    """
    aws: AWSRates = field(default_factory=AWSRates)
    gcp: GCPRates = field(default_factory=GCPRates)
    is_live: bool = False
    staleness_warning: str = ""
    aws_region: str = "us-east-1"
    bq_location: str = "us"


class PriceLookup:
    """Fetch live pricing from AWS + GCP APIs with caching and graceful fallback.

    ``aws_region`` selects the AWS Price List offer file; ``bq_location`` (a BigQuery
    dataset location token like "us" or "australia-southeast1") filters GCP Billing
    Catalog SKUs by ``serviceRegions``. Callers should pass the Source's detected
    location and its mapped AWS region (``cost_constants.bq_location_to_aws_region``).
    """

    def __init__(self, aws_region: str = "us-east-1", bq_location: str = "us",
                 use_cache: bool = True):
        self._aws_region = aws_region
        self._bq_location = (bq_location or "us").strip().lower()
        self._use_cache = use_cache

    def fetch(self, gcp_client=None) -> PricingRates:
        """Fetch live rates from both APIs. Returns hardcoded fallback on failure."""
        # Check cache first
        if self._use_cache:
            cached = self._read_cache()
            if cached is not None:
                return cached

        rates = PricingRates(aws_region=self._aws_region, bq_location=self._bq_location)

        # Fetch AWS rates (no auth needed)
        aws_rates = self._fetch_aws_rates()
        if aws_rates is not None:
            rates.aws = aws_rates
            rates.is_live = True

        # Fetch GCP rates (needs ADC)
        if gcp_client is not None:
            gcp_rates = self._fetch_gcp_rates(gcp_client)
            if gcp_rates is not None:
                rates.gcp = gcp_rates

        # Fall back to hardcoded if either failed
        if rates.aws.source == "hardcoded":
            rates.aws = self._hardcoded_aws()
            rates.staleness_warning = self._staleness_note("AWS", rates.aws.fetched_at)
        if rates.gcp.source == "hardcoded":
            rates.gcp = self._hardcoded_gcp()
            if not rates.staleness_warning:
                rates.staleness_warning = self._staleness_note("GCP", rates.gcp.fetched_at)

        # Cache the result — but ONLY when BOTH halves are genuinely live. Caching a
        # mixed entry (AWS live + GCP hardcoded fallback) under a 24h TTL pins the
        # fallback: every run that day would skip the GCP fetch even after a transient
        # network/auth issue clears, while the console claims live pricing.
        both_live = (
            not rates.aws.source.startswith("hardcoded")
            and not rates.gcp.source.startswith("hardcoded")
        )
        if self._use_cache and rates.is_live and both_live:
            self._write_cache(rates)

        return rates

    # ================================================================ AWS

    def _fetch_aws_rates(self) -> AWSRates | None:
        """Query the AWS Price List API for Redshift rates (public, no auth)."""
        import urllib.request
        import urllib.error

        try:
            logger.info("Fetching AWS Redshift pricing from Price List API (%s)...", self._aws_region)
            url = _AWS_OFFER_URL_TEMPLATE.format(service="AmazonRedshift", region=self._aws_region)
            req = urllib.request.Request(url)
            req.add_header("Accept-Encoding", "gzip")
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - hardcoded https AWS Price List API URL, no user input
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
            logger.warning("AWS Price List API unreachable: %s — using hardcoded rates", exc)
            return None

        try:
            return self._parse_aws_redshift(data)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse AWS pricing response: %s", exc)
            return None

    def _parse_aws_redshift(self, data: dict) -> AWSRates:
        """Extract Redshift rates from the Price List API JSON."""
        products = data.get("products", {})
        terms = data.get("terms", {})
        on_demand_terms = terms.get("OnDemand", {})
        reserved_terms = terms.get("Reserved", {})

        rates = AWSRates(
            fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source="AWS Price List API",
        )

        # Find Redshift Serverless RPU rate. Match the exact usagetype suffix: regional
        # offer files also carry capacity-reservation SKUs like "ServerlessUsage-CR-1YR-AU"
        # (an all-upfront $2,716/RPU figure) that a substring match would grab first.
        for sku, product in products.items():
            attrs = product.get("attributes", {})
            usage_type = attrs.get("usagetype", "")
            if usage_type.endswith("Redshift:ServerlessUsage") and attrs.get("locationType") == "AWS Region":
                price = self._extract_ondemand_price(sku, on_demand_terms)
                if price:
                    rates.rpu_hour_usd = price
                    break

        # Find RA3 node rates
        node_map = {
            "ra3.xlplus": ("ra3_xlplus_ondemand", "ra3_xlplus_1yr", "ra3_xlplus_3yr"),
            "ra3.4xlarge": ("ra3_4xl_ondemand", "ra3_4xl_1yr", "ra3_4xl_3yr"),
            "ra3.16xlarge": ("ra3_16xl_ondemand", "ra3_16xl_1yr", "ra3_16xl_3yr"),
        }

        for sku, product in products.items():
            attrs = product.get("attributes", {})
            instance_type = attrs.get("instanceType", "")
            usage_type = attrs.get("usagetype", "")

            if instance_type not in node_map:
                continue
            if "Node" not in usage_type:
                continue

            od_field, ri1_field, ri3_field = node_map[instance_type]

            # On-demand price
            od_price = self._extract_ondemand_price(sku, on_demand_terms)
            if od_price:
                setattr(rates, od_field, od_price)

            # Reserved prices
            ri_prices = self._extract_reserved_prices(sku, reserved_terms)
            if ri_prices.get("1yr"):
                setattr(rates, ri1_field, ri_prices["1yr"])
            if ri_prices.get("3yr"):
                setattr(rates, ri3_field, ri_prices["3yr"])

        # Managed storage
        for sku, product in products.items():
            attrs = product.get("attributes", {})
            usage_type = attrs.get("usagetype", "")
            if "RMS" in usage_type or "ManagedStorage" in usage_type:
                price = self._extract_ondemand_price(sku, on_demand_terms)
                if price:
                    rates.managed_storage_usd_per_gb = price
                    break

        # Fetch S3 Tables pricing separately
        s3_rates = self._fetch_s3_tables_rates()
        if s3_rates:
            rates.s3_tables_tier1 = s3_rates.get("tier1", 0)
            rates.s3_tables_tier2 = s3_rates.get("tier2", 0)
            rates.s3_tables_tier3 = s3_rates.get("tier3", 0)

        return rates

    def _fetch_s3_tables_rates(self) -> dict | None:
        """Fetch S3 Tables storage rates from the S3 Price List API."""
        import urllib.request
        import urllib.error

        try:
            url = _AWS_OFFER_URL_TEMPLATE.format(service="AmazonS3", region=self._aws_region)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - hardcoded https AWS Price List API URL, no user input
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
            return None

        return self._parse_s3_tables_tiers(
            data.get("products", {}), data.get("terms", {}).get("OnDemand", {})
        )

    @staticmethod
    def _parse_s3_tables_tiers(products: dict, terms: dict) -> dict | None:
        """Extract the three S3 Tables Standard storage tiers from an offer file."""
        tiers = {}
        for sku, product in products.items():
            attrs = product.get("attributes", {})
            usage_type = attrs.get("usagetype", "")

            # Exact-suffix match: offer files also carry Intelligent-Tiering variants
            # (…Tables-TimedStorage-INT-FA-ByteHrs etc.) that a substring match would
            # conflate with the Standard tiers.
            if not usage_type.endswith("Tables-TimedStorage-ByteHrs"):
                continue

            # One SKU carries all three tiers as separate priceDimensions — read each
            # dimension's OWN price (a single extracted price assigned to every tier
            # would bill tier-2/3 storage at the tier-1 rate).
            for offer in terms.get(sku, {}).values():
                for dim in offer.get("priceDimensions", {}).values():
                    price = float(dim.get("pricePerUnit", {}).get("USD", "0") or "0")
                    if price <= 0:
                        continue
                    begin = float(dim.get("beginRange", "0") or "0")
                    if begin == 0:
                        tiers["tier1"] = price
                    elif begin <= 51200:  # 50 TB in GB
                        tiers["tier2"] = price
                    else:
                        tiers["tier3"] = price

        return tiers if tiers else None

    def _extract_ondemand_price(self, sku: str, on_demand_terms: dict) -> float:
        """Extract the hourly/monthly on-demand price for a SKU."""
        sku_terms = on_demand_terms.get(sku, {})
        for offer_term in sku_terms.values():
            price_dims = offer_term.get("priceDimensions", {})
            for dim in price_dims.values():
                price_str = dim.get("pricePerUnit", {}).get("USD", "0")
                price = float(price_str)
                if price > 0:
                    return price
        return 0.0

    def _extract_reserved_prices(self, sku: str, reserved_terms: dict) -> dict:
        """Extract 1yr and 3yr no-upfront RI effective hourly rates."""
        result = {}
        sku_terms = reserved_terms.get(sku, {})

        for offer_key, offer in sku_terms.items():
            term_attrs = offer.get("termAttributes", {})
            lease_length = term_attrs.get("LeaseContractLength", "")
            purchase_option = term_attrs.get("PurchaseOption", "")

            if purchase_option != "No Upfront":
                continue

            price_dims = offer.get("priceDimensions", {})
            for dim in price_dims.values():
                if dim.get("unit", "").lower() in ("hrs", "hr", "hour"):
                    price_str = dim.get("pricePerUnit", {}).get("USD", "0")
                    price = float(price_str)
                    if price > 0:
                        if "1yr" in lease_length or "1 yr" in lease_length.lower():
                            result["1yr"] = price
                        elif "3yr" in lease_length or "3 yr" in lease_length.lower():
                            result["3yr"] = price

        return result

    # ================================================================ GCP

    def _fetch_gcp_rates(self, client) -> GCPRates | None:
        """Query GCP Cloud Billing Catalog for BigQuery rates using existing ADC."""
        try:
            from google.auth.transport.requests import AuthorizedSession
            import google.auth

            credentials = client._credentials if hasattr(client, "_credentials") else None
            if credentials is None:
                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-billing.readonly"]
                )

            session = AuthorizedSession(credentials)
            logger.info(
                "Fetching GCP BigQuery pricing from Cloud Billing Catalog (%s)...",
                self._bq_location,
            )

            # List ALL SKUs for the BigQuery service (paginated — a single unpaginated call
            # returns only the first page and silently misses most regions' SKUs).
            url = f"https://cloudbilling.googleapis.com/v1/{_GCP_BQ_SERVICE_NAME}/skus"
            skus: list[dict] = []
            page_token = None
            while True:
                params = {"currencyCode": "USD", "pageSize": 5000}
                if page_token:
                    params["pageToken"] = page_token
                resp = session.get(url, params=params, timeout=30)
                if resp.status_code != 200:
                    logger.warning("GCP Billing API returned %d: %s", resp.status_code, resp.text[:200])
                    return None
                data = resp.json()
                skus.extend(data.get("skus", []))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            rates = self._parse_gcp_skus(skus)
            # A parse that matched no analysis SKU is NOT a live result: returning it
            # would skip the hardcoded fallback, stamp V4_CONFIRMED_DATE with today via
            # apply_live_rates, and pin zeroed rates in the 24h cache. Treat as a miss.
            if rates.ondemand_usd_per_tib <= 0:
                logger.warning(
                    "No on-demand analysis SKU matched region %r in the Billing Catalog "
                    "— using hardcoded regional rates", self._bq_location,
                )
                return None
            return rates
        except Exception as exc:
            logger.warning("GCP Billing API lookup failed: %s — using hardcoded rates", exc)
            return None

    def _gcp_region_tokens(self) -> tuple[str, ...]:
        """serviceRegions tokens that identify the Source's location in the catalog.

        The catalog labels the EU multi-region "europe" on analysis/storage SKUs (dataset
        location token is "eu"); everything else matches the location token directly.
        """
        if self._bq_location == "eu":
            return ("eu", "europe")
        return (self._bq_location,)

    def _parse_gcp_skus(self, skus: list[dict]) -> GCPRates:
        """Extract BQ pricing for the Source's region from the Catalog SKU list.

        Filters on ``serviceRegions`` — the catalog returns every region's SKUs, and the
        description alone does not disambiguate ("Analysis" exists per-region). Matches on
        the catalog's ``category.resourceGroup`` (OnDemandAnalysis / ActiveStorage /
        LongTermStorage), which is stabler than description keywords.
        """
        rates = GCPRates(
            fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source=f"GCP Cloud Billing Catalog API ({self._bq_location})",
        )
        region_tokens = self._gcp_region_tokens()

        for sku in skus:
            regions = sku.get("serviceRegions", [])
            if not any(tok in regions for tok in region_tokens):
                continue

            desc = sku.get("description", "").lower()
            group = sku.get("category", {}).get("resourceGroup", "")

            pricing_info = sku.get("pricingInfo", [])
            if not pricing_info:
                continue
            price_expr = pricing_info[0].get("pricingExpression", {})
            tiered_rates = price_expr.get("tieredRates", [])
            if not tiered_rates:
                continue

            # Use the last tier (the rate after any free tier)
            rate = tiered_rates[-1] if len(tiered_rates) > 1 else tiered_rates[0]
            unit_price = rate.get("unitPrice", {})
            nanos = unit_price.get("nanos", 0)
            units = int(unit_price.get("units", "0") or "0")
            price = units + nanos / 1_000_000_000
            if price <= 0:
                continue

            usage_unit = price_expr.get("usageUnit", "").lower()

            if group == "OnDemandAnalysis" and desc.startswith("analysis"):
                # Catalog unit is TiBy (per-TiB); normalize other units defensively.
                if usage_unit == "tiby" or "tebibyte" in usage_unit:
                    rates.ondemand_usd_per_tib = price
                elif "miby" in usage_unit or "mebibyte" in usage_unit:
                    rates.ondemand_usd_per_tib = price * (1024 ** 2)
                elif usage_unit in ("by", "byte", "bytes"):
                    rates.ondemand_usd_per_tib = price * (1024 ** 4)
                else:
                    rates.ondemand_usd_per_tib = price

            elif group == "ActiveStorage" and "logical" in desc:
                if usage_unit in ("by", "byte", "bytes"):
                    rates.storage_active_logical_usd_per_gib = price * (1024 ** 3)
                else:  # GiBy.mo
                    rates.storage_active_logical_usd_per_gib = price

            elif group == "LongTermStorage" and "logical" in desc:
                if usage_unit in ("by", "byte", "bytes"):
                    rates.storage_longterm_logical_usd_per_gib = price * (1024 ** 3)
                else:
                    rates.storage_longterm_logical_usd_per_gib = price

        return rates

    # ================================================================ Hardcoded Fallback

    def _hardcoded_aws(self) -> AWSRates:
        """Return hardcoded AWS rates from cost_constants.py.

        The collector distribution ships without bq_assess.engine — there the
        fallback returns a default-valued AWSRates still marked hardcoded. Safe:
        apply_live_rates never applies hardcoded halves, and the report side
        (which has the engine) re-derives its own regional rates.
        """
        try:
            from bq_assess.engine.redshift import cost_constants as k
        except ImportError:
            return AWSRates(source="hardcoded (engine unavailable in collector)")

        nodes = k.V6_RA3_NODE_TYPES
        rg = k.V7_RG_NODE_TYPES
        return AWSRates(
            rpu_hour_usd=k.V1_RPU_HOUR_USD,
            managed_storage_usd_per_gb=k.V6_MANAGED_STORAGE_USD_PER_GB_MONTH,
            ra3_xlplus_ondemand=nodes["ra3.xlplus"]["ondemand_usd_per_node_hour"],
            ra3_xlplus_1yr=nodes["ra3.xlplus"]["ri_1yr_usd_per_node_hour"],
            ra3_xlplus_3yr=nodes["ra3.xlplus"]["ri_3yr_usd_per_node_hour"],
            ra3_4xl_ondemand=nodes["ra3.4xlarge"]["ondemand_usd_per_node_hour"],
            ra3_4xl_1yr=nodes["ra3.4xlarge"]["ri_1yr_usd_per_node_hour"],
            ra3_4xl_3yr=nodes["ra3.4xlarge"]["ri_3yr_usd_per_node_hour"],
            ra3_16xl_ondemand=nodes["ra3.16xlarge"]["ondemand_usd_per_node_hour"],
            ra3_16xl_1yr=nodes["ra3.16xlarge"]["ri_1yr_usd_per_node_hour"],
            ra3_16xl_3yr=nodes["ra3.16xlarge"]["ri_3yr_usd_per_node_hour"],
            rg_xl_ondemand=rg["rg.xlarge"]["ondemand_usd_per_node_hour"],
            rg_xl_1yr=rg["rg.xlarge"]["ri_1yr_usd_per_node_hour"],
            rg_xl_3yr=rg["rg.xlarge"]["ri_3yr_usd_per_node_hour"],
            rg_4xl_ondemand=rg["rg.4xlarge"]["ondemand_usd_per_node_hour"],
            rg_4xl_1yr=rg["rg.4xlarge"]["ri_1yr_usd_per_node_hour"],
            rg_4xl_3yr=rg["rg.4xlarge"]["ri_3yr_usd_per_node_hour"],
            rg_16xl_ondemand=rg["rg.16xlarge"]["ondemand_usd_per_node_hour"],
            rg_16xl_1yr=rg["rg.16xlarge"]["ri_1yr_usd_per_node_hour"],
            rg_16xl_3yr=rg["rg.16xlarge"]["ri_3yr_usd_per_node_hour"],
            s3_tables_tier1=k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER1,
            s3_tables_tier2=k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER2,
            s3_tables_tier3=k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER3,
            fetched_at=k.AWS_CONFIRMED_DATE,
            source=f"hardcoded (verified {k.AWS_CONFIRMED_DATE})",
        )

    def _hardcoded_gcp(self) -> GCPRates:
        """Return hardcoded GCP rates from pricing_constants.py."""
        from bq_assess.core import pricing_constants as v4

        return GCPRates(
            ondemand_usd_per_tib=v4.V4_ONDEMAND_USD_PER_TIB,
            storage_active_logical_usd_per_gib=v4.V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH,
            storage_longterm_logical_usd_per_gib=v4.V4_STORAGE_LONGTERM_LOGICAL_USD_PER_GIB_MONTH,
            fetched_at=v4.V4_CONFIRMED_DATE,
            source=f"hardcoded (verified {v4.V4_CONFIRMED_DATE})",
        )

    def _staleness_note(self, provider: str, date_str: str) -> str:
        """Generate a staleness warning if rates are old."""
        if not date_str:
            return f"{provider} pricing could not be fetched — using hardcoded rates (date unknown)"
        try:
            fetched = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - fetched).days
            if age_days > 90:
                return (
                    f"{provider} pricing is {age_days} days old (verified {date_str}). "
                    f"Run with internet access to refresh from the {provider} Price List API."
                )
        except ValueError:
            pass
        return ""

    # ================================================================ Cache

    def _cache_key(self) -> str:
        """Rates are region-specific — one cache entry per (aws_region, bq_location)."""
        return f"{self._aws_region}|{self._bq_location}"

    def _read_cache(self) -> PricingRates | None:
        """Read cached rates for this region pair if within TTL."""
        if not _CACHE_FILE.exists():
            return None
        try:
            cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            data = cache.get(self._cache_key())
            if not data:
                return None
            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at > _CACHE_TTL_SECONDS:
                return None
            return self._deserialize_rates(data)
        except (json.JSONDecodeError, KeyError, OSError, AttributeError):
            return None

    def _write_cache(self, rates: PricingRates) -> None:
        """Write rates for this region pair into the cache file (merging other entries)."""
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache: dict = {}
            if _CACHE_FILE.exists():
                try:
                    existing = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                    # Pre-2026-07 cache files were a flat single-region dict — discard them.
                    if isinstance(existing, dict) and "aws" not in existing:
                        cache = existing
                except (json.JSONDecodeError, OSError):
                    pass
            data = self._serialize_rates(rates)
            data["cached_at"] = time.time()
            cache[self._cache_key()] = data
            _CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.debug("Could not write pricing cache: %s", exc)

    def _serialize_rates(self, rates: PricingRates) -> dict:
        """Serialize PricingRates to a JSON-safe dict (all dataclass fields, RG included)."""
        return rates_to_dict(rates)

    def _deserialize_rates(self, data: dict) -> PricingRates:
        """Deserialize a cached dict back to PricingRates."""
        return rates_from_dict(
            data, default_aws_region=self._aws_region, default_bq_location=self._bq_location
        )


def rates_to_dict(rates: PricingRates) -> dict:
    """Serialize PricingRates to a JSON-safe dict (pricing cache + bundle rates.json)."""
    return {
        "aws": {f: getattr(rates.aws, f) for f in AWSRates.__dataclass_fields__},
        "gcp": {f: getattr(rates.gcp, f) for f in GCPRates.__dataclass_fields__},
        "is_live": rates.is_live,
        "staleness_warning": rates.staleness_warning,
        "aws_region": rates.aws_region,
        "bq_location": rates.bq_location,
    }


def rates_from_dict(
    data: dict,
    *,
    default_aws_region: str = "us-east-1",
    default_bq_location: str = "us",
) -> PricingRates:
    """Deserialize a rates dict (pricing cache entry or bundle rates.json)."""
    aws_data = data.get("aws", {})
    gcp_data = data.get("gcp", {})
    return PricingRates(
        aws=AWSRates(**{k: v for k, v in aws_data.items() if k in AWSRates.__dataclass_fields__}),
        gcp=GCPRates(**{k: v for k, v in gcp_data.items() if k in GCPRates.__dataclass_fields__}),
        is_live=data.get("is_live", False),
        staleness_warning=data.get("staleness_warning", ""),
        aws_region=data.get("aws_region", default_aws_region),
        bq_location=data.get("bq_location", default_bq_location),
    )


class PricingTimeout(Exception):
    """Raised when a live pricing lookup exceeds its aggregate wall-clock budget."""


def fetch_live_rates_with_timeout(
    lookup: PriceLookup,
    gcp_client=None,
    budget_seconds: float = _LIVE_FETCH_BUDGET_SECONDS,
) -> PricingRates:
    """Run ``lookup.fetch()`` under an aggregate wall-clock budget.

    The underlying HTTP calls are synchronous ``urllib`` requests that cannot be cancelled
    mid-flight, so we run the fetch on a worker thread and stop WAITING for it once the
    budget expires — raising :class:`PricingTimeout`. The orphaned thread finishes (or
    times out on its own 30s socket timeout) in the background and is harmless: it only
    ever reads public pricing data and writes the local cache. Callers fall back to the
    region-cascaded hardcoded rates already loaded into the constant modules.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    # daemon threads so a hung request never blocks interpreter exit
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pricing-fetch")
    future = executor.submit(lookup.fetch, gcp_client)
    try:
        return future.result(timeout=budget_seconds)
    except FutureTimeout:
        raise PricingTimeout(
            f"live pricing lookup exceeded {budget_seconds:.0f}s budget"
        ) from None
    finally:
        # Don't block on the worker if it's still running — let it finish detached.
        executor.shutdown(wait=False)


def is_live_half(half) -> bool:
    """True when a rates half (AWSRates/GCPRates) carries a genuine live fetch.

    THE live-ness predicate — apply_live_rates gates value application on it and
    callers derive their messaging from apply_live_rates' return value, so the
    rule lives exactly once. Prefix-match: the fallback's source reads
    "hardcoded (verified …)".
    """
    return bool(half.fetched_at) and not half.source.startswith("hardcoded")


def apply_live_rates(rates: PricingRates) -> tuple[bool, bool]:
    """Apply live rates to the module-level constants used by CostEstimator.

    This overwrites the constants in pricing_constants.py and cost_constants.py at runtime
    so that CostEstimator (which reads them at call time) picks up the live values.
    The overridable-via-module-assignment design (R18.7) was built for exactly this.

    Returns ``(aws_applied, gcp_applied)`` — which halves were genuinely live and
    had their values applied. Callers MUST derive user-facing messaging from this
    instead of re-deriving live-ness (message/application drift was a review find).
    """
    from bq_assess.core import pricing_constants as v4
    from bq_assess.engine.redshift import cost_constants as k

    aws = rates.aws
    gcp = rates.gcp

    # Per-half live gate: a hardcoded-fallback half must NOT have its values applied.
    # Fallback halves are captured from whatever the module constants held at fetch
    # time — in the collector distribution that is the un-cascaded us-east-1/US
    # defaults, so applying them here would clobber the region-correct rates
    # apply_bq_region/apply_aws_region installed (the Sydney-priced-as-US class).
    aws_is_live = is_live_half(aws)
    gcp_is_live = is_live_half(gcp)

    # AWS Serverless
    if aws_is_live and aws.rpu_hour_usd > 0:
        k.V1_RPU_HOUR_USD = aws.rpu_hour_usd
        # Recalculate derived reservation rates and breakeven thresholds
        k.V1_SERVERLESS_1YR_RPU_HOUR_USD = round(
            k.V1_RPU_HOUR_USD * (1 - k.V1_SERVERLESS_RESERVATION_1YR_DISCOUNT), 4
        )
        k.V1_SERVERLESS_3YR_RPU_HOUR_USD = round(
            k.V1_RPU_HOUR_USD * (1 - k.V1_SERVERLESS_RESERVATION_3YR_DISCOUNT), 4
        )

    # AWS S3 Tables storage
    if aws_is_live and aws.s3_tables_tier1 > 0:
        k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER1 = aws.s3_tables_tier1
    if aws_is_live and aws.s3_tables_tier2 > 0:
        k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER2 = aws.s3_tables_tier2
    if aws_is_live and aws.s3_tables_tier3 > 0:
        k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER3 = aws.s3_tables_tier3

    # AWS Provisioned RA3
    if aws_is_live and aws.managed_storage_usd_per_gb > 0:
        k.V6_MANAGED_STORAGE_USD_PER_GB_MONTH = aws.managed_storage_usd_per_gb

    node_updates = {
        "ra3.xlplus": {
            "ondemand_usd_per_node_hour": aws.ra3_xlplus_ondemand,
            "ri_1yr_usd_per_node_hour": aws.ra3_xlplus_1yr,
            "ri_3yr_usd_per_node_hour": aws.ra3_xlplus_3yr,
        },
        "ra3.4xlarge": {
            "ondemand_usd_per_node_hour": aws.ra3_4xl_ondemand,
            "ri_1yr_usd_per_node_hour": aws.ra3_4xl_1yr,
            "ri_3yr_usd_per_node_hour": aws.ra3_4xl_3yr,
        },
        "ra3.16xlarge": {
            "ondemand_usd_per_node_hour": aws.ra3_16xl_ondemand,
            "ri_1yr_usd_per_node_hour": aws.ra3_16xl_1yr,
            "ri_3yr_usd_per_node_hour": aws.ra3_16xl_3yr,
        },
    }
    for node_type, updates in node_updates.items():
        for rate_key, value in updates.items():
            if aws_is_live and value > 0:
                k.V6_RA3_NODE_TYPES[node_type][rate_key] = value

    # RG Graviton4 instances (used by the provisioned scenarios)
    rg_updates = {
        "rg.xlarge": {
            "ondemand_usd_per_node_hour": aws.rg_xl_ondemand,
            "ri_1yr_usd_per_node_hour": aws.rg_xl_1yr,
            "ri_3yr_usd_per_node_hour": aws.rg_xl_3yr,
        },
        "rg.4xlarge": {
            "ondemand_usd_per_node_hour": aws.rg_4xl_ondemand,
            "ri_1yr_usd_per_node_hour": aws.rg_4xl_1yr,
            "ri_3yr_usd_per_node_hour": aws.rg_4xl_3yr,
        },
        "rg.16xlarge": {
            "ondemand_usd_per_node_hour": aws.rg_16xl_ondemand,
            "ri_1yr_usd_per_node_hour": aws.rg_16xl_1yr,
            "ri_3yr_usd_per_node_hour": aws.rg_16xl_3yr,
        },
    }
    for node_type, updates in rg_updates.items():
        for rate_key, value in updates.items():
            if aws_is_live and value > 0:
                k.V7_RG_NODE_TYPES[node_type][rate_key] = value

    # GCP BigQuery
    if gcp_is_live and gcp.ondemand_usd_per_tib > 0:
        v4.V4_ONDEMAND_USD_PER_TIB = gcp.ondemand_usd_per_tib
    if gcp_is_live and gcp.storage_active_logical_usd_per_gib > 0:
        v4.V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH = gcp.storage_active_logical_usd_per_gib
    if gcp_is_live and gcp.storage_longterm_logical_usd_per_gib > 0:
        v4.V4_STORAGE_LONGTERM_LOGICAL_USD_PER_GIB_MONTH = gcp.storage_longterm_logical_usd_per_gib

    # Update confirmed dates + region tags — same per-half live gate. Stamping the
    # region tags here keeps the "tag == region the constants reflect" invariant true
    # across ALL writers — the estimate() skip-guard and the unknown-region reset both
    # key on these tags.
    if aws_is_live:
        k.AWS_CONFIRMED_DATE = aws.fetched_at
        k.AWS_PROVISIONED_CONFIRMED_DATE = aws.fetched_at
        k.AWS_PRICING_REGION = rates.aws_region
        k.AWS_REGION_SCOPE = (
            f"{k.AWS_REGIONAL_RATES[rates.aws_region]['label']} / {rates.aws_region}"
            if rates.aws_region in k.AWS_REGIONAL_RATES else rates.aws_region
        )
    if gcp_is_live:
        v4.V4_CONFIRMED_DATE = gcp.fetched_at
        v4.V4_PRICING_REGION = rates.bq_location
        v4.V4_REGION_SCOPE = f"BigQuery region {rates.bq_location}"

    return aws_is_live, gcp_is_live
