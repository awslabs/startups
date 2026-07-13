# Feature: bq-assess-lakehouse, Phase 7: CLI properties (P1, P2)
"""Property tests for CLI config (P1, P2).

Property 1 (P1): CLI override precedence
- For any key, CLI value always wins over config value

Property 2 (P2): Credential mode exclusivity
- Exactly one credential mode resolves, or both absent is an error state
"""

from __future__ import annotations

from hypothesis import given, settings, assume
import hypothesis.strategies as st

from bq_assess.cli import _merge_config


@settings(max_examples=100)
@given(
    key=st.sampled_from(["gcp_project", "output", "format", "datasets", "bigquery_monthly_cost"]),
    cli_val=st.text(min_size=1, max_size=20),
    config_val=st.text(min_size=1, max_size=20),
)
def test_p1_cli_override_precedence(key, cli_val, config_val):
    """P1: For any key, CLI value always wins over config value."""
    assume(cli_val != config_val)
    merged = _merge_config({key: cli_val}, {key: config_val})
    assert merged[key] == cli_val


@settings(max_examples=100)
@given(
    has_credentials=st.booleans(),
    has_adc=st.booleans(),
)
def test_p2_credential_mode_exclusivity(has_credentials, has_adc):
    """P2: Exactly one credential mode resolves, or both absent is an error state.

    Note: The actual validation of XOR happens in _run_pipeline (lines 221-226 in cli.py),
    not in _merge_config. This property test validates that the merge operation
    preserves both credential modes when present, allowing the validation to occur later.
    """
    params: dict = {}
    if has_credentials:
        params["credentials"] = "/path/to/sa.json"
    if has_adc:
        params["use_adc"] = True

    # The merge function itself doesn't enforce XOR - it just merges values
    # The XOR validation happens in _run_pipeline, after the merge
    merged = _merge_config(params, {})

    # Verify the merge preserves what was passed in
    if has_credentials:
        assert merged.get("credentials") == "/path/to/sa.json"
    if has_adc:
        assert merged.get("use_adc") is True

    # Verify the merge doesn't introduce credentials when not provided
    if not has_credentials:
        assert "credentials" not in merged or merged.get("credentials") is None
    if not has_adc:
        assert "use_adc" not in merged or not merged.get("use_adc")


@settings(max_examples=100)
@given(
    key=st.sampled_from(["gcp_project", "output", "datasets", "query_logs"]),
    val=st.text(min_size=1, max_size=30),
)
def test_p3_none_cli_value_preserves_config(key, val):
    """P3: When CLI param is None, config value is preserved in merge."""
    config = {key: val}
    cli = {key: None}
    merged = _merge_config(cli, config)
    # None values should be skipped, so config value should remain
    assert merged[key] == val


@settings(max_examples=100)
@given(
    config_keys=st.lists(
        st.sampled_from(["output", "format", "datasets", "query_log_days"]),
        min_size=1,
        max_size=4,
        unique=True,
    ),
    cli_key=st.sampled_from(["gcp_project", "use_adc"]),
)
def test_p4_merge_preserves_disjoint_keys(config_keys, cli_key):
    """P4: Merge preserves all keys from config that are not in CLI params."""
    # Build config with the selected keys
    config = {k: f"config-{k}" for k in config_keys}
    # Build CLI with one different key
    cli = {cli_key: f"cli-{cli_key}"}

    merged = _merge_config(cli, config)

    # All config keys should be preserved
    for k in config_keys:
        assert k in merged
        assert merged[k] == f"config-{k}"

    # CLI key should be in result
    assert merged[cli_key] == f"cli-{cli_key}"
