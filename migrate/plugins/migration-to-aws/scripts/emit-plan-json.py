#!/usr/bin/env python3
"""Emit plan.json from a finished migration run.

Copies already-validated values from a run's artifacts into a `plan.json`
summary the AWS Startups Migrate web import page ingests. It GENERATES nothing:
every field is copied from a validated artifact or omitted, because every extra
field is a mistake surface.

Fail-open by design: any missing or unreadable input leaves the migration
successful, writes no file, prints the reason, and stays re-runnable. A missed
handoff must never cost a customer their migration result.

Scope: GCP and Heroku infra runs (the two skills that persist a cost estimate).
The OpenAI/LLM-to-Bedrock path has no persisted cost artifact and is a follow-up.

Usage:
  python3 scripts/emit-plan-json.py --migration-dir <dir>

Reads:
  <dir>/.phase-status.json              run_id, owning_skill
  <dir>/estimation-infra.json           projected_costs.aws_monthly_balanced, current_costs.*
  <PLUGIN_ROOT>/.claude-plugin/plugin.json   version

Writes:
  <dir>/plan.json

Status line (stdout, machine-readable):
  PLAN_OK   | path=<dir>/plan.json | platform=GCP | scope=INFRA_ONLY
  PLAN_SKIP | reason=<why>                 (fail-open; exit 0, no file written)
Exit code is 0 for success AND for every fail-open skip; only a usage error is non-zero.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

# scripts/ -> plugin root (holds .claude-plugin/plugin.json).
PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Highest plan.json schema the web import page understands (kept in lock-step there).
SCHEMA_VERSION = 1

# owning_skill (telemetry id written to .phase-status.json at _init) ->
# sourcePlatform. Not generated data: each skill records its own id at _init and
# never changes it. LLM_TO_BEDROCK (OpenAI) is intentionally absent — it has no
# persisted cost artifact to copy, so it is a follow-up.
SKILL_TO_PLATFORM = {
    "GCP_TO_AWS": "GCP",
    "HEROKU_TO_AWS": "HEROKU",
}

# We copy the "balanced" AWS scenario (projected_costs.aws_monthly_balanced), so the
# basis the web contract records for that figure is BALANCED.
AWS_MONTHLY_BASIS = "BALANCED"

# Bounds the strict web import contract enforces. Mirrored here so an out-of-bounds
# value is dropped (or the handoff fails open) locally rather than being emitted and
# rejecting the whole import: USD amounts <= $100M, at most 100 service items, each
# serviceName at most 128 chars.
MAX_USD_AMOUNT = 100_000_000
MAX_SERVICE_ITEMS = 100
MAX_SERVICE_NAME_LEN = 128

# Naming for the write temp files, shared by the writer and the orphan sweep below.
_TEMP_PREFIX = ".plan-"
_TEMP_SUFFIX = ".json.tmp"
# A real write finishes in milliseconds, so any temp older than this is an orphan
# abandoned by a crashed run and safe to reclaim without racing a live writer.
_ORPHAN_TEMP_AGE_S = 3600

# The current-cost key each platform writes. Checked first so an extra *_monthly
# field in current_costs can't be copied into sourceMonthly by accident.
PLATFORM_SOURCE_KEY = {
    "GCP": "gcp_monthly",
    "HEROKU": "heroku_monthly",
}


class SkipEmit(Exception):
    """Fail-open signal: a reason to skip writing plan.json without failing the run."""


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _is_amount(value: object) -> bool:
    """True for a real, finite, non-negative JSON number.

    Excludes bool (a Python int subclass, so a JSON `true` would otherwise slip
    through) and non-finite floats (json.load accepts Infinity/NaN by default, and
    json.dumps would then emit the literal tokens `Infinity`/`NaN`, which the strict
    web import rejects). The USD cap is checked SEPARATELY by callers so an over-cap
    value can be diagnosed distinctly from a missing/malformed one.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _is_usable_amount(value: object) -> bool:
    """A non-negative number within the contract's USD cap — the values safe to copy
    into OPTIONAL cost fields (service items, sourceMonthly), which are simply dropped
    when over cap rather than failing the whole handoff."""
    return _is_amount(value) and value <= MAX_USD_AMOUNT


