# Feature: bq-assess-lakehouse, Phase 7: CLI rewrite (R1)
"""Unit tests for cli.py — arg parsing, config, validation (R1).

Tests cover:
- R1.1: Missing --gcp-project rejected
- R1.2: Missing credential mode (--credentials XOR --use-adc) rejected
- R1.3: --redshift-type removed (not accepted)
- R1.4: csv format rejected
- R1.5: --reservation-config in help
- R1.6-16: Config loading, merging, precedence
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bq_assess.cli import _load_config, _merge_config, _interactive_prompts, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FULL_CONFIG_YAML = """\
gcp:
  project_id: my-gcp-project
  credentials: /path/to/sa.json
  use_adc: false
  datasets:
    - analytics
    - marketing

query_logs:
  enabled: true
  file: /tmp/logs.json
  days: 7

cost:
  bigquery_monthly: 5000.0
  reservation_config: /path/to/res.yaml

options:
  output: output_dir/
  format:
    - json
    - html
"""

_MINIMAL_CONFIG_YAML = """\
gcp:
  project_id: minimal-project
"""


# ---------------------------------------------------------------------------
# Tests: _load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Test YAML config file loading (R1.6-11)."""

    def test_load_full_config(self, tmp_path: object) -> None:
        """Load a YAML file with all config sections and verify the flat dict (R1.6)."""
        config_file = os.path.join(str(tmp_path), "config.yaml")
        with open(config_file, "w") as f:
            f.write(_FULL_CONFIG_YAML)

        result = _load_config(config_file)

        assert result["gcp_project"] == "my-gcp-project"
        assert result["credentials"] == "/path/to/sa.json"
        assert result["use_adc"] is False
        assert result["datasets"] == "analytics,marketing"
        assert result["include_query_logs"] is True
        assert result["query_logs"] == "/tmp/logs.json"  # nosec B108 - asserting CLI arg passthrough, no file created
        assert result["query_log_days"] == 7
        assert result["bigquery_monthly_cost"] == 5000.0
        assert result["reservation_config"] == "/path/to/res.yaml"
        assert result["output"] == "output_dir/"
        assert result["format"] == "json,html"

    def test_load_minimal_config(self, tmp_path: object) -> None:
        """Load a config with only gcp.project_id set (R1.7)."""
        config_file = os.path.join(str(tmp_path), "config.yaml")
        with open(config_file, "w") as f:
            f.write(_MINIMAL_CONFIG_YAML)

        result = _load_config(config_file)

        assert result["gcp_project"] == "minimal-project"
        assert "credentials" not in result
        assert "use_adc" not in result

    def test_reservation_config_parsed(self, tmp_path: object) -> None:
        """_load_config parses cost.reservation_config correctly (R1.8)."""
        config_file = os.path.join(str(tmp_path), "config.yaml")
        with open(config_file, "w") as f:
            f.write("cost:\n  reservation_config: /path/to/res.json\n")

        result = _load_config(config_file)
        assert result["reservation_config"] == "/path/to/res.json"

    def test_missing_file_exits(self, tmp_path: object) -> None:
        """Loading a non-existent config file should sys.exit(1) (R1.10)."""
        with pytest.raises(SystemExit) as exc_info:
            _load_config(os.path.join(str(tmp_path), "nonexistent.yaml"))
        assert exc_info.value.code == 1

    def test_invalid_yaml_exits(self, tmp_path: object) -> None:
        """Loading an invalid YAML file should sys.exit(1) (R1.11)."""
        config_file = os.path.join(str(tmp_path), "bad.yaml")
        with open(config_file, "w") as f:
            f.write(":\n  - :\n  bad: [unterminated")

        with pytest.raises(SystemExit) as exc_info:
            _load_config(config_file)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests: _merge_config
# ---------------------------------------------------------------------------


class TestMergeConfig:
    """Test CLI/config merging (R1.12-16)."""

    def test_cli_overrides_config(self) -> None:
        """CLI params override config file values for the same key (R1.12)."""
        config_values = {"gcp_project": "config-project", "output": "config-out/"}
        cli_params = {"gcp_project": "cli-project"}

        merged = _merge_config(cli_params, config_values)

        assert merged["gcp_project"] == "cli-project"
        assert merged["output"] == "config-out/"

    def test_config_only_keys_preserved(self) -> None:
        """Keys present only in config are preserved in the merged result (R1.16)."""
        config_values = {"output": "dir/", "bigquery_monthly_cost": 3000.0}
        cli_params = {"gcp_project": "my-proj"}

        merged = _merge_config(cli_params, config_values)

        assert merged["gcp_project"] == "my-proj"
        assert merged["output"] == "dir/"
        assert merged["bigquery_monthly_cost"] == 3000.0

    def test_none_cli_values_do_not_override(self) -> None:
        """None CLI values should not override config values (R1.14)."""
        config_values = {"gcp_project": "config-project"}
        cli_params = {"gcp_project": None}

        merged = _merge_config(cli_params, config_values)

        assert merged["gcp_project"] == "config-project"

    def test_empty_config_returns_cli_params(self) -> None:
        """When config is empty, merged result equals CLI params (non-None) (R1.15)."""
        cli_params = {"gcp_project": "proj", "use_adc": True}

        merged = _merge_config(cli_params, {})

        assert merged["gcp_project"] == "proj"
        assert merged["use_adc"] is True

    def test_config_value_used_when_cli_none(self) -> None:
        """When CLI doesn't provide a value, config value is used (R1.13)."""
        config_values = {"gcp_project": "config-proj", "output": "config-dir"}
        cli_params = {}

        merged = _merge_config(cli_params, config_values)

        assert merged["gcp_project"] == "config-proj"
        assert merged["output"] == "config-dir"


