"""CLI interface and pipeline orchestration for bq-assess.

Entry point for the BigQuery migration assessment tool. The pipeline is split at the
collection seam (2026-07-08 collector/report design):

- ``collect(params) -> Bundle`` (collector.py) — every stage that touches GCP.
- ``analyze_and_report(bundle, params)`` (here) — pure computation + report writing.

``bq-assess assess`` composes both in-process (behavior unchanged); ``bq-assess report
--bundle`` runs the analysis half offline on a customer bundle produced by bq-collect.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from bq_assess import __version__
from bq_assess.bundle import Bundle, BundleLoader, BundleWriter
from bq_assess.bundle.loader import BundleError
from bq_assess.collector import collect
from bq_assess.core.disclaimer import CLI_ONE_LINER
from bq_assess.core.sql_surface import SQLSurfaceAnalyzer
from bq_assess.core.relationships import RelationshipInferrer
from bq_assess.core.price_lookup import (
    PriceLookup, PricingTimeout, apply_live_rates, fetch_live_rates_with_timeout,
    rates_from_dict,
)
from bq_assess.core.storage_stats import effective_physical_bytes
from bq_assess.targets.iceberg.converter import IcebergConverter
from bq_assess.targets.iceberg.dml import DMLGenerator
from bq_assess.scoring.effort import EffortScorer
from bq_assess.scoring.complexity import ComplexityScorer
from bq_assess.engine.redshift.rewrite import RewriteGuide
from bq_assess.engine.redshift.placement import PlacementAdvisor
from bq_assess.engine.redshift.cost import CostEstimator
from bq_assess.report.json_writer import JSONWriter
from bq_assess.report.html_writer import HTMLWriter
from bq_assess.models import (
    Assessment, AssessmentSummary, EntityReport, EntityPopulation,
    EffortResult, ComplexityResult, PlacementRecommendation, TranslationResult,
    FailureRecord, ConfidenceLevel, CostComparison, BQPricingModel,
)

logger = logging.getLogger(__name__)
console = Console()


def _load_config(config_path: str) -> dict:
    """Load a YAML config file and return a flat dict of values."""
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(1)
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        console.print(f"[red]Invalid YAML in config file: {exc}[/red]")
        sys.exit(1)

    result: dict = {}
    gcp = raw.get("gcp", {})
    if gcp.get("project_id"):
        result["gcp_project"] = gcp["project_id"]
    if gcp.get("credentials"):
        result["credentials"] = gcp["credentials"]
    if gcp.get("use_adc") is not None:
        result["use_adc"] = bool(gcp["use_adc"])
    if gcp.get("datasets"):
        datasets = gcp["datasets"]
        result["datasets"] = ",".join(datasets) if isinstance(datasets, list) else str(datasets)

    ql = raw.get("query_logs", {})
    if ql.get("enabled") is not None:
        result["include_query_logs"] = bool(ql["enabled"])
    if ql.get("file"):
        result["query_logs"] = ql["file"]
    if ql.get("days") is not None:
        result["query_log_days"] = int(ql["days"])

    cost = raw.get("cost", {})
    if cost.get("bigquery_monthly") is not None:
        result["bigquery_monthly_cost"] = float(cost["bigquery_monthly"])
    if cost.get("reservation_config"):
        result["reservation_config"] = cost["reservation_config"]

    opts = raw.get("options", {})
    if opts.get("output"):
        result["output"] = opts["output"]
    if opts.get("format"):
        fmt = opts["format"]
        result["format"] = ",".join(fmt) if isinstance(fmt, list) else str(fmt)

    return result


def _merge_config(cli_params: dict, config_values: dict) -> dict:
    """Merge CLI params with config file values. CLI args take precedence."""
    merged = dict(config_values)
    for key, value in cli_params.items():
        if value is not None:
            merged[key] = value
    return merged


def _interactive_prompts(params: dict) -> dict:
    """Prompt the user for missing values using Rich prompts."""
    console.print("\n[bold cyan]Interactive configuration mode[/bold cyan]\n")

    if not params.get("gcp_project"):
        params["gcp_project"] = Prompt.ask("GCP Project ID")

    if not params.get("credentials") and not params.get("use_adc"):
        cred_choice = Prompt.ask(
            "Authentication method",
            choices=["credentials", "adc"],
            default="adc",
        )
        if cred_choice == "credentials":
            params["credentials"] = Prompt.ask("Path to service account JSON")
        else:
            params["use_adc"] = True

    if not params.get("datasets"):
        ds = Prompt.ask("Datasets to scan (comma-separated, or empty for all)", default="")
        if ds.strip():
            params["datasets"] = ds.strip()

    params["include_query_logs"] = params.get("include_query_logs") or Confirm.ask(
        "Include query log analysis?", default=False
    )

    if params.get("include_query_logs") and not params.get("query_logs"):
        ql = Prompt.ask("Path to exported query logs JSON (or empty for API)", default="")
        if ql.strip():
            params["query_logs"] = ql.strip()

    if params.get("include_query_logs") and not params.get("query_logs") and params.get("query_log_days") is None:
        qld = Prompt.ask("Query log lookback window in days (1-90)", default="30")
        try:
            qld_int = int(qld.strip())
            if 1 <= qld_int <= 90:
                params["query_log_days"] = qld_int
            else:
                console.print("[yellow]Out of range, using default 30 days.[/yellow]")
        except ValueError:
            console.print("[yellow]Invalid value, using default 30 days.[/yellow]")

    if params.get("bigquery_monthly_cost") is None:
        bq_cost = Prompt.ask("Monthly BigQuery cost override (or empty to calculate)", default="")
        if bq_cost.strip():
            try:
                params["bigquery_monthly_cost"] = float(bq_cost.strip())
            except ValueError:
                console.print("[yellow]Invalid cost value, will calculate automatically.[/yellow]")

    if not params.get("output"):
        params["output"] = Prompt.ask("Output directory", default="reports/")

    if not params.get("format"):
        params["format"] = Prompt.ask("Output formats (json,html)", default="json,html")

    return params




def _validate_report_params(params: dict) -> list[str]:
    """Validate output format params; return the parsed formats list. Exits on error."""
    output_format: str = params.get("format", "json,html")
    formats = [f.strip().lower() for f in output_format.split(",") if f.strip()]
    for fmt in formats:
        if fmt not in ("json", "html"):
            console.print(f"[red]Error: format '{fmt}' not supported. Use 'json' or 'html'.[/red]")
            sys.exit(1)
    return formats


def _validate_collect_params(params: dict) -> None:
    """Validate credential params and load reservation config. Exits on error."""
    credentials: str | None = params.get("credentials")
    use_adc: bool = params.get("use_adc", False)

    if credentials and use_adc:
        console.print("[red]Error: --credentials and --use-adc are mutually exclusive[/red]")
        sys.exit(1)
    if not credentials and not use_adc:
        console.print("[red]Error: provide --credentials or --use-adc[/red]")
        sys.exit(1)

    # Load reservation config if provided (parsed here so collect() stays file-free)
    reservation_config_path: str | None = params.get("reservation_config")
    if reservation_config_path:
        try:
            with open(reservation_config_path, encoding="utf-8") as f:
                if reservation_config_path.endswith(".json"):
                    import json
                    params["reservation_config_data"] = json.load(f)
                else:
                    params["reservation_config_data"] = yaml.safe_load(f)
            console.print(f"[green]✓ Loaded reservation config: {reservation_config_path}[/green]")
        except Exception as exc:
            console.print(f"[yellow]⚠ Failed to load reservation config: {exc}[/yellow]")


def analyze_and_report(bundle: Bundle, params: dict) -> Assessment:
    """Run the pure-computation stages (3-16) on a Bundle and write reports.

    Works identically whether the Bundle came from an in-process collect() (assess)
    or was loaded from disk (report --bundle) — the anti-drift guarantee.
    """
    entities = bundle.entities
    failures = list(bundle.failures)
    gcp_project = bundle.project_id
    detected_location = bundle.bq_location
    slots = bundle.workload
    pricing = bundle.pricing
    storage_basis = bundle.storage_basis

    bigquery_monthly_cost: float | None = params.get("bigquery_monthly_cost")
    output_dir: str = params.get("output", "reports/")
    formats = _validate_report_params(params)

    if not entities:
        console.print("[red]Bundle contains no entities. Nothing to assess.[/red]")
        sys.exit(1)

    # ── Stage 3: SQL Surface Detection ─────────────────────────────
    console.print("\n[bold]Stage 3:[/bold] Detecting SQL surface constructs...")
    sql_analyzer = SQLSurfaceAnalyzer()
    query_log_text: list[str] | None = None

    # Anonymized statements from the bundle (queries.jsonl or in-process collection)
    if bundle.queries:
        query_log_text = [q.query for q in bundle.queries if q.query]
        console.print(f"[green]✓ {len(query_log_text)} anonymized statements available for analysis.[/green]")

    constructs_by_entity = sql_analyzer.detect_for_entities(entities, query_log_text)
    console.print(f"[green]✓ Detected SQL constructs for {len(constructs_by_entity)} entities.[/green]")

    # ── Stage 4: Iceberg Conversion ────────────────────────────────
    console.print("\n[bold]Stage 4:[/bold] Converting TABLE entities to Iceberg schemas...")
    converter = IcebergConverter()
    conversion_results: dict[str, object] = {}

    table_entities = [e for e in entities if e.population == EntityPopulation.TABLE]
    for entity in table_entities:
        try:
            result = converter.convert(entity)
            conversion_results[entity.full_name] = result
            if not result.success:
                failures.append(FailureRecord(
                    entity_name=entity.full_name,
                    stage="convert",
                    error="; ".join(result.warnings),
                ))
        except Exception as exc:
            console.print(f"[yellow]⚠ Conversion failed for {entity.full_name}: {exc}[/yellow]")
            failures.append(FailureRecord(
                entity_name=entity.full_name,
                stage="convert",
                error=str(exc),
            ))

    console.print(f"[green]✓ Converted {len(conversion_results)} schemas.[/green]")

    # ── Stage 5: Score Effort ──────────────────────────────────────
    console.print("\n[bold]Stage 5:[/bold] Scoring migration effort for TABLE entities...")
    effort_scorer = EffortScorer()
    effort_results: dict[str, EffortResult] = {}

    for entity in table_entities:
        try:
            conversion = conversion_results.get(entity.full_name)
            if conversion:
                result = effort_scorer.score(entity, conversion)
                effort_results[entity.full_name] = result
        except Exception as exc:
            console.print(f"[yellow]⚠ Effort scoring failed for {entity.full_name}: {exc}[/yellow]")
            failures.append(FailureRecord(
                entity_name=entity.full_name,
                stage="score_effort",
                error=str(exc),
            ))

    console.print(f"[green]✓ Scored effort for {len(effort_results)} tables.[/green]")

    # ── Stage 6: Relationships ─────────────────────────────────────
    console.print("\n[bold]Stage 6:[/bold] Inferring table relationships...")
    inferrer = RelationshipInferrer()

    # View SQL is already scanned — feed it to the JOIN-clause inference path
    # (was passed as None until the 2026-07-08 collector/report split; SCRUM_NOTES).
    view_definitions = {
        e.full_name: (e.view_query or e.mview_query)
        for e in entities
        if e.view_query or e.mview_query
    }

    try:
        rel_result = inferrer.infer(entities, query_analysis=None, view_definitions=view_definitions or None)
        console.print(
            f"[green]✓ Found {len(rel_result.relationships)} relationships.[/green]"
        )
    except Exception as exc:
        console.print(f"[yellow]⚠ Relationship inference failed: {exc}[/yellow]")
        rel_result = None

    # ── Stage 7: Score Complexity ──────────────────────────────────
    console.print("\n[bold]Stage 7:[/bold] Scoring query complexity...")
    complexity_scorer = ComplexityScorer()
    complexity_results: dict[str, ComplexityResult] = {}
    has_query_logs = bool(bundle.queries)
    dep_counts = ComplexityScorer.build_dep_counts(rel_result)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), console=console,
    ) as progress:
        task = progress.add_task("Scoring complexity...", total=len(entities))
        for entity in entities:
            try:
                constructs = constructs_by_entity.get(entity.full_name, [])
                result = complexity_scorer.score(entity, constructs, has_logs=has_query_logs, dep_counts=dep_counts)
                complexity_results[entity.full_name] = result
            except Exception as exc:
                console.print(f"[yellow]⚠ Complexity scoring failed for {entity.full_name}: {exc}[/yellow]")
                failures.append(FailureRecord(
                    entity_name=entity.full_name,
                    stage="score_complexity",
                    error=str(exc),
                ))
            progress.advance(task)

    console.print(f"[green]✓ Scored complexity for {len(complexity_results)} entities.[/green]")

    # ── Stage 8: Region + Rates Replay ─────────────────────────────
    # Re-point the rate tables at the Source's geography recorded in the bundle, then
    # apply the collection-time rate snapshot. Fully offline — the report side never
    # hits GCP or the pricing APIs unless --refresh-pricing explicitly asks for it.
    console.print("\n[bold]Stage 8:[/bold] Applying region and pricing snapshot...")
    from bq_assess.core import pricing_constants as _v4
    from bq_assess.engine.redshift import cost_constants as _k
    if _v4.apply_bq_region(detected_location):
        console.print(f"[green]✓ BigQuery priced for region: {detected_location}[/green]")
    else:
        console.print(
            f"[yellow]⚠ No verified rate table for BigQuery location "
            f"'{detected_location}' — using US multi-region rates (may understate cost).[/yellow]"
        )
    aws_region = bundle.aws_region or _k.bq_location_to_aws_region(detected_location)
    _k.apply_aws_region(aws_region)
    console.print(f"[green]✓ AWS priced for region: {aws_region}[/green]")

    if params.get("refresh_pricing", False):
        try:
            price_lookup = PriceLookup(
                aws_region=aws_region, bq_location=detected_location,
                use_cache=not params.get("no_cache", True),
            )
            # No GCP client in report mode — only the AWS half (public Price List
            # API) can actually refresh; say so rather than claiming both.
            with console.status("[dim]Fetching live AWS pricing…[/dim]", spinner="dots"):
                live_rates = fetch_live_rates_with_timeout(price_lookup, gcp_client=None)
            if live_rates.is_live:
                # Bundle snapshot first (GCP half), then the fresh AWS fetch on top —
                # reversed order would let the older snapshot clobber the refresh.
                _apply_bundle_rates(bundle, aws_region, detected_location)
                apply_live_rates(live_rates)
                console.print(
                    f"[green]✓ AWS pricing refreshed ({live_rates.aws.fetched_at}).[/green] "
                    f"[dim]GCP rates cannot be refreshed offline — using bundle snapshot/regional rates.[/dim]"
                )
            else:
                console.print("[dim]  Refresh returned no live rates — falling back to bundle snapshot.[/dim]")
                _apply_bundle_rates(bundle, aws_region, detected_location)
        except PricingTimeout as exc:
            console.print(f"[yellow]⚠ {exc} — falling back to bundle snapshot.[/yellow]")
            _apply_bundle_rates(bundle, aws_region, detected_location)
        except Exception as exc:
            console.print(f"[dim]  Pricing refresh skipped: {exc}[/dim]")
            _apply_bundle_rates(bundle, aws_region, detected_location)
    else:
        _apply_bundle_rates(bundle, aws_region, detected_location)

    # ── Stage 10: Cost Estimation ──────────────────────────────────
    console.print("\n[bold]Stage 10:[/bold] Estimating costs...")
    if pricing:
        cost_estimator = CostEstimator(skip_live_pricing=True)
        effort_total = sum(er.score for er in effort_results.values())

        try:
            cost_comparison = cost_estimator.estimate(
                entities, pricing, slots, bigquery_monthly_cost, effort_total,
                location=detected_location,
                storage_basis=storage_basis,
            )
            console.print("[green]✓ Cost estimation complete.[/green]")
        except Exception as exc:
            console.print(f"[yellow]⚠ Cost estimation failed: {exc}[/yellow]")
            # Fix 2: Create sentinel CostComparison on failure
            cost_comparison = CostComparison(
                bq_pricing_model=BQPricingModel.ON_DEMAND,
                bigquery_monthly=0.0,
                bigquery_breakdown=[],
                aws_lines=[],
                aws_monthly_low=0.0,
                aws_monthly_high=0.0,
                monthly_delta_low=0.0,
                monthly_delta_high=0.0,
                annual_savings_low=0.0,
                annual_savings_high=0.0,
                migration_onetime=0.0,
                breakeven_months_low=9999.0,
                breakeven_months_high=9999.0,
                compute_confidence=ConfidenceLevel.LOW,
            )
    else:
        console.print("[yellow]⚠ Skipping cost estimation (no pricing data).[/yellow]")
        # Fix 2: Create sentinel CostComparison when no pricing data
        cost_comparison = CostComparison(
            bq_pricing_model=BQPricingModel.UNKNOWN,
            bigquery_monthly=0.0,
            bigquery_breakdown=[],
            aws_lines=[],
            aws_monthly_low=0.0,
            aws_monthly_high=0.0,
            monthly_delta_low=0.0,
            monthly_delta_high=0.0,
            annual_savings_low=0.0,
            annual_savings_high=0.0,
            migration_onetime=0.0,
            breakeven_months_low=9999.0,
            breakeven_months_high=9999.0,
            compute_confidence=ConfidenceLevel.LOW,
        )

    # ── Stage 11: DML Generation ───────────────────────────────────
    console.print("\n[bold]Stage 11:[/bold] Generating DML for TABLE entities...")
    dml_generator = DMLGenerator()
    dml_results: dict[str, str | None] = {}

    for entity in table_entities:
        try:
            effort = effort_results.get(entity.full_name)
            conversion = conversion_results.get(entity.full_name)
            if effort and conversion:
                dml = dml_generator.generate(entity, effort, conversion)
                dml_results[entity.full_name] = dml
        except Exception as exc:
            console.print(f"[yellow]⚠ DML generation failed for {entity.full_name}: {exc}[/yellow]")

    console.print(f"[green]✓ Generated DML for {len([d for d in dml_results.values() if d])} tables.[/green]")

    # ── Stage 12: Rewrite Guidance ─────────────────────────────────
    console.print("\n[bold]Stage 12:[/bold] Generating rewrite guidance...")
    rewrite_guide = RewriteGuide()
    guidance_results: dict[str, list[str]] = {}

    for entity in entities:
        try:
            constructs = constructs_by_entity.get(entity.full_name, [])
            if constructs:
                guidance = rewrite_guide.guide(entity, constructs)
                guidance_results[entity.full_name] = guidance
        except Exception as exc:
            console.print(f"[yellow]⚠ Guidance generation failed for {entity.full_name}: {exc}[/yellow]")

    console.print(f"[green]✓ Generated guidance for {len(guidance_results)} entities.[/green]")

    # ── Stage 12b: Best-Effort SQL Translation ─────────────────────
    translation_results: dict[str, TranslationResult] = {}

    if params.get("skip_translation"):
        console.print("\n[bold]Stage 12b:[/bold] SQL translation [yellow]skipped[/yellow] (--skip-translation).")
    else:
        console.print("\n[bold]Stage 12b:[/bold] Translating SQL to Redshift...")
        translation_cache: dict[str, TranslationResult] = {}

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
            BarColumn(), TaskProgressColumn(), console=console,
        ) as progress:
            task = progress.add_task("Translating...", total=len(entities))
            for entity in entities:
                try:
                    sql = entity.view_query or entity.mview_query or (entity.routine.body if entity.routine else None)
                    if sql:
                        if sql in translation_cache:
                            translation_results[entity.full_name] = translation_cache[sql]
                        else:
                            result = rewrite_guide.translate(sql)
                            translation_cache[sql] = result
                            translation_results[entity.full_name] = result
                except Exception as exc:
                    console.print(f"[yellow]⚠ Translation failed for {entity.full_name}: {exc}[/yellow]")
                progress.advance(task)

        console.print(f"[green]✓ Translated SQL for {len(translation_results)} entities.[/green]")

    # ── Stage 13: Placement ────────────────────────────────────────
    console.print("\n[bold]Stage 13:[/bold] Recommending placement for REBUILT entities...")
    placement_advisor = PlacementAdvisor()
    placement_results: dict[str, PlacementRecommendation] = {}

    rebuilt_entities = [e for e in entities if e.population == EntityPopulation.REBUILT]
    for entity in rebuilt_entities:
        try:
            placement = placement_advisor.recommend(entity, rel_result, has_query_logs)
            if placement:
                placement_results[entity.full_name] = placement
        except Exception as exc:
            console.print(f"[yellow]⚠ Placement recommendation failed for {entity.full_name}: {exc}[/yellow]")

    console.print(f"[green]✓ Recommended placement for {len(placement_results)} entities.[/green]")

    # ── Stage 14: Assemble Assessment ──────────────────────────────
    console.print("\n[bold]Stage 14:[/bold] Assembling assessment report...")

    # Build summary
    effort_counts = {"AUTO": 0, "ASSISTED": 0, "MANUAL": 0}
    complexity_counts = {"PORTABLE": 0, "ADAPT": 0, "REWRITE": 0}
    total_size_gb = 0.0
    total_logical_size_gb = 0.0

    for entity in entities:
        total_size_gb += effective_physical_bytes(entity.num_bytes, entity.physical_bytes) / (1024 ** 3)
        total_logical_size_gb += entity.num_bytes / (1024 ** 3)

        if entity.full_name in effort_results:
            effort = effort_results[entity.full_name]
            effort_counts[effort.category.value] += 1

        if entity.full_name in complexity_results:
            comp = complexity_results[entity.full_name]
            complexity_counts[comp.category.value] += 1

    # Determine overall SQL surface confidence
    complexity_confidences = [cr.confidence for cr in complexity_results.values()]
    if not complexity_confidences:
        sql_confidence = ConfidenceLevel.LOW
    elif any(c == ConfidenceLevel.HIGH for c in complexity_confidences):
        sql_confidence = ConfidenceLevel.HIGH
    elif any(c == ConfidenceLevel.MEDIUM for c in complexity_confidences):
        sql_confidence = ConfidenceLevel.MEDIUM
    else:
        sql_confidence = ConfidenceLevel.LOW

    summary = AssessmentSummary(
        total_entities=len(entities),
        total_tables=len(table_entities),
        total_size_gb=round(total_size_gb, 4),
        effort_counts=effort_counts,
        complexity_counts=complexity_counts,
        sql_surface_confidence=sql_confidence,
        total_logical_size_gb=round(total_logical_size_gb, 4),
    )

    # Build entity reports
    entity_reports = []
    for entity in entities:
        effort = effort_results.get(entity.full_name)
        conversion = conversion_results.get(entity.full_name)
        complexity = complexity_results.get(entity.full_name)
        dml = dml_results.get(entity.full_name)
        guidance = guidance_results.get(entity.full_name, [])
        placement = placement_results.get(entity.full_name)

        entity_reports.append(EntityReport(
            full_name=entity.full_name,
            entity_type=entity.entity_type,
            population=entity.population,
            rows=entity.num_rows,
            size_gb=round(entity.num_bytes / (1024 ** 3), 4),
            depends_on=entity.depends_on,
            effort=effort,
            conversion=conversion,
            load_sync_dml=dml,
            complexity=complexity,
            rewrite_guidance=guidance,
            translated_sql=translation_results.get(entity.full_name),
            placement=placement,
            physical_bytes=entity.physical_bytes,
        ))

    # Generate assessment ID
    now = datetime.now(timezone.utc)
    hash_input = f"{gcp_project}-{now.isoformat()}"
    short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    assessment_id = f"assess-{now.strftime('%Y%m%d')}-{short_hash}"

    assessment = Assessment(
        assessment_id=assessment_id,
        generated_at=now,
        project_id=gcp_project,
        summary=summary,
        cost=cost_comparison,
        entities=entity_reports,
        failures=failures,
    )

    console.print("[green]✓ Assessment assembled.[/green]")

    # ── Stage 15: Write Reports ────────────────────────────────────
    console.print("\n[bold]Stage 15:[/bold] Writing reports...")

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    output_files: list[str] = []

    if "json" in formats:
        json_writer = JSONWriter()
        paths = json_writer.write(assessment, output_dir)
        output_files.extend(paths)
        for path in paths:
            console.print(f"  [green]✓ JSON report: {path}[/green]")

    if "html" in formats:
        html_writer = HTMLWriter()
        paths = html_writer.write(assessment, output_dir, storage_basis=storage_basis)
        output_files.extend(paths)
        for path in paths:
            console.print(f"  [green]✓ HTML report: {path}[/green]")

    # Bundle export (replaces the pre-0.3 metadata/ export — the bundle is a strict
    # superset and is re-processable by `bq-assess report`).
    if params.get("export_bundle", True):
        writer = BundleWriter()
        bundle_dir = writer.write(bundle, output_dir)
        output_files.append(bundle_dir)
        console.print(f"  [green]✓ Bundle exported: {bundle_dir}[/green]")

    # ── Stage 16: Terminal Summary ─────────────────────────────────
    _print_summary(assessment, output_files)
    return assessment


def _apply_bundle_rates(bundle: Bundle, aws_region: str, bq_location: str) -> None:
    """Apply the bundle's collection-time rate snapshot (offline pricing replay).

    apply_live_rates gates per half: only genuinely LIVE halves overwrite the
    region-cascaded constants Stage 8 installed. A hardcoded-fallback half was
    captured from the collector's un-cascaded default constants — applying it
    would price the report in the wrong geography (the Sydney-as-US class).
    """
    if not bundle.rates:
        console.print("[dim]  No rate snapshot in bundle — using region-adjusted hardcoded rates.[/dim]")
        return
    try:
        rates = rates_from_dict(
            bundle.rates, default_aws_region=aws_region, default_bq_location=bq_location
        )
        # apply_live_rates reports which halves it actually applied — the message
        # derives from that, never from a re-derived live-ness predicate.
        aws_live, gcp_live = apply_live_rates(rates)
        if aws_live and gcp_live:
            console.print(
                f"[green]✓ Bundle rate snapshot applied "
                f"(AWS: {rates.aws.fetched_at}, GCP: {rates.gcp.fetched_at}).[/green]"
            )
        elif aws_live or gcp_live:
            live_half = "AWS" if aws_live else "GCP"
            console.print(
                f"[yellow]⚠ Bundle snapshot is part-live — applied {live_half} half only; "
                f"the other side uses region-adjusted hardcoded rates.[/yellow]"
            )
        else:
            console.print(
                "[dim]  Bundle snapshot carries hardcoded fallback rates — "
                "keeping region-adjusted rates instead.[/dim]"
            )
    except Exception as exc:
        console.print(f"[yellow]⚠ Could not apply bundle rate snapshot: {exc} — using hardcoded rates.[/yellow]")


def _print_summary(assessment: Assessment, output_files: list[str]) -> None:
    """Print a Rich summary table to the terminal."""
    console.print("\n")
    console.rule("[bold cyan]Assessment Summary[/bold cyan]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Total entities scanned", str(assessment.summary.total_entities))
    table.add_row("Total tables", str(assessment.summary.total_tables))
    table.add_row("Total data size (BigQuery logical)", f"{assessment.summary.total_logical_size_gb:.2f} GB")
    table.add_row("Projected size on S3 Iceberg", f"{assessment.summary.total_size_gb:.2f} GB")

    effort_counts = assessment.summary.effort_counts
    table.add_row(
        "Migration effort",
        f"[green]AUTO: {effort_counts['AUTO']}[/green]  "
        f"[yellow]ASSISTED: {effort_counts['ASSISTED']}[/yellow]  "
        f"[red]MANUAL: {effort_counts['MANUAL']}[/red]",
    )

    complexity_counts = assessment.summary.complexity_counts
    table.add_row(
        "Query complexity",
        f"[green]PORTABLE: {complexity_counts['PORTABLE']}[/green]  "
        f"[yellow]ADAPT: {complexity_counts['ADAPT']}[/yellow]  "
        f"[red]REWRITE: {complexity_counts['REWRITE']}[/red]",
    )

    if assessment.cost:
        cost = assessment.cost
        if cost.monthly_delta_low == cost.monthly_delta_high:
            delta_str = f"${cost.monthly_delta_low:,.2f}"
        else:
            delta_str = f"${cost.monthly_delta_low:,.2f} - ${cost.monthly_delta_high:,.2f}"

        table.add_row("Monthly cost delta", delta_str)

        confidence_color = {"LOW": "red", "MEDIUM": "yellow", "HIGH": "green"}
        color = confidence_color.get(cost.compute_confidence.value, "white")
        table.add_row("Cost confidence", f"[{color}]{cost.compute_confidence.value}[/{color}]")

    sql_confidence_color = {"LOW": "red", "MEDIUM": "yellow", "HIGH": "green"}
    sql_color = sql_confidence_color.get(assessment.summary.sql_surface_confidence.value, "white")
    table.add_row("SQL surface confidence", f"[{sql_color}]{assessment.summary.sql_surface_confidence.value}[/{sql_color}]")

    if assessment.failures:
        table.add_row("Failed entities", f"[yellow]{len(assessment.failures)}[/yellow]")

    console.print(table)

    if output_files:
        console.print("\n[bold]Output files:[/bold]")
        for f in output_files:
            console.print(f"  • {f}")

    console.print(f"\n[dim]{CLI_ONE_LINER}[/dim]\n")


class _DefaultToAssessGroup(click.Group):
    """Click group that routes unrecognized invocations to `assess`.

    Backward compatibility for the pre-0.3 single-command CLI: when the first
    token is not a known subcommand or a group-level option (derived from the
    group's OWN params — never a hardcoded list, so adding a group option can't
    silently reroute it), "assess" is prepended and its parser handles every
    option. Options are registered once, on the subcommands, so
    `bq-assess --gcp-project p assess` errors instead of dropping flags.
    """

    def parse_args(self, ctx, args):
        if not args:
            return super().parse_args(ctx, ["assess"])
        # Group-level options = declared params + the auto-added help option
        # (click injects it at parse time, so it is not in self.params).
        group_opts = {opt for p in self.params for opt in (*p.opts, *p.secondary_opts)}
        group_opts.update(ctx.help_option_names)
        first = args[0].split("=", 1)[0]
        if first.startswith("-") and first not in group_opts:
            args = ["assess", *args]
        return super().parse_args(ctx, args)


@click.group(
    "bq-assess",
    cls=_DefaultToAssessGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, message=f"bq-assess %(version)s (beta)\n{CLI_ONE_LINER}")
def main() -> None:
    """BigQuery migration assessment tool.

    Scans BigQuery metadata and generates a comprehensive lakehouse migration
    assessment report with effort scoring, complexity scoring, cost estimates,
    and Iceberg DDL.

    Bare invocation runs `assess` (backward compatible). Use `report` to generate
    a report from a customer bundle produced by bq-collect.
    """


def _assess_options(f):
    """Click options for the assess subcommand (registered once, here only)."""
    options = [
        click.option("--gcp-project", default=None, help="GCP project ID (required)."),
        click.option("--credentials", default=None, help="Path to service account JSON."),
        click.option("--use-adc", is_flag=True, default=False, help="Use Application Default Credentials."),
        click.option("--datasets", default=None, help="Comma-separated dataset filter."),
        click.option("--include-query-logs", is_flag=True, default=False, help="Analyze INFORMATION_SCHEMA.JOBS."),
        click.option("--query-logs", default=None, help="Path to exported query logs JSON."),
        click.option(
            "--query-log-days",
            type=click.IntRange(1, 90),
            default=None,
            help="Lookback window for INFORMATION_SCHEMA.JOBS in days (1-90, default: 30).",
        ),
        click.option("--bigquery-monthly-cost", type=float, default=None, help="Monthly BigQuery spend override."),
        click.option("--reservation-config", default=None, help="Path to BigQuery reservation config YAML/JSON."),
        click.option("--output", default=None, help="Output directory (default: reports/)."),
        click.option("--format", "output_format", default=None, help="Output formats: json,html (default: json,html)."),
        click.option("--interactive", is_flag=True, default=False, help="Interactive prompt mode."),
        click.option(
            "--export-bundle/--no-export-bundle", "export_bundle", default=True,
            help="Write the re-processable bundle/ next to the report (default: enabled).",
        ),
        click.option(
            "--exclude-query-text", is_flag=True, default=False,
            help="Omit anonymized query statements from the bundle (privacy opt-out).",
        ),
        click.option("--concurrency", type=int, default=50, show_default=True, help="Max parallel API requests for metadata scanning."),
        click.option("--skip-translation", is_flag=True, default=False, help="Skip SQL translation stage for faster runs."),
        click.option("--skip-workload", is_flag=True, default=False, help="Skip workload analysis even when pricing is detected."),
        click.option("--offline-pricing", is_flag=True, default=False, help="Skip live pricing lookup (use hardcoded rates)."),
        click.option(
            "--no-cache/--use-cache", "no_cache", default=True, show_default=True,
            help="Force a fresh metadata scan (default — stale cached metadata produced wrong "
                 "customer-facing numbers). Pass --use-cache to reuse cached metadata offline.",
        ),
        click.option("--config", default=None, help="Path to YAML config file."),
    ]
    for option in reversed(options):
        f = option(f)
    return f


@main.command("assess")
@_assess_options
def assess_cmd(
    gcp_project: str | None,
    credentials: str | None,
    use_adc: bool,
    datasets: str | None,
    include_query_logs: bool,
    query_logs: str | None,
    query_log_days: int | None,
    bigquery_monthly_cost: float | None,
    reservation_config: str | None,
    output: str | None,
    output_format: str | None,
    interactive: bool,
    export_bundle: bool,
    exclude_query_text: bool,
    concurrency: int,
    skip_translation: bool,
    skip_workload: bool,
    offline_pricing: bool,
    no_cache: bool,
    config: str | None,
) -> None:
    """Full end-to-end assessment: scan the Source, analyze, write reports + bundle."""
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

    params = _build_params(
        gcp_project=gcp_project, credentials=credentials, use_adc=use_adc,
        datasets=datasets, include_query_logs=include_query_logs, query_logs=query_logs,
        query_log_days=query_log_days, bigquery_monthly_cost=bigquery_monthly_cost,
        reservation_config=reservation_config, output=output, output_format=output_format,
        interactive=interactive, export_bundle=export_bundle,
        exclude_query_text=exclude_query_text, concurrency=concurrency,
        skip_translation=skip_translation, skip_workload=skip_workload,
        offline_pricing=offline_pricing, no_cache=no_cache, config=config,
    )

    try:
        _validate_collect_params(params)
        _validate_report_params(params)
        bundle = collect(params)
        analyze_and_report(bundle, params)
    except KeyboardInterrupt:
        console.print("\n[yellow]Assessment interrupted by user.[/yellow]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]Fatal error: {exc}[/red]")
        logger.exception("Fatal error during assessment")
        sys.exit(1)


@main.command("report")
@click.option(
    "--bundle", "bundle_path", required=True,
    help="Path to a bundle directory or .zip produced by bq-collect (or bq-assess assess).",
)
@click.option("--output", default=None, help="Output directory (default: reports/).")
@click.option("--format", "output_format", default=None, help="Output formats: json,html (default: json,html).")
@click.option("--bigquery-monthly-cost", type=float, default=None, help="Monthly BigQuery spend override.")
@click.option("--skip-translation", is_flag=True, default=False, help="Skip SQL translation stage for faster runs.")
@click.option(
    "--refresh-pricing", is_flag=True, default=False,
    help="Re-fetch live AWS/GCP rates instead of using the bundle's snapshot (needs network).",
)
@click.option(
    "--export-bundle/--no-export-bundle", "export_bundle", default=False,
    help="Re-write the bundle next to the report (default: off — the input bundle already exists).",
)
def report_cmd(
    bundle_path: str,
    output: str | None,
    output_format: str | None,
    bigquery_monthly_cost: float | None,
    skip_translation: bool,
    refresh_pricing: bool,
    export_bundle: bool,
) -> None:
    """Generate the assessment report from a customer bundle — fully offline."""
    logging.basicConfig(level=logging.WARNING)

    params: dict = {
        "output": output or "reports/",
        "format": output_format or "json,html",
        "export_bundle": export_bundle,
        "refresh_pricing": refresh_pricing,
    }
    if bigquery_monthly_cost is not None:
        params["bigquery_monthly_cost"] = bigquery_monthly_cost
    if skip_translation:
        params["skip_translation"] = True

    console.print(f"\n[bold]Loading bundle:[/bold] {bundle_path}")
    try:
        loader = BundleLoader()
        bundle = loader.load(bundle_path)
    except BundleError as exc:
        console.print(f"[red]✗ Bundle verification failed: {exc}[/red]")
        sys.exit(1)

    console.print(
        f"[green]✓ Bundle verified[/green] — project '{bundle.project_id}', "
        f"{len(bundle.entities)} entities, collected {bundle.created_at or 'unknown'} "
        f"by collector v{bundle.collector_version or '?'} "
        f"(region: {bundle.bq_location} → {bundle.aws_region})"
    )

    try:
        analyze_and_report(bundle, params)
    except KeyboardInterrupt:
        console.print("\n[yellow]Report generation interrupted by user.[/yellow]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]Fatal error: {exc}[/red]")
        logger.exception("Fatal error during report generation")
        sys.exit(1)


def _build_params(**kwargs) -> dict:
    """Merge CLI args, config file, and defaults into the params dict (CLI wins)."""
    cli_params: dict = {}
    if kwargs.get("gcp_project") is not None:
        cli_params["gcp_project"] = kwargs["gcp_project"]
    if kwargs.get("credentials") is not None:
        cli_params["credentials"] = kwargs["credentials"]
    if kwargs.get("use_adc"):
        cli_params["use_adc"] = True
    if kwargs.get("datasets") is not None:
        cli_params["datasets"] = kwargs["datasets"]
    if kwargs.get("include_query_logs"):
        cli_params["include_query_logs"] = True
    if kwargs.get("query_logs") is not None:
        cli_params["query_logs"] = kwargs["query_logs"]
    if kwargs.get("query_log_days") is not None:
        cli_params["query_log_days"] = kwargs["query_log_days"]
    if kwargs.get("bigquery_monthly_cost") is not None:
        cli_params["bigquery_monthly_cost"] = kwargs["bigquery_monthly_cost"]
    if kwargs.get("reservation_config") is not None:
        cli_params["reservation_config"] = kwargs["reservation_config"]
    if kwargs.get("output") is not None:
        cli_params["output"] = kwargs["output"]
    if kwargs.get("output_format") is not None:
        cli_params["format"] = kwargs["output_format"]
    if kwargs.get("interactive"):
        cli_params["interactive"] = True
    cli_params["export_bundle"] = kwargs.get("export_bundle", True)
    if kwargs.get("exclude_query_text"):
        cli_params["exclude_query_text"] = True
    cli_params["concurrency"] = kwargs.get("concurrency", 50)
    if kwargs.get("skip_translation"):
        cli_params["skip_translation"] = True
    if kwargs.get("skip_workload"):
        cli_params["skip_workload"] = True
    if kwargs.get("offline_pricing"):
        cli_params["offline_pricing"] = True
    # Always set (default True): fresh scan unless --use-cache was passed explicitly.
    cli_params["no_cache"] = kwargs.get("no_cache", True)

    # Load config file if provided
    config_values: dict = {}
    if kwargs.get("config"):
        config_values = _load_config(kwargs["config"])

    # Merge: CLI args > config file > defaults
    params = _merge_config(cli_params, config_values)

    params.setdefault("use_adc", False)
    params.setdefault("include_query_logs", False)
    params.setdefault("output", "reports/")
    params.setdefault("format", "json,html")
    params.setdefault("interactive", False)

    if params.get("interactive"):
        params = _interactive_prompts(params)

    if not params.get("gcp_project"):
        console.print(
            "[red]Error: --gcp-project is required.[/red]\n"
            "Provide it via CLI argument, config file, or use --interactive mode."
        )
        sys.exit(1)

    if not params.get("credentials") and not params.get("use_adc"):
        console.print(
            "[red]Error: Either --credentials or --use-adc is required.[/red]\n"
            "Provide a service account JSON path or enable Application Default Credentials."
        )
        sys.exit(1)

    return params


if __name__ == "__main__":
    main()
