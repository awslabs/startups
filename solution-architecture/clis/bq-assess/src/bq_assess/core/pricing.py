"""BigQuery pricing-model detection — on-demand vs capacity / Editions (R16, V4/V5).

``PricingDetector.detect()`` classifies how a Source is billed so the Cost Comparison (R18)
prices the BigQuery side against the *real* model, never an assumed one (R16.4). It resolves
to exactly four outcomes:

  1. ``--reservation-config`` supplied        → CAPACITY + figures, HIGH confidence (R16.2)
  2. JOBS carry a non-null ``reservation_id``  → CAPACITY + edition, MEDIUM (figures unknown)
  3. JOBS all-NULL ``reservation_id``          → ON_DEMAND, MEDIUM (lookback-window caveat)
  4. no usable signal (empty / all-SCRIPT /    → ON_DEMAND, LOW, prompt for --reservation-config
     missing ``jobs.listAll``)                   (R16.3 / P20: never silently guess capacity)

The primary signal is ``INFORMATION_SCHEMA.JOBS.reservation_id`` (NULL ⇒ on-demand, non-null ⇒
capacity) — verified V5, simpler than reading the reservation views and needing no perms beyond
``jobs.listAll``. SCRIPT *parent* jobs report NULL ``reservation_id`` even under capacity, so
they are excluded before classification (V5 caveat).

The detector never returns ``model == UNKNOWN`` and never raises: an undeterminable verdict
collapses to ON_DEMAND at LOW confidence with a prompting ``source_note`` (R16.3). Verified
constants live in ``core/pricing_constants.py`` (dated, overridable; read at call time).

⚠️ Scope (issue 5.1): the model is classified from JOBS; capacity slot *figures* come only from
``--reservation-config``. Auto-reading baseline/max/commitment out of the reservation views is
deferred (their column schema is unverified — see SCRUM_NOTES § Detector scope 2026-06-15), so
auto-detected CAPACITY is reported at MEDIUM with a prompt for ``--reservation-config``.
"""

from __future__ import annotations

import logging

from bq_assess.core import jobs_query
from bq_assess.core import pricing_constants as k
from bq_assess.models import BQPricingModel, ConfidenceLevel, PricingDetection

logger = logging.getLogger(__name__)