# ---------------------------------------------------------------------------
# Tests: Click command argument parsing
# ---------------------------------------------------------------------------


class TestClickCommand:
    """Test Click CLI argument parsing with CliRunner (R1.1-5).

    The pipeline seam is now collect() + analyze_and_report() (collector/report
    split) — tests patch both where they used to patch _run_pipeline.
    """

    def test_gcp_project_and_use_adc_accepted(self) -> None:
        """--gcp-project and --use-adc are accepted as valid options."""
        runner = CliRunner()
        with patch("bq_assess.cli.collect") as mock_collect, \
             patch("bq_assess.cli.analyze_and_report") as mock_report:
            result = runner.invoke(main, [
                "--gcp-project", "test-project",
                "--use-adc",
            ])
            # Pipeline should be called (we mock it to avoid real BQ calls)
            assert mock_collect.called
            assert mock_report.called
            assert result.exit_code == 0

    def test_gcp_project_with_credentials_accepted(self) -> None:
        """--gcp-project with --credentials is accepted."""
        runner = CliRunner()
        with patch("bq_assess.cli.collect") as mock_collect, \
             patch("bq_assess.cli.analyze_and_report") as mock_report:
            result = runner.invoke(main, [
                "--gcp-project", "test-project",
                "--credentials", "/path/to/creds.json",
            ])
            assert mock_collect.called
            assert mock_report.called
            assert result.exit_code == 0

    def test_assess_subcommand_equivalent_to_bare(self) -> None:
        """`bq-assess assess …` parses identically to bare `bq-assess …`."""
        runner = CliRunner()
        with patch("bq_assess.cli.collect") as mock_collect, \
             patch("bq_assess.cli.analyze_and_report") as mock_report:
            result = runner.invoke(main, [
                "assess",
                "--gcp-project", "test-project",
                "--use-adc",
            ])
            assert mock_collect.called
            assert mock_report.called
            assert result.exit_code == 0

    def test_missing_gcp_project_shows_error(self) -> None:
        """Missing --gcp-project (without --interactive) should exit with code 1 (R1.1)."""
        runner = CliRunner()
        result = runner.invoke(main, ["--use-adc"])
        assert result.exit_code == 1
        assert "gcp-project" in result.output.lower() or "required" in result.output.lower()

    def test_missing_credentials_shows_error(self) -> None:
        """Missing both --credentials and --use-adc should exit with code 1 (R1.2)."""
        runner = CliRunner()
        result = runner.invoke(main, ["--gcp-project", "test-project"])
        assert result.exit_code == 1
        assert "credentials" in result.output.lower() or "use-adc" in result.output.lower()

    def test_redshift_type_not_accepted(self) -> None:
        """CLI rejects --redshift-type option (removed in Phase 7, R1.3)."""
        runner = CliRunner()
        result = runner.invoke(main, ["--gcp-project", "p", "--use-adc", "--redshift-type", "ra3.xlplus"])
        # Click should reject the unknown option
        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "redshift-type" in result.output.lower()

    def test_csv_format_rejected(self) -> None:
        """CLI rejects csv format (not implemented, R20.8)."""
        runner = CliRunner()
        # Format validation runs before collect() — mock collect to prevent BQ calls.
        with patch("bq_assess.cli.collect") as mock_collect:
            result = runner.invoke(main, ["--gcp-project", "p", "--use-adc", "--format", "csv"])
            assert result.exit_code != 0, "csv format must be rejected with non-zero exit"
            assert "not supported" in result.output.lower() or "csv" in result.output.lower()
            assert not mock_collect.called, "collect must not run when the format is invalid"

    def test_help_shows_reservation_config(self) -> None:
        """assess help includes --reservation-config option (R1.5). Options live on
        the subcommand only (group options were silently dropped — review fix 5)."""
        runner = CliRunner()
        result = runner.invoke(main, ["assess", "--help"])
        assert result.exit_code == 0
        assert "--reservation-config" in result.output

    def test_options_before_subcommand_error_not_silently_dropped(self) -> None:
        """`bq-assess --gcp-project p assess` must ERROR clearly, not parse the
        options at group level and silently discard them (review fix 5)."""
        runner = CliRunner()
        with patch("bq_assess.cli.collect") as mock_collect:
            result = runner.invoke(main, ["--gcp-project", "p", "--use-adc", "assess"])
            assert result.exit_code != 0
            assert not mock_collect.called

    def test_config_file_option(self, tmp_path: object) -> None:
        """--config loads values from a YAML file."""
        config_file = os.path.join(str(tmp_path), "config.yaml")
        with open(config_file, "w") as f:
            f.write("gcp:\n  project_id: config-proj\n  use_adc: true\n")

        runner = CliRunner()
        with patch("bq_assess.cli.collect") as mock_collect, \
             patch("bq_assess.cli.analyze_and_report"):
            result = runner.invoke(main, ["--config", config_file])
            assert mock_collect.called
            # Verify the pipeline received the config values
            call_params = mock_collect.call_args[0][0]
            assert call_params["gcp_project"] == "config-proj"
            assert call_params["use_adc"] is True
            assert result.exit_code == 0

    def test_cli_overrides_config_file(self, tmp_path: object) -> None:
        """CLI args override config file values."""
        config_file = os.path.join(str(tmp_path), "config.yaml")
        with open(config_file, "w") as f:
            f.write("gcp:\n  project_id: config-proj\n  use_adc: true\n")

        runner = CliRunner()
        with patch("bq_assess.cli.collect") as mock_collect, \
             patch("bq_assess.cli.analyze_and_report"):
            result = runner.invoke(main, [
                "--config", config_file,
                "--gcp-project", "cli-proj",
                "--use-adc",
            ])
            assert mock_collect.called
            call_params = mock_collect.call_args[0][0]
            assert call_params["gcp_project"] == "cli-proj"
            assert result.exit_code == 0

    def test_pipeline_exception_exits_with_code_1(self) -> None:
        """If the pipeline raises an exception, CLI exits with code 1."""
        runner = CliRunner()
        with patch("bq_assess.cli.collect", side_effect=RuntimeError("boom")):
            result = runner.invoke(main, [
                "--gcp-project", "test-project",
                "--use-adc",
            ])
            assert result.exit_code == 1
            assert "fatal" in result.output.lower() or "boom" in result.output.lower()


