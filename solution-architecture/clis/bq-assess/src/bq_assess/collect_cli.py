"""bq-collect — the customer-environment collector CLI.

Runs ONLY the collection half of the pipeline (collector.collect) and writes the
bundle. Ships as its own slim distribution (packaging/collector/) with no report,
scoring, conversion, or engine code — see the 2026-07-08 collector/report design.
"""

from __future__ import annotations

import logging
import os
import sys

import click
from rich.console import Console
from rich.panel import Panel

from bq_assess import __version__
from bq_assess.bundle import BundleWriter
from bq_assess.collector import collect
from bq_assess.core.disclaimer import CLI_ONE_LINER, DATA_HANDLING

logger = logging.getLogger(__name__)
console = Console()


@click.command("bq-collect")
@click.version_option(__version__, message=f"bq-collect %(version)s (beta)\n{CLI_ONE_LINER}")
@click.option("--gcp-project", required=True, help="GCP project ID.")
@click.option("--credentials", default=None, help="Path to service account JSON.")
@click.option("--use-adc", is_flag=True, default=False, help="Use Application Default Credentials.")
@click.option("--datasets", default=None, help="Comma-separated dataset filter.")
@click.option(
    "--query-log-days",
    type=click.IntRange(1, 90),
    default=30,
    show_default=True,
    help="Lookback window for INFORMATION_SCHEMA.JOBS in days.",
)
@click.option("--reservation-config", default=None, help="Path to BigQuery reservation config YAML/JSON.")
@click.option("--output", default="bundle-out/", show_default=True, help="Directory the bundle/ is written into.")
@click.option(
    "--exclude-query-text", is_flag=True, default=False,
    help="Omit anonymized query statements from the bundle (privacy opt-out).",
)
@click.option("--concurrency", type=int, default=50, show_default=True, help="Max parallel API requests for metadata scanning.")
@click.option("--skip-workload", is_flag=True, default=False, help="Skip workload analysis.")
@click.option("--offline-pricing", is_flag=True, default=False, help="Skip the live pricing snapshot.")
@click.option(
    "--no-cache/--use-cache", "no_cache", default=True, show_default=True,
    help="Force a fresh metadata scan. Pass --use-cache to reuse cached metadata.",
)
def main(
    gcp_project: str,
    credentials: str | None,
    use_adc: bool,
    datasets: str | None,
    query_log_days: int,
    reservation_config: str | None,
    output: str,
    exclude_query_text: bool,
    concurrency: int,
    skip_workload: bool,
    offline_pricing: bool,
    no_cache: bool,
) -> None:
    """Collect BigQuery metadata into a bundle for offline assessment.

    Read-only: scans metadata, INFORMATION_SCHEMA statistics, and (unless
    --exclude-query-text) anonymized query statements. Review the bundle
    contents before transmitting them outside your environment.
    """
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

    if credentials and use_adc:
        console.print("[red]Error: --credentials and --use-adc are mutually exclusive[/red]")
        sys.exit(1)
    if not credentials and not use_adc:
        console.print("[red]Error: provide --credentials or --use-adc[/red]")
        sys.exit(1)

    params: dict = {
        "gcp_project": gcp_project,
        "credentials": credentials,
        "use_adc": use_adc,
        "datasets": datasets,
        "query_log_days": query_log_days,
        "reservation_config": reservation_config,
        "exclude_query_text": exclude_query_text,
        "concurrency": concurrency,
        "skip_workload": skip_workload,
        "offline_pricing": offline_pricing,
        "no_cache": no_cache,
    }

    # Load reservation config if provided (kept file-free inside collect())
    if reservation_config:
        try:
            with open(reservation_config, encoding="utf-8") as f:
                if reservation_config.endswith(".json"):
                    import json
                    params["reservation_config_data"] = json.load(f)
                else:
                    import yaml
                    params["reservation_config_data"] = yaml.safe_load(f)
            console.print(f"[green]✓ Loaded reservation config: {reservation_config}[/green]")
        except Exception as exc:
            console.print(f"[yellow]⚠ Failed to load reservation config: {exc}[/yellow]")

    try:
        bundle = collect(params)

        console.print("\n[bold]Writing bundle...[/bold]")
        writer = BundleWriter()
        bundle_dir = writer.write(bundle, output)
        console.print(f"[green]✓ Bundle written: {bundle_dir}[/green]")

        _print_collection_summary(bundle, bundle_dir)
    except KeyboardInterrupt:
        console.print("\n[yellow]Collection interrupted by user.[/yellow]")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"\n[red]Fatal error: {exc}[/red]")
        logger.exception("Fatal error during collection")
        sys.exit(1)


def _print_collection_summary(bundle, bundle_dir: str) -> None:
    """Show what was collected and what is leaving the environment."""
    console.print()
    console.rule("[bold cyan]Collection Summary[/bold cyan]")
    console.print(f"  Project:            {bundle.project_id}")
    console.print(f"  Entities:           {len(bundle.entities)}")
    console.print(f"  Region:             {bundle.bq_location} (AWS: {bundle.aws_region})")
    console.print(f"  Workload data:      {'yes' if bundle.workload else 'no'}")
    console.print(f"  Pricing detection:  {'yes' if bundle.pricing else 'no'}")
    console.print(f"  Rate snapshot:      {'yes' if bundle.rates else 'no'}")
    console.print(
        f"  Query statements:   "
        f"{len(bundle.queries) if bundle.queries else 'none (excluded or unavailable)'}"
        f"{' — anonymized, literals stripped' if bundle.queries else ''}"
    )
    console.print(f"  Scan failures:      {len(bundle.failures)}")
    console.print(f"  Storage basis:      {bundle.storage_basis}")

    console.print(Panel.fit(
        f"[bold]Next steps[/bold]\n"
        f"1. Review the JSON files in [cyan]{bundle_dir}[/cyan] — everything the bundle\n"
        f"   contains is plain text you can audit.\n"
        f"2. Zip the directory and send it to your AWS contact:\n"
        f"   [dim]cd {os.path.dirname(bundle_dir) or '.'} && zip -r bundle.zip {os.path.basename(bundle_dir)}/[/dim]\n\n"
        f"[dim]{DATA_HANDLING}[/dim]",
        border_style="cyan",
    ))
    console.print(f"\n[dim]{CLI_ONE_LINER}[/dim]\n")


if __name__ == "__main__":
    main()
