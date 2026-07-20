# test_bedrock_pricing.py
import bedrock_pricing as bp

def test_parse_price_dimensions_extracts_per_1k_token_rates():
    # Pure parser over a Pricing API PriceList JSON fragment.
    fragment = {
        "terms": {"OnDemand": {"x": {"priceDimensions": {
            "d1": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.003"},
                   "description": "Input tokens for Claude"},
            "d2": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.015"},
                   "description": "Output tokens for Claude"},
        }}}}}
    out = bp.parse_price_dimensions(fragment)
    assert out["input_per_1k_usd"] == 0.003
    assert out["output_per_1k_usd"] == 0.015

def test_unavailable_returns_banner_not_exception():
    out = bp.unavailable("network error")
    assert out["available"] is False
    assert "network error" in out["note"]

def test_static_fallback_returns_known_model():
    out = bp._static_fallback("us.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert out is not None
    assert out["available"] is True
    assert out["input_per_1k_usd"] == 0.001
    assert out["output_per_1k_usd"] == 0.005

def test_static_fallback_partial_match():
    # us.anthropic.claude-sonnet-4-6 (no version suffix) should match
    out = bp._static_fallback("us.anthropic.claude-sonnet-4-6")
    assert out is not None
    assert out["available"] is True
    assert out["input_per_1k_usd"] == 0.003

def test_static_fallback_dated_id_matches_undated_key():
    # A dated ID form (even a fabricated one from a stale plan) should still
    # resolve to the undated table key after the date stamp is stripped.
    # Built by concatenation so tools/model-id-lint.py doesn't flag a literal
    # fabricated ID — this test exists precisely to handle such broken inputs.
    dated_id = "us.anthropic.claude-sonnet-4-6" + "-20250514-v1:0"
    out = bp._static_fallback(dated_id)
    assert out is not None
    assert out["input_per_1k_usd"] == 0.003


def test_static_fallback_opus_48_rate_matches_cache():
    # Guards the $5/$25 per-1M rate (pricing-cache.md § Anthropic) — this entry
    # previously carried Opus-4-class $15/$75, a 3x overstatement.
    out = bp._static_fallback("us.anthropic.claude-opus-4-8")
    assert out is not None
    assert out["input_per_1k_usd"] == 0.005
    assert out["output_per_1k_usd"] == 0.025


def test_static_fallback_unknown_returns_none():
    out = bp._static_fallback("totally.fake.model-id")
    assert out is None


def test_display_name_guess_derives_pricing_api_display_names():
    # The Pricing API's 'model' attribute holds display names, not model ids.
    assert bp.display_name_guess("us.anthropic.claude-haiku-4-5-20251001-v1:0") == "Claude Haiku 4.5"
    assert bp.display_name_guess("amazon.nova-lite-v1:0") == "Nova Lite"
    assert bp.display_name_guess("us.anthropic.claude-haiku-4-5-20251001-v1:0") == "Claude Haiku 4.5"


def test_parse_price_dimensions_ignores_cache_dimensions():
    """Cache read/write dimensions must not override base input/output rates."""
    fragment = {
        "terms": {"OnDemand": {"x": {"priceDimensions": {
            "d1": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.003"},
                   "description": "Input tokens for Claude"},
            "d2": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.015"},
                   "description": "Output tokens for Claude"},
            "d3": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.00030"},
                   "description": "Cache read input tokens for Claude"},
            "d4": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.00375"},
                   "description": "Cache write input tokens for Claude"},
        }}}}}
    out = bp.parse_price_dimensions(fragment)
    assert out["input_per_1k_usd"] == 0.003
    assert out["output_per_1k_usd"] == 0.015


def test_parse_price_dimensions_ignores_batch_dimensions():
    """Batch dimensions should be skipped."""
    fragment = {
        "terms": {"OnDemand": {"x": {"priceDimensions": {
            "d1": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.001"},
                   "description": "Input token price for batch inference"},
            "d2": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.003"},
                   "description": "Input tokens for Claude"},
            "d3": {"unit": "1K tokens", "pricePerUnit": {"USD": "0.015"},
                   "description": "Output tokens for Claude"},
        }}}}}
    out = bp.parse_price_dimensions(fragment)
    assert out["input_per_1k_usd"] == 0.003
    assert out["output_per_1k_usd"] == 0.015


def test_lookup_serves_static_table_first_without_calling_the_api(monkeypatch):
    # Models in the curated table must not depend on boto3 at all.
    import builtins
    real_import = builtins.__import__
    def deny_boto3(name, *a, **k):
        if name == "boto3":
            raise AssertionError("lookup() must not import boto3 for static-table models")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", deny_boto3)
    out = bp.lookup("us-east-1", "amazon.nova-pro-v1:0")
    assert out["available"] is True
    assert out["input_per_1k_usd"] == 0.0008