class PricingDetector:
    """Detect the BigQuery billing model for a Source (R16)."""

    def detect(
        self,
        client,
        project_id: str,
        reservation_config: dict | None,
        location: str = "US",
    ) -> PricingDetection:
        """Classify the Source's pricing model. See module docstring for the four outcomes.

        ``location`` region-qualifies the JOBS query (``\\`region-<location>\\```); it defaults
        to ``"US"`` to match the US-only pricing constants (V4). Never raises (R16.3/P20).
        """
        # 1. A supplied --reservation-config is a confidence rung above auto-detection (R16.2):
        #    it forces CAPACITY and carries the figures the Cost Estimator prices from. Read with
        #    .get() so a partial/malformed dict degrades to None rather than raising (P20).
        if reservation_config:
            edition = reservation_config.get("edition")
            commitment_slots = reservation_config.get("commitment_slots")
            note = (
                f"Capacity model from supplied --reservation-config (manual_input); "
                f"V4/V5 {k.V5_CONFIRMED_DATE}."
            )
            # STANDARD edition has no true capacity/slot commitments (V4). Surface — don't
            # silently price — a config that claims STANDARD with a commitment.
            if (
                edition is not None
                and edition not in k.V4_EDITIONS_WITH_CAPACITY_COMMITMENTS
                and commitment_slots
            ):
                note += (
                    f" ⚠️ Edition {edition} has no true capacity/slot commitments — the supplied "
                    f"commitment_slots={commitment_slots} is unexpected (V4); verify the figures."
                )
            return PricingDetection(
                model=BQPricingModel.CAPACITY,
                confidence=ConfidenceLevel.HIGH,
                edition=edition,
                baseline_slots=reservation_config.get("baseline_slots"),
                max_slots=reservation_config.get("max_slots"),
                commitment_slots=commitment_slots,
                commitment_plan=reservation_config.get("commitment_plan"),
                source_note=note,
            )

        rows = self._read_jobs(client, project_id, location)
        # Rows are GROUPED (reservation_id, edition, job_count) — see _read_jobs. Each group
        # summarizes job_count jobs; legacy per-job shaped rows (tests, file import) count
        # as 1 each via the job_count default.
        # Defense-in-depth: SCRIPT parents are excluded at the SQL level (jobs_query shared
        # WHERE) AND here. The SQL filter is the primary guard; this Python filter ensures
        # correctness if rows arrive via a non-SQL path (tests, file import) or if the
        # constant is overridden at runtime (R18.7). Grouped rows carry no statement_type,
        # so the filter only bites on per-job shaped input.
        leaf_rows = [
            r for r in rows
            if r.get(k.V5_JOBS_STATEMENT_TYPE_COLUMN) != k.V5_JOBS_SCRIPT_STATEMENT_TYPE
        ]
        capacity_rows = [
            r for r in leaf_rows if r.get(k.V5_JOBS_RESERVATION_ID_COLUMN) is not None
        ]
        n = sum(_group_count(r) for r in leaf_rows)

        if capacity_rows:
            # Any capacity job ⇒ the project is (at least partly) capacity-billed. Classify it
            # so the cost step never under-prices a reserved Source (R16.4). Edition comes from
            # the JOBS edition column; slot figures are not auto-enriched in 5.1 (MEDIUM).
            n_capacity = sum(_group_count(r) for r in capacity_rows)
            edition = next(
                (r.get(k.V5_JOBS_EDITION_COLUMN) for r in capacity_rows
                 if r.get(k.V5_JOBS_EDITION_COLUMN)),
                None,
            )
            return PricingDetection(
                model=BQPricingModel.CAPACITY,
                confidence=ConfidenceLevel.MEDIUM,
                edition=edition,
                source_note=(
                    f"Capacity model detected from INFORMATION_SCHEMA.JOBS."
                    f"{k.V5_JOBS_RESERVATION_ID_COLUMN} (non-null on {n_capacity} of {n} "
                    f"leaf jobs; edition={edition}). Slot figures not auto-detected — supply "
                    f"--reservation-config for baseline/max/commitment. V5 {k.V5_CONFIRMED_DATE}."
                ),
            )

        if not leaf_rows:
            # No usable leaf signal (empty job list, all-SCRIPT parents, or JOBS unreadable).
            # Undeterminable ⇒ default ON_DEMAND, mark LOW, prompt for --reservation-config.
            # Never return UNKNOWN and never raise (R16.3 / P20: don't silently guess capacity).
            return PricingDetection(
                model=BQPricingModel.ON_DEMAND,
                confidence=ConfidenceLevel.LOW,
                source_note=(
                    "Could not determine pricing model (no readable, non-SCRIPT job data); "
                    "defaulting to on-demand at LOW confidence — supply --reservation-config to "
                    f"classify a capacity Source. V5 {k.V5_CONFIRMED_DATE}."
                ),
            )

        return PricingDetection(
            model=BQPricingModel.ON_DEMAND,
            confidence=ConfidenceLevel.MEDIUM,
            source_note=(
                f"On-demand model detected from INFORMATION_SCHEMA.JOBS."
                f"{k.V5_JOBS_RESERVATION_ID_COLUMN} (NULL on all {n} leaf jobs); reflects the "
                f"query-log lookback window only. V5 {k.V5_CONFIRMED_DATE}."
            ),
        )

    def _read_jobs(self, client, project_id: str, location: str) -> list:
        """Read GROUPED (reservation_id, edition, job_count) rows from project job history.

        Delegates to ``core.jobs_query.read_reservation_groups`` (JOBS_BY_PROJECT,
        completed-query lookback, project/region-qualified, GROUP BY reservation/edition) —
        a handful of rows regardless of the Source's query volume (2026-07-08 storm audit:
        the per-job read was a multi-GB row stream on busy projects). Returns ``[]`` if the
        query cannot be run (e.g. missing ``jobs.listAll``) — the caller treats no-signal
        as undeterminable (R16.3), never an error.
        """
        return jobs_query.read_reservation_groups(client, project_id, location=location)


def _group_count(row) -> int:
    """Jobs summarized by a grouped row; per-job shaped rows (no job_count) count as 1."""
    try:
        return max(int(row.get("job_count", 1) or 1), 1)
    except (ValueError, TypeError):
        return 1