# ---------------------------------------------------------------------------
# Tests: _interactive_prompts (mocked)
# ---------------------------------------------------------------------------


class TestInteractivePrompts:
    """Test interactive mode prompts with mocked Rich prompts."""

    @patch("bq_assess.cli.Prompt.ask")
    @patch("bq_assess.cli.Confirm.ask")
    def test_fills_missing_gcp_project(self, mock_confirm, mock_prompt) -> None:
        """Interactive mode prompts for gcp_project when missing."""
        mock_prompt.side_effect = lambda *a, **kw: {
            "GCP Project ID": "prompted-project",
            "Authentication method": "adc",
            "Datasets to scan (comma-separated, or empty for all)": "",
            "Path to exported query logs JSON (or empty for API)": "",
            "Query log lookback window in days (1-90)": "30",
            "Monthly BigQuery cost override (or empty to calculate)": "",
            "Output directory": "reports/",
            "Output formats (json,html)": "json,html",
        }.get(a[0], "")
        mock_confirm.return_value = False

        params: dict = {}
        result = _interactive_prompts(params)

        assert result["gcp_project"] == "prompted-project"
        assert result["use_adc"] is True

    @patch("bq_assess.cli.Prompt.ask")
    @patch("bq_assess.cli.Confirm.ask")
    def test_preserves_existing_values(self, mock_confirm, mock_prompt) -> None:
        """Interactive mode does not overwrite already-set values."""
        mock_prompt.side_effect = lambda *a, **kw: {
            "Datasets to scan (comma-separated, or empty for all)": "",
            "Path to exported query logs JSON (or empty for API)": "",
            "Query log lookback window in days (1-90)": "30",
            "Monthly BigQuery cost override (or empty to calculate)": "",
            "Output directory": "reports/",
            "Output formats (json,html)": "json,html",
        }.get(a[0], "")
        mock_confirm.return_value = False

        params = {"gcp_project": "already-set", "use_adc": True}
        result = _interactive_prompts(params)

        assert result["gcp_project"] == "already-set"

    @patch("bq_assess.cli.Prompt.ask")
    @patch("bq_assess.cli.Confirm.ask")
    def test_credentials_path_prompt(self, mock_confirm, mock_prompt) -> None:
        """Interactive mode prompts for credentials path when 'credentials' is chosen."""
        call_count = 0

        def prompt_side_effect(*args, **kwargs):
            nonlocal call_count
            prompt_text = args[0] if args else ""
            call_count += 1
            responses = {
                "GCP Project ID": "my-proj",
                "Authentication method": "credentials",
                "Path to service account JSON": "/path/to/sa.json",
                "Datasets to scan (comma-separated, or empty for all)": "",
                "Path to exported query logs JSON (or empty for API)": "",
                "Query log lookback window in days (1-90)": "30",
                "Monthly BigQuery cost override (or empty to calculate)": "",
                "Output directory": "reports/",
                "Output formats (json,html)": "json,html",
            }
            return responses.get(prompt_text, "")

        mock_prompt.side_effect = prompt_side_effect
        mock_confirm.return_value = False

        params: dict = {}
        result = _interactive_prompts(params)

        assert result["gcp_project"] == "my-proj"
        assert result["credentials"] == "/path/to/sa.json"