def _import_str_len(text: str) -> int:
    """Length as the strict web schema (JS/TS) counts it — UTF-16 code units, not
    Python code points — so the serviceName bound matches the import exactly even for
    astral-plane characters (which are one code point but two UTF-16 units)."""
    return len(text.encode("utf-16-le")) // 2


def _source_monthly(current_costs: object, source_platform: str) -> float | None:
    """The numeric monthly source-platform cost if present, else None.

    `current_costs` carries a skill-specific key (e.g. gcp_monthly / heroku_monthly)
    and may instead mark the baseline unavailable (no billing access), in which case
    there is no number to copy and sourceMonthly is omitted. The platform's own key
    is preferred so an unrelated *_monthly field can't be copied by accident.
    """
    if not isinstance(current_costs, dict):
        return None
    # Honor ONLY the platform's own key. No fallback to any other *_monthly field:
    # copying an unrelated one (e.g. support_monthly) would fabricate a source figure.
    preferred = PLATFORM_SOURCE_KEY.get(source_platform)
    if preferred and _is_usable_amount(current_costs.get(preferred)):
        return current_costs[preferred]
    return None


def _service_items(projected: object) -> list[dict]:
    """Per-service line items copied from projected_costs.breakdown.

    The breakdown is keyed by service, and its shape varies across skills and rows.
    An entry is either a bare monthly number, or an object carrying the figure under
    `monthly` (GCP core services) or `mid` (observability / Heroku scenarios) plus an
    optional `service` display label; the key is the fallback display name. Nested
    `alternative`/`components`/sub-cost objects are ignored — only the entry's own
    figure is read. The "total" rollup row, any entry with no usable amount, and any
    name over the contract length are skipped; GCP runs may carry an empty breakdown.

    classification is INFRASTRUCTURE — always correct here because this writer only
    emits INFRA_ONLY runs (AI-inclusive runs are skipped upstream), so it is implied
    by the scope, not generated. `category` is not persisted, so it is omitted.
    """
    if not isinstance(projected, dict):
        return []
    breakdown = projected.get("breakdown")
    if not isinstance(breakdown, dict):
        return []

    items: list[dict] = []
    for key, entry in breakdown.items():
        # Drop the aggregate row (any casing) so the total is never shown as a service.
        if not isinstance(key, str) or key.strip().lower() == "total":
            continue

        if _is_usable_amount(entry):
            # Bare-number form: {"compute": 75}.
            name, monthly = key, entry
        elif isinstance(entry, dict):
            # Object form: the figure is under `monthly` (GCP) or `mid`
            # (observability/Heroku) — one key per row. Take the first PRESENT key and
            # validate that one; don't substitute the other when the primary figure is
            # present but out of range, which would misreport a different number.
            raw = next((entry[k] for k in ("monthly", "mid") if k in entry), None)
            if not _is_usable_amount(raw):
                continue
            monthly = raw
            label = entry.get("service")
            name = label if isinstance(label, str) and label.strip() else key
        else:
            continue

        name = name.strip()
        # Skip a blank name, a rollup surfaced via the label (service:"Total"), and a
        # name the strict import would reject for length.
        if not name or name.lower() == "total" or _import_str_len(name) > MAX_SERVICE_NAME_LEN:
            continue
        items.append(
            {
                "serviceName": name,
                "monthlyCost": monthly,
                "classification": "INFRASTRUCTURE",
            }
        )
    return items


