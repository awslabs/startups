"""Single-file HTML report (Landing + Effort + Query tabs), offline-inlined — R20.

Renders all three views into one self-contained HTML file with JS tab navigation,
mobile-responsive layout. Uses the same serialization layer as JSONWriter.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined

from bq_assess.models import Assessment
from bq_assess.core import pricing_constants as v4
from bq_assess.core.disclaimer import (
    ADVISORY_GUIDANCE, AS_IS, BETA_STATUS, COST_NOT_QUOTE, DATA_HANDLING,
)
from bq_assess.engine.redshift import cost_constants as k
from bq_assess.report._serialize import (
    build_report_rows, serialize_entities, serialize_landing,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _format_currency(value):
    """Jinja2 filter: format USD with commas, rounded to integer."""
    if value is None or isinstance(value, Undefined):
        return "N/A"
    return f"${value:,.0f}"


def _format_currency_precise(value):
    """Show up to 2 decimal places for all values."""
    if value is None or isinstance(value, Undefined):
        return "N/A"
    abs_val = abs(value)
    if abs_val < 0.005:
        return "$0.00"
    if abs_val < 100:
        return f"${value:,.2f}"
    return f"${value:,.0f}"


def _format_timestamp(value):
    """Render an ISO timestamp (str or datetime) in the local timezone, minute precision.

    e.g. 2026-06-29 21:42 PDT — aware values are converted to the machine's
    local timezone; naive values are displayed as-is.
    """
    if value is None or isinstance(value, Undefined):
        return "N/A"
    dt = value
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return value
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    tz = dt.strftime("%Z")
    return dt.strftime("%Y-%m-%d %H:%M") + (f" {tz}" if tz else "")


def _format_savings(value):
    """Render savings: positive = 'Save $X', zero = 'Comparable', negative = 'No savings'."""
    if value is None or isinstance(value, Undefined):
        return "N/A"
    abs_val = abs(value)
    if abs_val < 1.0:
        return "Comparable"
    if value < 0:
        return "No savings"
    formatted = _format_currency_precise(abs_val)
    return f"Save {formatted}"


class HTMLWriter:
    """Write a single combined HTML report from an Assessment."""

    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=True,
        )
        self._env.filters["currency"] = _format_currency
        self._env.filters["currency_precise"] = _format_currency_precise
        self._env.filters["savings"] = _format_savings
        self._env.filters["timestamp"] = _format_timestamp

    def write(self, assessment: Assessment, out_dir: str, storage_basis: str = "assumed") -> list[str]:
        """Write a single combined HTML file; return list with its absolute path."""
        landing_data = serialize_landing(assessment)
        effort_entities, query_entities = serialize_entities(assessment)
        report_rows = build_report_rows(effort_entities, query_entities)

        rg_4xl = k.V7_RG_NODE_TYPES["rg.4xlarge"]
        ri_1yr_discount = round(
            (1 - rg_4xl["ri_1yr_usd_per_node_hour"] / rg_4xl["ondemand_usd_per_node_hour"]) * 100
        )
        ri_3yr_discount = round(
            (1 - rg_4xl["ri_3yr_usd_per_node_hour"] / rg_4xl["ondemand_usd_per_node_hour"]) * 100
        )

        # Compute reservation rates from the (possibly live-updated) base rate
        serverless_1yr_rate = round(
            k.V1_RPU_HOUR_USD * (1 - k.V1_SERVERLESS_RESERVATION_1YR_DISCOUNT), 4
        )
        serverless_3yr_rate = round(
            k.V1_RPU_HOUR_USD * (1 - k.V1_SERVERLESS_RESERVATION_3YR_DISCOUNT), 4
        )

        # Per-render CSP nonce: the one legitimate inline <script> carries it; any
        # script injected via a malicious BigQuery identifier (rendered into DDL/SQL
        # code blocks) will NOT, so a compliant browser refuses to execute it. Fresh
        # per file so the value is never guessable/reusable.
        script_nonce = secrets.token_urlsafe(16)

        ctx = {
            **landing_data,
            "report_rows": report_rows,
            "storage_basis": storage_basis,
            "csp_nonce": script_nonce,
            "disclaimer_paragraphs": [
                BETA_STATUS, COST_NOT_QUOTE, ADVISORY_GUIDANCE, AS_IS, DATA_HANDLING,
            ],
            "pricing": {
                "s3_tables_tier1_per_gb": k.V2_S3_TABLES_USD_PER_GB_MONTH_TIER1,
                "rms_per_gb": k.V6_MANAGED_STORAGE_USD_PER_GB_MONTH,
                "serverless_rpu_hr": k.V1_RPU_HOUR_USD,
                "serverless_1yr_rpu_hr": serverless_1yr_rate,
                "serverless_3yr_rpu_hr": serverless_3yr_rate,
                "serverless_1yr_discount_pct": round(k.V1_SERVERLESS_RESERVATION_1YR_DISCOUNT * 100),
                "serverless_3yr_discount_pct": round(k.V1_SERVERLESS_RESERVATION_3YR_DISCOUNT * 100),
                "serverless_1yr_breakeven_pct": round(k.V1_SERVERLESS_1YR_BREAKEVEN_UTIL * 100),
                "serverless_3yr_breakeven_pct": round(k.V1_SERVERLESS_3YR_BREAKEVEN_UTIL * 100),
                "slot_to_rpu_ratio": k.V3_SLOT_TO_RPU_RATIO,
                "rg_4xl_ondemand_hr": rg_4xl["ondemand_usd_per_node_hour"],
                "ri_1yr_discount_pct": ri_1yr_discount,
                "ri_3yr_discount_pct": ri_3yr_discount,
                "hours_per_month": int(k.HOURS_PER_MONTH),
                "region": k.AWS_REGION_SCOPE,
                "aws_region": k.AWS_PRICING_REGION,
                "bq_region": v4.V4_PRICING_REGION,
                "bq_ondemand_per_tib": v4.V4_ONDEMAND_USD_PER_TIB,
                "bq_storage_active_per_gib": v4.V4_STORAGE_ACTIVE_LOGICAL_USD_PER_GIB_MONTH,
                "physical_ratio": k.ASSUMED_PHYSICAL_RATIO,
            },
        }

        template = self._env.get_template("combined.html.j2")
        html = template.render(**ctx)

        filename = f"{assessment.project_id}-assessment.html"
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

        return [os.path.abspath(path)]
