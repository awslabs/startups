"""Single source of truth for beta/legal disclaimers (both distributions)."""

DISCLAIMER_VERSION = 1

BETA_STATUS = (
    "This tool is in beta. Features, scoring models, and cost calculations are under "
    "active development and may change without notice. Results should be independently "
    "validated before being used for planning or budgeting decisions."
)

COST_NOT_QUOTE = (
    "All cost figures are directional estimates based on published list pricing, "
    "detected or assumed usage patterns, and stated assumptions at the time of "
    "generation. They are not a quote, offer, or commitment from Amazon Web Services "
    "or Google. Actual costs depend on final architecture, negotiated pricing, usage, "
    "and region. Refer to official AWS and Google Cloud pricing for authoritative rates."
)

ADVISORY_GUIDANCE = (
    "Migration effort scores, complexity classifications, generated DDL/DML, SQL "
    "translations, and placement recommendations are automated, best-effort guidance. "
    "They do not replace engineering review. Validate all generated code and "
    "recommendations before use in any environment."
)

AS_IS = (
    'This software is provided "AS IS", without warranties or conditions of any kind, '
    "express or implied, per the Apache License 2.0. Use at your own risk."
)

DATA_HANDLING = (
    "This tool performs read-only operations against BigQuery metadata and "
    "INFORMATION_SCHEMA. It does not read table data contents. The output bundle "
    "contains schema metadata, aggregated workload statistics, and anonymized query "
    "text (literals stripped; disable with --exclude-query-text). You are responsible "
    "for reviewing bundle contents before transmitting them outside your environment."
)

FULL_DISCLAIMER = "\n\n".join([
    BETA_STATUS,
    COST_NOT_QUOTE,
    ADVISORY_GUIDANCE,
    AS_IS,
    DATA_HANDLING,
])

CLI_ONE_LINER = (
    "⚠ BETA — estimates are directional, not a pricing quote. "
    "See report footer for full disclaimer."
)
