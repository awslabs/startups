# Review fixes (2026-07-03): live price lookup parsing regressions.
"""Unit tests for PriceLookup parsing — S3 Tables per-dimension tier prices and
the zero-SKU GCP result treated as a miss (not a fake-live result)."""

from __future__ import annotations

import time

import pytest

from bq_assess.core.price_lookup import (
    PriceLookup,
    PricingRates,
    PricingTimeout,
    fetch_live_rates_with_timeout,
)


def _offer(products, terms):
    return products, {"OnDemand": terms}["OnDemand"]


def test_s3_tables_tiers_read_each_dimensions_own_price() -> None:
    """One SKU carries all three tiers as priceDimensions with DIFFERENT prices —
    each tier must get its own, not the first dimension's price three times."""
    products = {
        "SKU1": {"attributes": {"usagetype": "Tables-TimedStorage-ByteHrs"}},
    }
    terms = {
        "SKU1": {
            "offer": {
                "priceDimensions": {
                    "d1": {"beginRange": "0", "endRange": "51200",
                           "pricePerUnit": {"USD": "0.0265"}},
                    "d2": {"beginRange": "51200", "endRange": "512000",
                           "pricePerUnit": {"USD": "0.0253"}},
                    "d3": {"beginRange": "512000", "endRange": "Inf",
                           "pricePerUnit": {"USD": "0.0242"}},
                }
            }
        }
    }
    tiers = PriceLookup._parse_s3_tables_tiers(products, terms)
    assert tiers == {"tier1": 0.0265, "tier2": 0.0253, "tier3": 0.0242}


def test_s3_tables_ignores_intelligent_tiering_variants() -> None:
    """INT-FA/INT-IA usagetypes must not clobber the Standard tiers."""
    products = {
        "STD": {"attributes": {"usagetype": "APS2-Tables-TimedStorage-ByteHrs"}},
        "INT": {"attributes": {"usagetype": "APS2-Tables-TimedStorage-INT-FA-ByteHrs"}},
    }
    terms = {
        "STD": {"o": {"priceDimensions": {"d": {"beginRange": "0", "pricePerUnit": {"USD": "0.0288"}}}}},
        "INT": {"o": {"priceDimensions": {"d": {"beginRange": "0", "pricePerUnit": {"USD": "0.9999"}}}}},
    }
    tiers = PriceLookup._parse_s3_tables_tiers(products, terms)
    assert tiers == {"tier1": 0.0288}


def test_gcp_parse_with_no_matching_region_returns_zeroed_rates() -> None:
    """A region-filtered parse that matches nothing yields zero rates — the caller
    (_fetch_gcp_rates) must then treat it as a miss and fall back to hardcoded."""
    lookup = PriceLookup(aws_region="us-east-1", bq_location="mars-north1", use_cache=False)
    rates = lookup._parse_gcp_skus([
        {
            "description": "Analysis (australia-southeast1)",
            "serviceRegions": ["australia-southeast1"],
            "category": {"resourceGroup": "OnDemandAnalysis"},
            "pricingInfo": [{"pricingExpression": {
                "usageUnit": "TiBy",
                "tieredRates": [{"unitPrice": {"units": "8", "nanos": 125000000}}],
            }}],
        }
    ])
    assert rates.ondemand_usd_per_tib == 0    # region filter excluded the only SKU


def test_gcp_parse_matches_own_region() -> None:
    lookup = PriceLookup(aws_region="ap-southeast-2", bq_location="australia-southeast1",
                         use_cache=False)
    rates = lookup._parse_gcp_skus([
        {
            "description": "Analysis (australia-southeast1)",
            "serviceRegions": ["australia-southeast1"],
            "category": {"resourceGroup": "OnDemandAnalysis"},
            "pricingInfo": [{"pricingExpression": {
                "usageUnit": "TiBy",
                "tieredRates": [{"unitPrice": {"units": "8", "nanos": 125000000}}],
            }}],
        }
    ])
    assert rates.ondemand_usd_per_tib == 8.125


def test_mixed_live_hardcoded_result_is_not_cached(tmp_path, monkeypatch) -> None:
    """AWS-live + GCP-fallback must NOT be cached — a 24h entry would pin the fallback
    and suppress the GCP retry after a transient failure clears."""
    import bq_assess.core.price_lookup as pl
    monkeypatch.setattr(pl, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(pl, "_CACHE_FILE", tmp_path / "pricing-cache.json")

    lookup = PriceLookup(aws_region="us-east-1", bq_location="us", use_cache=True)
    monkeypatch.setattr(lookup, "_fetch_aws_rates", lambda: pl.AWSRates(
        rpu_hour_usd=0.375, fetched_at="2026-07-04", source="AWS Price List API"))
    rates = lookup.fetch(gcp_client=None)   # no client → GCP falls back to hardcoded
    assert rates.gcp.source.startswith("hardcoded")
    assert not (tmp_path / "pricing-cache.json").exists()


def test_both_live_result_is_cached(tmp_path, monkeypatch) -> None:
    import bq_assess.core.price_lookup as pl
    monkeypatch.setattr(pl, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(pl, "_CACHE_FILE", tmp_path / "pricing-cache.json")

    lookup = PriceLookup(aws_region="us-east-1", bq_location="us", use_cache=True)
    monkeypatch.setattr(lookup, "_fetch_aws_rates", lambda: pl.AWSRates(
        rpu_hour_usd=0.375, fetched_at="2026-07-04", source="AWS Price List API"))
    monkeypatch.setattr(lookup, "_fetch_gcp_rates", lambda client: pl.GCPRates(
        ondemand_usd_per_tib=6.25, fetched_at="2026-07-04",
        source="GCP Cloud Billing Catalog API (us)"))
    lookup.fetch(gcp_client=object())
    assert (tmp_path / "pricing-cache.json").exists()


def test_fetch_live_rates_times_out_before_slow_fetch_completes() -> None:
    """A fetch that outlasts the budget raises PricingTimeout at the deadline, not later.

    Regression for the storm-aws deep-audit finding that the paginated GCP catalog fetch
    could freeze the CLI for minutes. The wait ends at the budget, and the orphaned worker
    thread must not delay the return.
    """
    class SlowLookup(PriceLookup):
        def fetch(self, gcp_client=None):
            time.sleep(5)
            return PricingRates(is_live=True)

    t0 = time.monotonic()
    with pytest.raises(PricingTimeout):
        fetch_live_rates_with_timeout(SlowLookup(), budget_seconds=0.3)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"waited {elapsed:.2f}s — should abort near the 0.3s budget"


def test_fetch_live_rates_returns_result_within_budget() -> None:
    """A fast fetch returns its PricingRates unchanged, well inside the budget."""
    class FastLookup(PriceLookup):
        def fetch(self, gcp_client=None):
            return PricingRates(is_live=True, aws_region="ap-southeast-2", bq_location="australia-southeast1")

    rates = fetch_live_rates_with_timeout(FastLookup(), budget_seconds=5)
    assert rates.is_live
    assert rates.aws_region == "ap-southeast-2"


def test_fetch_live_rates_passes_gcp_client_through() -> None:
    """The gcp_client argument is forwarded to the wrapped fetch()."""
    seen = {}

    class RecordingLookup(PriceLookup):
        def fetch(self, gcp_client=None):
            seen["client"] = gcp_client
            return PricingRates(is_live=False)

    sentinel = object()
    fetch_live_rates_with_timeout(RecordingLookup(), gcp_client=sentinel, budget_seconds=5)
    assert seen["client"] is sentinel