def build_plan(migration_dir: Path, plugin_json_path: Path) -> tuple[dict, str, str]:
    """Build the plan dict from validated artifacts, or raise SkipEmit to fail open."""
    status_path = migration_dir / ".phase-status.json"
    infra_path = migration_dir / "estimation-infra.json"

    if not status_path.is_file():
        raise SkipEmit("no .phase-status.json in migration dir")
    if not infra_path.is_file():
        raise SkipEmit("no estimation-infra.json (no cost estimate to hand off)")

    status = _load_json(status_path)
    if not isinstance(status, dict):
        raise SkipEmit(".phase-status.json is not a JSON object")

    owning_skill = status.get("owning_skill")
    # Guard the type before the dict lookup: a non-string (e.g. a list) is unhashable
    # and would raise TypeError, and only a string can name a skill anyway.
    source_platform = SKILL_TO_PLATFORM.get(owning_skill) if isinstance(owning_skill, str) else None
    if source_platform is None:
        raise SkipEmit(f"owning_skill {owning_skill!r} has no web handoff yet")

    # Scope reflects what the run actually costed. A run that also costed AI
    # (estimation-ai.json present) is FULL or AI_ONLY, and its awsMonthly must fold
    # in the Bedrock cost under a *_PLUS_AI_SUM basis — that merge is a follow-up.
    # This writer emits only the pure-infra case, so skip any AI-inclusive run
    # rather than mislabel it INFRA_ONLY with an infra-only cost.
    if (migration_dir / "estimation-ai.json").is_file():
        raise SkipEmit("AI-inclusive run (FULL/AI_ONLY) — infra-only handoff is a follow-up")
    scope = "INFRA_ONLY"

    # runId carries the attribution the handoff exists for; without it there is
    # nothing to hand off, so fail open rather than write an unattributable plan.
    # Must be a non-empty string: a numeric/other run_id would be copied verbatim and
    # rejected by the strict web schema (which types runId as a string).
    run_id = status.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise SkipEmit("no usable run_id in .phase-status.json")

    infra = _load_json(infra_path)
    if not isinstance(infra, dict):
        raise SkipEmit("estimation-infra.json is not a JSON object")
    projected = infra.get("projected_costs")
    aws_monthly = projected.get("aws_monthly_balanced") if isinstance(projected, dict) else None
    if not _is_amount(aws_monthly):
        raise SkipEmit("no usable projected_costs.aws_monthly_balanced")
    # Distinct from the missing/malformed case above: a real figure that merely
    # exceeds the contract cap, so an on-call reader isn't sent hunting for corruption.
    if aws_monthly > MAX_USD_AMOUNT:
        raise SkipEmit("projected_costs.aws_monthly_balanced exceeds the supported maximum")

    plan: dict = {
        "schemaVersion": SCHEMA_VERSION,
        "sourcePlatform": source_platform,
        "scope": scope,
        "runId": run_id,
        "cost": {
            "awsMonthly": aws_monthly,
            "awsMonthlyBasis": AWS_MONTHLY_BASIS,
        },
    }

    source_monthly = _source_monthly(infra.get("current_costs"), source_platform)
    if source_monthly is not None:
        plan["cost"]["sourceMonthly"] = source_monthly

    service_items = _service_items(projected)
    # The contract caps the list at 100. If a breakdown yields more, there is no
    # meaningful subset to pick, so omit the optional field rather than send an
    # over-limit list that would reject the whole handoff.
    if 0 < len(service_items) <= MAX_SERVICE_ITEMS:
        plan["cost"]["awsServiceItems"] = service_items

    # The web contract's field is `producerVersion` (named for the producer, not the
    # plugin, so a partner submission needs no second contract) — NOT `pluginVersion`.
    # The schema is strict, so a wrong key would make the whole import fail.
    # producerVersion is optional: a missing OR unreadable plugin.json omits it rather
    # than sinking an otherwise-valid handoff.
    if plugin_json_path.is_file():
        try:
            version = _load_json(plugin_json_path).get("version")
        except Exception:
            # producerVersion is optional, so ANY fault reading plugin.json (decode
            # error, non-object manifest, even a pathological RecursionError) just omits
            # the version — it must never sink an otherwise-valid handoff.
            version = None
        if isinstance(version, str) and version:
            plan["producerVersion"] = version

    return plan, source_platform, scope


