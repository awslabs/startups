"""BigQuery metadata scanner — yields normative EntityMetadata (R2, R3, R4, R23.1-.2).

Read-only: captures table/view/mview/routine *metadata and definitions* only; never
executes SELECT against data rows (R22.2). Resilient: transient API errors (429/500/503)
retried with exponential backoff (R23.1); per-entity failures recorded and skipped (R23.2).

Implements the design.md § Component Interfaces ``BigQueryScanner`` contract — the frozen
seam other modules build on is ``scan() -> Iterator[EntityMetadata]`` and
``self.failures: list[FailureRecord]``. (Issue #6 / 1.1.)
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery
from google.oauth2 import service_account

from bq_assess.core.classifier import classify_population
from bq_assess.models import (
    ColumnSchema,
    EntityMetadata,
    EntityPopulation,
    EntityType,
    FailureRecord,
    RangePartitionConfig,
    RoutineMetadata,
    TimePartitionConfig,
)

logger = logging.getLogger(__name__)

# Retry configuration for transient BigQuery API errors (R23.1)
RETRY_CONFIG = {
    "max_retries": 3,
    "initial_delay_seconds": 1.0,
    "backoff_multiplier": 2.0,  # 1s, 2s, 4s
    "retryable_status_codes": [429, 500, 503],
}

# BigQuery table_type string -> EntityType (R4.1). Unknown types fall back to TABLE.
_TABLE_TYPE_MAP: dict[str, EntityType] = {
    "TABLE": EntityType.TABLE,
    "EXTERNAL": EntityType.EXTERNAL,
    "VIEW": EntityType.VIEW,
    "MATERIALIZED_VIEW": EntityType.MATERIALIZED_VIEW,
}


class ScannerError(Exception):
    """Raised when the scanner encounters a fatal error (auth, project-not-found)."""


def population_for(entity_type: EntityType) -> EntityPopulation:
    """Deprecated shim — delegates to the canonical classifier (issue #7).

    Kept as a thin alias so any external caller of the old name still works; new code
    should import ``classify_population`` from ``core/classifier`` directly. (The #6 seam
    note is resolved: the classifier is now the single source of truth.)
    """
    return classify_population(entity_type)


class BigQueryScanner:
    """Scans BigQuery project metadata with retry logic and per-entity resilience.

    Supports service-account JSON credentials or Application Default Credentials.
    Accesses metadata and object definitions only — never reads data rows (R22.2).
    """

    def __init__(
        self,
        project_id: str,
        credentials_path: str | None = None,
        use_adc: bool = False,
        max_concurrent_requests: int = 16,
    ) -> None:
        self._project_id = project_id
        self._credentials_path = credentials_path
        self._use_adc = use_adc
        self._max_concurrent = max_concurrent_requests
        self._client: bigquery.Client | None = None
        self.failures: list[FailureRecord] = []

    # ------------------------------------------------------------------
    # Client initialisation
    # ------------------------------------------------------------------

    def _get_client(self) -> bigquery.Client:
        """Lazily create and return the BigQuery client (read-only scope)."""
        if self._client is not None:
            return self._client

        if self._credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                self._credentials_path,
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
            )
            self._client = bigquery.Client(
                project=self._project_id, credentials=credentials
            )
        elif self._use_adc:
            self._client = bigquery.Client(project=self._project_id)
        else:
            raise ScannerError(
                "No credentials provided. Supply a service account JSON path "
                "or enable Application Default Credentials (--use-adc)."
            )

        self._expand_connection_pool(self._client)
        return self._client

    def _expand_connection_pool(self, client: bigquery.Client) -> None:
        """Resize the HTTP connection pool to match concurrency, preventing pool-full warnings."""
        from requests.adapters import HTTPAdapter

        pool_size = self._max_concurrent + 10
        adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        client._http.mount("https://", adapter)
        client._http.mount("http://", adapter)

    # ------------------------------------------------------------------
    # Credential validation (R2)
    # ------------------------------------------------------------------

    def validate_credentials(self) -> bool:
        """Run a lightweight metadata-only call to verify read access (R2.1).

        Returns ``True`` on success; raises :class:`ScannerError` with a descriptive
        message distinguishing invalid-credentials / insufficient-permissions /
        project-not-found on failure (R2.2).
        """
        try:
            client = self._get_client()
            _ = list(client.list_datasets(max_results=1))
            return True
        except ScannerError:
            raise
        except Exception as exc:
            raise ScannerError(_describe_auth_error(exc)) from exc

    # ------------------------------------------------------------------
    # Scanning (R3, R4, R23)
    # ------------------------------------------------------------------

    def scan(
        self, dataset_filter: list[str] | None = None
    ) -> Iterator[EntityMetadata]:
        """Yield :class:`EntityMetadata` for every entity in the project.

        Scans, per dataset: tables/views/materialized-views/external (via ``list_tables``
        + ``get_table``) and persistent routines (via ``list_routines``). When
        ``dataset_filter`` is provided, only those datasets are scanned; otherwise all
        datasets in the project (R3.4).

        Transient API errors are retried (R23.1). Per-entity errors are recorded in
        ``self.failures`` and skipped so one bad entity never aborts the scan (R23.2).
        """
        client = self._get_client()
        self.failures = []

        datasets = self._list_datasets_with_retry(client)
        if dataset_filter:
            filter_set = set(dataset_filter)
            datasets = [ds for ds in datasets if ds.dataset_id in filter_set]

        for dataset_ref in datasets:
            dataset_id = dataset_ref.dataset_id
            yield from self._scan_tables(client, dataset_id)
            yield from self._scan_routines(client, dataset_id)

    def _scan_tables(
        self, client: bigquery.Client, dataset_id: str
    ) -> Iterator[EntityMetadata]:
        """Yield EntityMetadata for tables/views/mviews/external in a dataset.

        Uses a thread pool to parallelize get_table calls (I/O-bound). On early exit
        (KeyboardInterrupt, GeneratorExit) pending futures are cancelled immediately.
        """
        try:
            table_items = self._list_tables_with_retry(client, dataset_id)
        except Exception as exc:  # dataset-level failure → record + continue (R23.2)
            logger.error("Failed to list tables in %s: %s", dataset_id, exc)
            self.failures.append(
                FailureRecord(entity_name=dataset_id, stage="scan", error=str(exc))
            )
            return

        yield from self._parallel_fetch(
            table_items,
            lambda item: self._get_table_with_retry(client, item.reference),
            lambda item: f"{item.dataset_id}.{item.table_id}",
            _to_entity_metadata,
        )

    def _scan_routines(
        self, client: bigquery.Client, dataset_id: str
    ) -> Iterator[EntityMetadata]:
        """Yield EntityMetadata for persistent routines (UDFs / procedures) — R3.3."""
        try:
            routines = self._list_routines_with_retry(client, dataset_id)
        except Exception as exc:
            logger.error("Failed to list routines in %s: %s", dataset_id, exc)
            self.failures.append(
                FailureRecord(
                    entity_name=f"{dataset_id} (routines)",
                    stage="scan",
                    error=str(exc),
                )
            )
            return

        yield from self._parallel_fetch(
            routines,
            lambda r: _retry(lambda: client.get_routine(r.reference)),
            lambda r: f"{dataset_id}.{r.routine_id}",
            lambda full_routine: _routine_to_entity(full_routine, dataset_id),
        )

    # ------------------------------------------------------------------
    # Parallel fetch helper
    # ------------------------------------------------------------------

    def _parallel_fetch(self, items, fetch_fn, name_fn, transform_fn) -> Iterator[EntityMetadata]:
        """Submit fetch_fn for each item via thread pool; yield transform_fn(result).

        On early exit (KeyboardInterrupt, GeneratorExit) pending futures are cancelled
        immediately — the process never blocks waiting for in-flight work to drain.
        """
        pool = ThreadPoolExecutor(max_workers=self._max_concurrent)
        futures: dict[Future, str] = {}
        try:
            for item in items:
                futures[pool.submit(fetch_fn, item)] = name_fn(item)
            for future in as_completed(futures):
                full_name = futures[future]
                try:
                    yield transform_fn(future.result())
                except Exception as exc:
                    logger.error("Failed to scan entity %s: %s", full_name, exc)
                    self.failures.append(
                        FailureRecord(entity_name=full_name, stage="scan", error=str(exc))
                    )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Retry wrappers
    # ------------------------------------------------------------------

    def _list_datasets_with_retry(self, client: bigquery.Client) -> list:
        return _retry(lambda: list(client.list_datasets()))

    def _list_tables_with_retry(self, client: bigquery.Client, dataset_id: str) -> list:
        return _retry(lambda: list(client.list_tables(dataset_id)))

    def _list_routines_with_retry(
        self, client: bigquery.Client, dataset_id: str
    ) -> list:
        return _retry(lambda: list(client.list_routines(dataset_id)))

    def _get_table_with_retry(
        self, client: bigquery.Client, table_ref: bigquery.TableReference
    ) -> bigquery.Table:
        return _retry(lambda: client.get_table(table_ref))


# ======================================================================
# Module-level helpers
# ======================================================================


def _retry(fn, config: dict | None = None):
    """Execute *fn* with exponential-backoff retries on transient errors (R23.1)."""
    cfg = config or RETRY_CONFIG
    max_retries: int = cfg["max_retries"]
    delay: float = cfg["initial_delay_seconds"]
    multiplier: float = cfg["backoff_multiplier"]
    retryable: set[int] = set(cfg["retryable_status_codes"])

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):  # 0 = first try, 1..3 = retries
        try:
            return fn()
        except GoogleAPICallError as exc:
            last_exc = exc
            if exc.code not in retryable or attempt == max_retries:
                raise
            jittered = delay * (0.5 + random.random())  # nosec B311 - retry jitter, not cryptographic
            logger.warning(
                "Transient error (code=%s), retrying in %.1fs (attempt %d/%d)",
                exc.code,
                jittered,
                attempt + 1,
                max_retries,
            )
            time.sleep(jittered)
            delay *= multiplier
        except Exception:
            raise

    raise last_exc  # type: ignore[misc]  # unreachable; satisfies type checkers


def _describe_auth_error(exc: Exception) -> str:
    """Return a user-friendly description for auth/permission errors (R2.2)."""
    msg = str(exc).lower()
    if "403" in msg or "permission" in msg:
        return (
            f"Insufficient permissions for project: {exc}. "
            "Ensure the principal has the bigquery.metadataViewer (or dataViewer) role."
        )
    if "404" in msg or "not found" in msg:
        return f"Project not found or inaccessible: {exc}"
    if "invalid" in msg or "credential" in msg or "401" in msg:
        return f"Invalid credentials: {exc}"
    return f"Credential validation failed: {exc}"


def _entity_type_for(table: bigquery.Table) -> EntityType:
    """Map a BigQuery table_type to EntityType (R4.1); unknown → TABLE."""
    return _TABLE_TYPE_MAP.get((table.table_type or "TABLE").upper(), EntityType.TABLE)


def _to_entity_metadata(table: bigquery.Table) -> EntityMetadata:
    """Convert a ``bigquery.Table`` to :class:`EntityMetadata` (tables/views/mviews)."""
    entity_type = _entity_type_for(table)
    population = classify_population(entity_type)

    columns = [_to_column_schema(f) for f in table.schema] if table.schema else []

    time_part = _to_time_partition(table)
    range_part = _to_range_partition(table)  # R3.8 — captured distinctly
    clustering = list(table.clustering_fields) if table.clustering_fields else None

    view_query = getattr(table, "view_query", None)
    mview_query = getattr(table, "mview_query", None)

    depends_on = _extract_dependencies(view_query or mview_query)

    return EntityMetadata(
        entity_id=table.table_id,
        dataset_id=table.dataset_id,
        full_name=f"{table.dataset_id}.{table.table_id}",
        entity_type=entity_type,
        population=population,
        num_rows=table.num_rows or 0,
        num_bytes=table.num_bytes or 0,
        columns=columns,
        time_partitioning=time_part,
        range_partitioning=range_part,
        clustering_fields=clustering,
        view_query=view_query,
        mview_query=mview_query,
        routine=None,
        depends_on=depends_on,
        last_modified=_normalize_modified(table.modified),
    )


def _routine_to_entity(routine, dataset_id: str) -> EntityMetadata:
    """Convert a fully-fetched routine to a ROUTINE :class:`EntityMetadata` (R3.3)."""

    arguments = [
        arg.name or f"arg{i}"
        for i, arg in enumerate(routine.arguments or [])
    ]
    routine_meta = RoutineMetadata(
        name=routine.routine_id,
        language=routine.language or "SQL",
        arguments=arguments,
        body=routine.body or "",
        routine_type=str(routine.type_ or "SCALAR_FUNCTION"),
    )

    depends_on = _extract_dependencies(routine.body)

    return EntityMetadata(
        entity_id=routine.routine_id,
        dataset_id=dataset_id,
        full_name=f"{dataset_id}.{routine.routine_id}",
        entity_type=EntityType.ROUTINE,
        population=EntityPopulation.REBUILT,
        num_rows=0,
        num_bytes=0,
        columns=[],
        time_partitioning=None,
        range_partitioning=None,
        clustering_fields=None,
        view_query=None,
        mview_query=None,
        routine=routine_meta,
        depends_on=depends_on,
        last_modified=_normalize_modified(getattr(routine, "modified", None)),
    )


def _to_time_partition(table: bigquery.Table) -> TimePartitionConfig | None:
    """Capture time partitioning; field=None models ingestion-time (_PARTITIONTIME)."""
    tp = table.time_partitioning
    if tp is None:
        return None
    return TimePartitionConfig(type=tp.type_ or "DAY", field=tp.field)


def _to_range_partition(table: bigquery.Table) -> RangePartitionConfig | None:
    """Capture range partitioning distinctly from time partitioning (R3.8)."""
    rp = getattr(table, "range_partitioning", None)
    if rp is None:
        return None
    rng = getattr(rp, "range_", None)
    return RangePartitionConfig(
        field=rp.field,
        start=int(getattr(rng, "start", 0) or 0),
        end=int(getattr(rng, "end", 0) or 0),
        interval=int(getattr(rng, "interval", 1) or 1),
    )


def _to_column_schema(field: bigquery.SchemaField) -> ColumnSchema:
    """Recursively convert a BigQuery ``SchemaField`` to :class:`ColumnSchema`.

    Nesting is preserved (no flattening) — STRUCT/RECORD children recurse (R6.2).
    """
    nested = [_to_column_schema(f) for f in field.fields] if field.fields else []
    return ColumnSchema(
        name=field.name,
        field_type=field.field_type,
        mode=field.mode or "NULLABLE",
        fields=nested,
    )


# Matches `project.dataset.table` or `dataset.table` references inside FROM/JOIN clauses,
# optionally backtick-quoted. Best-effort dependency extraction (R4.5); refined in 4.x.
_DEP_RE = re.compile(
    r"(?:FROM|JOIN)\s+`?([A-Za-z0-9_.\-]+)`?",
    re.IGNORECASE,
)


def _extract_dependencies(sql: str | None) -> list[str]:
    """Best-effort parse of referenced tables from view/mview/routine SQL (R4.5).

    Returns ``dataset.table`` FQNs (project prefix stripped), de-duplicated, order-stable.
    Deliberately conservative — relationship inference (issue 4.1) refines this later.
    """
    if not sql:
        return []
    seen: dict[str, None] = {}
    for raw in _DEP_RE.findall(sql):
        ref = raw.strip("`").strip()
        if not ref or "." not in ref:
            continue
        parts = ref.split(".")
        # Normalize project.dataset.table -> dataset.table
        fqn = ".".join(parts[-2:]) if len(parts) >= 2 else ref
        seen.setdefault(fqn, None)
    return list(seen.keys())


def _normalize_modified(modified: datetime | None) -> datetime:
    """Return a tz-aware UTC datetime for the entity's last-modified time."""
    if modified is None:
        return datetime.now(timezone.utc)
    if modified.tzinfo is None:
        return modified.replace(tzinfo=timezone.utc)
    return modified
