"""Collection pipeline — every stage that touches the customer's GCP environment.

``collect(params)`` runs credential validation, metadata scan, pricing detection,
workload analysis, anonymized query collection, live-rate snapshotting, and physical-
bytes resolution, and returns a ``Bundle``. It deliberately imports NOTHING from
``report/``, ``scoring/``, ``targets/``, or ``engine/`` — the collector distribution
ships this module (with ``core/`` and ``bundle/``) and must run without them.

``bq-assess assess`` composes ``collect()`` with ``analyze_and_report()`` in-process;
``bq-collect`` runs ``collect()`` alone and writes the bundle. One code path, two
distributions (docs/superpowers/specs/2026-07-08-collector-report-split-design.md).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm

from bq_assess import __version__
from bq_assess.bundle.models import Bundle, QueryRecord
from bq_assess.core.scanner import BigQueryScanner
from bq_assess.core.cache import MetadataCache
from bq_assess.core.analyzer import QueryAnalyzer
from bq_assess.core.pricing import PricingDetector
from bq_assess.core.workload import WorkloadAnalyzer
from bq_assess.core.region_mapping import bq_location_to_aws_region
from bq_assess.core.storage_stats import resolve_physical_bytes, effective_physical_bytes, ASSUMED_PHYSICAL_RATIO
from bq_assess.core.jobs_query import read_jobs_queries, QUERIES_EXPORT_LIMIT
from bq_assess.core.price_lookup import (
    PriceLookup,
    PricingTimeout,
    fetch_live_rates_with_timeout,
    rates_to_dict,
)
from bq_assess.models import EntityMetadata, FailureRecord

logger = logging.getLogger(__name__)
console = Console()


def collect(params: dict) -> Bundle:
    """Run all GCP-touching stages and return the Bundle. Exits(1) on fatal errors."""
    gcp_project: str = params["gcp_project"]
    credentials: str | None = params.get("credentials")
    use_adc: bool = params.get("use_adc", False)
    datasets_str: str | None = params.get("datasets")
    include_query_logs: bool = params.get("include_query_logs", False)
    query_logs_path: str | None = params.get("query_logs")
    query_log_days: int = int(params.get("query_log_days") or 30)
    reservation_config: dict | None = params.get("reservation_config_data")
    exclude_query_text: bool = params.get("exclude_query_text", False)

    dataset_filter: list[str] | None = None
    if datasets_str:
        dataset_filter = [d.strip() for d in datasets_str.split(",") if d.strip()]

    failures: list[FailureRecord] = []

    # ── Stage 1: Validate credentials ──────────────────────────────
    console.print("\n[bold]Stage 1:[/bold] Validating BigQuery credentials...")
    scanner = BigQueryScanner(
        project_id=gcp_project,
        credentials_path=credentials,
        use_adc=use_adc,
        max_concurrent_requests=params.get("concurrency", 16),
    )
    if not scanner.validate_credentials():
        console.print("[red]✗ Credential validation failed.[/red]")
        sys.exit(1)
    console.print("[green]✓ Credentials validated successfully.[/green]")

    # ── Stage 2: Scan or load from cache ───────────────────────────
    cache = MetadataCache()
    entities: list[EntityMetadata] | None = None

    if not params.get("no_cache") and cache.has_cache(gcp_project):
        use_cache = True
        if params.get("interactive"):
            use_cache = Confirm.ask(
                f"Cached metadata found for project '{gcp_project}'. Use cached data?",
                default=True,
            )
        else:
            console.print(f"[cyan]Using cached metadata for project '{gcp_project}'.[/cyan]")

        if use_cache:
            entities = cache.load(gcp_project)
            if entities:
                console.print(f"[green]✓ Loaded {len(entities)} entities from cache.[/green]")
            else:
                console.print("[yellow]⚠ Cache is empty — rescanning.[/yellow]")
                entities = None

    if entities is None:
        console.print("\n[bold]Stage 2:[/bold] Scanning BigQuery metadata...")
        scanned_entities = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scanning entities...", total=None)
            for entity_meta in scanner.scan(dataset_filter=dataset_filter):
                scanned_entities.append(entity_meta)
                progress.update(task, description=f"Scanned {len(scanned_entities)} entities...")

        failures.extend(scanner.failures)

        entities = scanned_entities
        console.print(f"[green]✓ Scanned {len(entities)} entities.[/green]")
        if scanner.failures:
            console.print(f"[yellow]⚠ {len(scanner.failures)} entities failed to scan.[/yellow]")

        if entities:
            console.print("[bold]Caching metadata...[/bold]")
            cache.store(gcp_project, entities)
            console.print("[green]✓ Metadata cached.[/green]")

    if not entities:
        console.print("[red]No entities found. Nothing to assess.[/red]")
        sys.exit(1)

    # ── Stage 3: Pricing Detection ─────────────────────────────────
    console.print("\n[bold]Stage 3:[/bold] Detecting BigQuery pricing model...")
    pricing_detector = PricingDetector()
    client = scanner._get_client()

    # Detect the dataset region from scanned entities so JOBS queries hit the right location.
    detected_location = _detect_dataset_location(client, entities)

    try:
        pricing = pricing_detector.detect(client, gcp_project, reservation_config, location=detected_location)
        console.print(f"[green]✓ Detected pricing model: {pricing.model.value}[/green]")
    except Exception as exc:
        console.print(f"[yellow]⚠ Pricing detection failed: {exc}[/yellow]")
        pricing = None

    # ── Stage 4: Workload Analysis ─────────────────────────────────
    # The live path reads HOURLY aggregates (≤ 24×days rows server-side) — bounded memory
    # and wall-clock regardless of the Source's query volume.
    console.print("\n[bold]Stage 4:[/bold] Analyzing workload...")
    workload_analyzer = WorkloadAnalyzer()
    slots = None
    skip_workload = params.get("skip_workload", False)

    try:
        if skip_workload:
            console.print("[yellow]⚠ Workload analysis skipped (--skip-workload).[/yellow]")
        elif query_logs_path:
            slots, _ = workload_analyzer.analyze_from_file(query_logs_path)
            if slots:
                console.print("[green]✓ Workload analyzed from file.[/green]")
        elif include_query_logs or pricing:
            if pricing and not include_query_logs:
                console.print("[dim]  Pricing detected — auto-running workload analysis for accurate cost (skip with --skip-workload)...[/dim]")
            slots, _ = workload_analyzer.analyze_from_api(client, gcp_project, days=query_log_days, location=detected_location)
            if slots:
                console.print(f"[green]✓ Workload analyzed from API (last {query_log_days} days).[/green]")
    except Exception as exc:
        console.print(f"[yellow]⚠ Workload analysis failed: {exc}[/yellow]")

    if not slots:
        console.print("[yellow]⚠ No workload data available - cost will be estimated as range.[/yellow]")

    # ── Stage 5: Anonymized Query Collection ───────────────────────
    # Default ON (design decision 2, amending R22.4): anonymized statements + per-job
    # stats ride on queries.jsonl. Literals are stripped BEFORE anything touches disk.
    # --skip-workload also skips this stage: both read INFORMATION_SCHEMA.JOBS, and
    # the flag's promise is "no project-wide JOBS scans".
    queries: list[QueryRecord] | None = None
    if exclude_query_text:
        console.print("\n[bold]Stage 5:[/bold] Query collection [yellow]skipped[/yellow] (--exclude-query-text).")
    elif skip_workload and not query_logs_path:
        console.print("\n[bold]Stage 5:[/bold] Query collection [yellow]skipped[/yellow] (--skip-workload covers all JOBS reads).")
    else:
        console.print("\n[bold]Stage 5:[/bold] Collecting anonymized query statements...")
        truncated = False
        try:
            if query_logs_path:
                queries = _queries_from_file(query_logs_path)
            elif include_query_logs or pricing:
                queries, truncated = _queries_from_api(
                    client, gcp_project, query_log_days, detected_location
                )
        except Exception as exc:
            console.print(f"[yellow]⚠ Query collection failed: {exc}[/yellow]")
            queries = None

        if queries:
            console.print(f"[green]✓ Collected {len(queries)} anonymized statements (literals stripped).[/green]")
            if truncated:
                console.print(
                    f"[yellow]⚠ Statement export capped at {QUERIES_EXPORT_LIMIT:,} "
                    f"(heaviest by slot-ms kept).[/yellow]"
                )
        else:
            queries = None
            console.print("[dim]  No query statements available (missing permission or no workload).[/dim]")

    # ── Stage 6: Region Detection + Rate Snapshot ──────────────────
    console.print("\n[bold]Stage 6:[/bold] Snapshotting pricing rates...")
    aws_region = bq_location_to_aws_region(detected_location)
    console.print(f"[dim]  Source region: {detected_location} → AWS region: {aws_region}[/dim]")

    rates_snapshot: dict | None = None
    if not params.get("offline_pricing", False):
        try:
            price_lookup = PriceLookup(
                aws_region=aws_region, bq_location=detected_location,
                use_cache=not params.get("no_cache", True),
            )
            with console.status("[dim]Fetching live pricing from AWS/GCP APIs…[/dim]", spinner="dots"):
                live_rates = fetch_live_rates_with_timeout(price_lookup, gcp_client=client)
            rates_snapshot = rates_to_dict(live_rates)
            if live_rates.is_live:
                console.print(f"[green]✓ Live rates snapshotted (AWS: {live_rates.aws.fetched_at}, GCP: {live_rates.gcp.fetched_at}).[/green]")
            elif live_rates.staleness_warning:
                console.print(f"[yellow]⚠ {live_rates.staleness_warning}[/yellow]")
            else:
                console.print("[dim]  Using cached/hardcoded pricing rates.[/dim]")
        except PricingTimeout as exc:
            console.print(f"[yellow]⚠ {exc} — bundle will carry no live snapshot; report prices with region-adjusted hardcoded rates.[/yellow]")
        except Exception as exc:
            console.print(f"[dim]  Pricing snapshot skipped: {exc}[/dim]")
    else:
        console.print("[dim]  Live pricing lookup skipped (--offline-pricing).[/dim]")

    # ── Stage 7: Physical Storage Resolution ───────────────────────
    console.print("\n[bold]Stage 7:[/bold] Resolving physical storage bytes...")
    try:
        storage_stats = resolve_physical_bytes(
            client, gcp_project, detected_location, entities
        )
        for entity in entities:
            entity.physical_bytes = storage_stats.physical_map.get(entity.full_name)

        if storage_stats.basis == "measured":
            console.print("[green]✓ Physical bytes measured from TABLE_STORAGE.[/green]")
        elif storage_stats.basis == "mixed":
            console.print(f"[yellow]⚠ Partial TABLE_STORAGE coverage — {storage_stats.source_note}[/yellow]")
        else:  # assumed
            console.print(f"[yellow]⚠ TABLE_STORAGE unavailable — using {ASSUMED_PHYSICAL_RATIO}× logical fallback.[/yellow]")
    except Exception as exc:
        console.print(f"[yellow]⚠ Physical storage resolution failed: {exc}[/yellow]")
        storage_stats = None
    finally:
        # Guarantee population even on failure — backfill any unpopulated physical_bytes
        for entity in entities:
            if entity.physical_bytes is None:
                entity.physical_bytes = effective_physical_bytes(entity.num_bytes, None)

    storage_basis = storage_stats.basis if storage_stats else "assumed"

    return Bundle(
        project_id=gcp_project,
        bq_location=detected_location,
        aws_region=aws_region,
        entities=entities,
        failures=failures,
        workload=slots,
        pricing=pricing,
        rates=rates_snapshot,
        queries=queries,
        storage_basis=storage_basis,
        collector_version=__version__,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _queries_from_api(
    client, project_id: str, days: int, location: str
) -> tuple[list[QueryRecord], bool]:
    """Read distinct statements from JOBS (bounded), anonymize BEFORE returning.

    Returns ``(records, truncated)``. Reads limit+1 rows so truncation is PROVEN
    from the RAW row count — empty-text rows are filtered out of the records, so
    the caller's list length alone can't distinguish "hit the limit" from
    "exactly at the limit" (review find: one empty-text group silently defeated
    the boundary check).
    """
    analyzer = QueryAnalyzer()
    rows = read_jobs_queries(
        client, project_id, days=days, location=location,
        limit=QUERIES_EXPORT_LIMIT + 1,
    )
    truncated = len(rows) > QUERIES_EXPORT_LIMIT
    records: list[QueryRecord] = []
    for row in rows:
        text = _col(row, "query")
        if not text:
            continue
        missing = _col(row, "missing_billed_jobs") or 0
        billed = _col(row, "total_bytes_billed")
        creation = _col(row, "creation_time")
        records.append(QueryRecord(
            query=analyzer.anonymize_query(text),
            total_slot_ms=_col(row, "total_slot_ms") or 0,
            total_bytes_processed=_col(row, "total_bytes_processed") or 0,
            # Billed carried only when EVERY job in the statement group had the column —
            # same all-or-nothing rule as the hourly workload read.
            total_bytes_billed=billed if (billed is not None and not missing) else None,
            statement_type=_col(row, "statement_type"),
            creation_time=creation.isoformat() if isinstance(creation, datetime) else (str(creation) if creation else None),
        ))
    return records[:QUERIES_EXPORT_LIMIT], truncated


def _queries_from_file(path: str) -> list[QueryRecord]:
    """Extract per-job entries carrying query text from an exported query-log file.

    Accepts the same formats as WorkloadAnalyzer.analyze_from_file (JSON array OR
    JSONL) via the shared parser — the two stages read the same --query-logs file
    and must never disagree on what parses.
    """
    from pathlib import Path as _Path

    from bq_assess.core.workload import parse_json_or_jsonl

    analyzer = QueryAnalyzer()
    try:
        text = _Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    data = parse_json_or_jsonl(text)
    if not data:
        return []

    records: list[QueryRecord] = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("query"):
            continue
        billed = entry.get("total_bytes_billed")
        records.append(QueryRecord(
            query=analyzer.anonymize_query(entry["query"]),
            total_slot_ms=int(entry.get("total_slot_ms") or 0),
            total_bytes_processed=int(entry.get("total_bytes_processed") or 0),
            total_bytes_billed=int(billed) if billed is not None else None,
            statement_type=entry.get("statement_type"),
            creation_time=str(entry["creation_time"]) if entry.get("creation_time") else None,
        ))
    return records


def _col(row, key):
    """Read a column from a dict (tests/files) or a BigQuery Row (live)."""
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _detect_dataset_location(client, entities: list[EntityMetadata]) -> str:
    """Return the BigQuery region of the scanned datasets (for JOBS queries).

    Falls back to "US" if no dataset can be resolved — matches the previous default.
    """
    seen: set[str] = set()
    for e in entities:
        if e.dataset_id not in seen:
            seen.add(e.dataset_id)
            try:
                ds = client.get_dataset(f"{client.project}.{e.dataset_id}")
                if ds.location:
                    return ds.location
            except Exception:  # nosec B112 - best-effort location probe; fall through to next dataset
                continue
    return "US"