def _unlink_quietly(path: Path) -> None:
    """Delete a file if it exists, ignoring any error (best-effort). Used both to drop
    a stale plan.json from an earlier run and to clean up the write temp file."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _sweep_orphan_temps(directory: Path) -> None:
    """Best-effort removal of write temps abandoned by a crashed earlier run. Because
    unique mkstemp names are no longer reused, nothing else reclaims them; the age
    gate (a real write finishes in milliseconds) keeps a concurrent run's in-flight
    temp from being deleted."""
    cutoff = time.time() - _ORPHAN_TEMP_AGE_S
    try:
        candidates = list(directory.glob(_TEMP_PREFIX + "*" + _TEMP_SUFFIX))
    except OSError:
        return
    for candidate in candidates:
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migration-dir",
        type=Path,
        required=True,
        help="The run's $MIGRATION_DIR (holds .phase-status.json and estimation-infra.json).",
    )
    parser.add_argument(
        "--plugin-json",
        type=Path,
        default=PLUGIN_ROOT / ".claude-plugin" / "plugin.json",
        help="Path to the plugin manifest read for producerVersion (defaults to this plugin's).",
    )
    args = parser.parse_args()
    migration_dir: Path = args.migration_dir
    out_path = migration_dir / "plan.json"

    # Reclaim any temp abandoned by a crashed earlier run, on EVERY invocation (not
    # only the write path) so a dir that keeps failing open still gets cleaned up.
    _sweep_orphan_temps(migration_dir)

    try:
        plan, platform, scope = build_plan(migration_dir, args.plugin_json)
    except SkipEmit as skip:
        # Deterministic disqualification (the run grew to include AI, lost its run_id,
        # has no cost estimate, etc.): this run should have NO plan, so drop a stale
        # one left by an earlier run.
        _unlink_quietly(out_path)
        print(f"PLAN_SKIP | reason={skip}")
        return 0
    except Exception as err:
        # Fail open on ANY error, not just the expected OSError/ValueError: a missed
        # handoff must never break the migration. But this is an UNCLASSIFIABLE input
        # fault (corrupt/unreadable artifact, RecursionError, ...) — we cannot tell
        # whether a prior plan.json is stale, so leave it: a transient glitch must not
        # destroy a previously-valid handoff. A later clean run overwrites it.
        print(f"PLAN_SKIP | reason=unreadable input: {err}")
        return 0

    # Write atomically to a UNIQUE, exclusively-created temp in the same dir, then
    # rename into place. mkstemp (O_EXCL, mode 0600) means concurrent reruns never
    # share a temp path and a pre-existing temp symlink can't be followed, so a
    # crash/kill can only leave an orphan temp — never a truncated or cross-written
    # plan.json the import might ingest.
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(out_path.parent), prefix=_TEMP_PREFIX, suffix=_TEMP_SUFFIX)
    except OSError as err:
        print(f"PLAN_SKIP | reason=could not write plan.json: {err}")
        return 0
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(plan, indent=2) + "\n")
        # Keep mkstemp's private 0600 (owner-only): plan.json holds the customer's
        # cost figures, and the only consumer is the same user's browser upload, so a
        # secure default loses nothing. Intentional — not the umask-wide 0644 that a
        # plain write would have produced.
        os.replace(tmp_path, out_path)
    except Exception as err:
        # Fail open on any write-path fault. os.replace is atomic, so on failure a
        # prior run's plan.json is untouched and still valid — leave it and clean up
        # only this invocation's own temp, never a good handoff.
        _unlink_quietly(tmp_path)
        print(f"PLAN_SKIP | reason=could not write plan.json: {err}")
        return 0

    print(f"PLAN_OK | path={out_path} | platform={platform} | scope={scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
