# Feature: phase1-assessment-tool, Property 1: Config file override precedence
"""Property test: CLI args override config file values for any shared key.

Validates: Requirements 1.4
"""

from __future__ import annotations

from hypothesis import given, settings
import hypothesis.strategies as st

from bq_assess.cli import _merge_config

# The config keys that _merge_config may encounter (flat dict keys produced by
# _load_config and passed from the Click CLI layer).
CONFIG_KEYS = [
    "gcp_project",
    "credentials",
    "use_adc",
    "datasets",
    "include_query_logs",
    "query_logs",
    "redshift_type",
    "bigquery_monthly_cost",
    "output",
    "format",
]

# Strategy: a value that could appear in either a config file dict or CLI params.
_config_value = st.one_of(
    st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.booleans(),
    st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    st.integers(min_value=0, max_value=100000),
)

# Strategy: a dict mapping a subset of CONFIG_KEYS to random non-None values.
_config_dict = st.fixed_dictionaries(
    {},
    optional={k: _config_value for k in CONFIG_KEYS},
)

# Strategy: CLI params dict — values may be None (meaning "not explicitly set").
_cli_dict = st.fixed_dictionaries(
    {},
    optional={k: st.one_of(st.none(), _config_value) for k in CONFIG_KEYS},
)


@settings(max_examples=100)
@given(cli_params=_cli_dict, config_values=_config_dict)
def test_cli_args_override_config_file_values(
    cli_params: dict,
    config_values: dict,
) -> None:
    """Property 1: Config file override precedence.

    **Validates: Requirements 1.4**

    For any YAML config file and any CLI argument that specifies the same
    configuration key, the resulting configuration value SHALL equal the CLI
    argument value, not the config file value.
    """
    merged = _merge_config(cli_params, config_values)

    # 1) Every CLI param that is not None must appear in the merged result
    #    with the CLI value (override).
    for key, value in cli_params.items():
        if value is not None:
            assert key in merged, f"CLI key '{key}' missing from merged result"
            assert merged[key] == value, (
                f"Key '{key}': expected CLI value {value!r}, got {merged[key]!r}"
            )

    # 2) Config-only keys (not overridden by CLI) must retain their config value.
    for key, value in config_values.items():
        cli_val = cli_params.get(key)
        if cli_val is None:
            assert key in merged, f"Config key '{key}' missing from merged result"
            assert merged[key] == value, (
                f"Key '{key}': expected config value {value!r}, got {merged[key]!r}"
            )

    # 3) No extra keys should appear beyond the union of both dicts.
    expected_keys = set(config_values.keys()) | {
        k for k, v in cli_params.items() if v is not None
    }
    assert set(merged.keys()) == expected_keys, (
        f"Unexpected keys in merged result: {set(merged.keys()) - expected_keys}"
    )
