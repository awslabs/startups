# Feature: collector/report split (2026-07-08 design)
"""Unit + property tests for the bundle package.

Covers:
- Write → load round-trip losslessness (entities incl. physical_bytes + nested STRUCTs,
  workload, pricing, rates, failures, queries) — the anti-drift guarantee's foundation.
- Strict manifest enforcement: schema-version mismatch refusal, checksum-tamper refusal,
  missing-required-file refusal, optional-file clean degrade.
- Zip ingestion: .zip == extracted directory, including a nested top-level folder.
- Disclaimer embedded in the manifest.
"""

from __future__ import annotations

import dataclasses
import json
import zipfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from bq_assess.bundle import Bundle, BundleLoader, BundleWriter, SCHEMA_VERSION
from bq_assess.bundle.loader import BundleError
from bq_assess.bundle.models import QueryRecord
from bq_assess.core.disclaimer import FULL_DISCLAIMER
from bq_assess.models import (
    BQPricingModel,
    ConfidenceLevel,
    FailureRecord,
    PricingDetection,
    SlotUtilization,
)
from tests.conftest import entity_metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(entities, **overrides) -> Bundle:
    defaults = dict(
        project_id="test-project",
        bq_location="australia-southeast1",
        aws_region="ap-southeast-2",
        entities=entities,
        failures=[FailureRecord(entity_name="ds.broken", stage="scan", error="403")],
        workload=SlotUtilization(
            avg_slots=10.0, p50_slots=8.0, p99_slots=40.0, peak_slots=55.0,
            active_hour_fraction=0.4, total_slot_ms=86_400_000, days_sampled=14,
            total_bytes_processed=5 * 10**12, total_bytes_billed=4 * 10**12,
            has_billed_bytes=True, total_queries=1200, lookback_days=30,
        ),
        pricing=PricingDetection(
            model=BQPricingModel.ON_DEMAND,
            confidence=ConfidenceLevel.HIGH,
            source_note="JOBS reservation_id NULL on all jobs (2026-07-08)",
        ),
        rates={"aws": {"rpu_hour": 0.45}, "gcp": {}, "is_live": True,
               "staleness_warning": "", "aws_region": "ap-southeast-2",
               "bq_location": "australia-southeast1"},
        queries=[
            QueryRecord(
                query="SELECT a FROM ds.t WHERE x = '?'",
                total_slot_ms=1234, total_bytes_processed=10**9,
                total_bytes_billed=10**9, statement_type="SELECT",
                creation_time="2026-07-01T10:00:00+00:00",
            ),
            QueryRecord(
                query="SELECT b FROM ds.u LIMIT ?",
                total_slot_ms=99, total_bytes_processed=0,
                total_bytes_billed=None, statement_type="SELECT",
                creation_time=None,
            ),
        ],
        storage_basis="measured",
        collector_version="0.3.0",
        created_at="2026-07-08T12:00:00+00:00",
    )
    defaults.update(overrides)
    return Bundle(**defaults)


def _entities_equal(a, b) -> bool:
    """Structural equality via dataclasses.asdict (nested columns included)."""
    return dataclasses.asdict(a) == dataclasses.asdict(b)


def _zip_bundle(src_dir: str, zip_path: Path, *, prefix: str = "") -> None:
    """Zip a bundle dir's files under an arc prefix — THE zip-builder for these tests."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for p in Path(src_dir).rglob("*"):
            if p.is_file():
                zf.write(p, prefix + p.name)


# ---------------------------------------------------------------------------
# Round-trip (property test over generated entities)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(entities=st.lists(entity_metadata(), min_size=1, max_size=6))
    def test_entities_round_trip_lossless(self, entities) -> None:
        """write → load preserves every entity field, incl. nested STRUCT columns,
        both partitionings, routines, and physical_bytes."""
        import tempfile
        for i, e in enumerate(entities):
            # Deduplicate full_names (strategy may collide) and populate physical_bytes
            e.full_name = f"{e.dataset_id}.{e.entity_id}_{i}"
            e.entity_id = f"{e.entity_id}_{i}"
            if e.num_bytes:
                e.physical_bytes = e.num_bytes // 2

        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(entities)
            bundle_dir = BundleWriter().write(bundle, tmp)
            loaded = BundleLoader().load(bundle_dir)

        assert len(loaded.entities) == len(entities)
        # Loader emits tables first, then routines — compare as maps by full_name.
        by_name = {e.full_name: e for e in loaded.entities}
        for original in entities:
            assert original.full_name in by_name, f"{original.full_name} lost in round-trip"
            assert _entities_equal(original, by_name[original.full_name])

    def test_full_bundle_round_trip(self, tmp_path) -> None:
        """Workload, pricing, rates, failures, queries, and manifest scalars survive."""
        entities = []
        bundle = _make_bundle(entities)
        bundle_dir = BundleWriter().write(bundle, str(tmp_path))
        loaded = BundleLoader().load(bundle_dir)

        assert loaded.project_id == bundle.project_id
        assert loaded.bq_location == bundle.bq_location
        assert loaded.aws_region == bundle.aws_region
        assert loaded.storage_basis == "measured"
        assert loaded.collector_version == "0.3.0"
        assert dataclasses.asdict(loaded.workload) == dataclasses.asdict(bundle.workload)
        assert dataclasses.asdict(loaded.pricing) == dataclasses.asdict(bundle.pricing)
        assert loaded.rates == bundle.rates
        assert [dataclasses.asdict(f) for f in loaded.failures] == [
            dataclasses.asdict(f) for f in bundle.failures
        ]
        assert [dataclasses.asdict(q) for q in loaded.queries] == [
            dataclasses.asdict(q) for q in bundle.queries
        ]

    def test_none_workload_pricing_rates_round_trip(self, tmp_path) -> None:
        """A degraded collection (no workload/pricing/rates/queries) loads cleanly."""
        bundle = _make_bundle([], workload=None, pricing=None, rates=None,
                              queries=None, failures=[])
        bundle_dir = BundleWriter().write(bundle, str(tmp_path))
        loaded = BundleLoader().load(bundle_dir)

        assert loaded.workload is None
        assert loaded.pricing is None
        assert loaded.rates is None
        assert loaded.queries is None
        assert loaded.failures == []

    def test_billed_key_absence_means_unavailable(self, tmp_path) -> None:
        """queries.jsonl omits total_bytes_billed when None — absent key must load
        back as None, never 0 (billed-unavailable semantics)."""
        bundle = _make_bundle([])
        bundle_dir = BundleWriter().write(bundle, str(tmp_path))

        lines = (Path(bundle_dir) / "queries.jsonl").read_text().strip().split("\n")
        rows = [json.loads(line) for line in lines]
        assert "total_bytes_billed" in rows[0]
        assert "total_bytes_billed" not in rows[1]

        loaded = BundleLoader().load(bundle_dir)
        assert loaded.queries[0].total_bytes_billed == 10**9
        assert loaded.queries[1].total_bytes_billed is None


# ---------------------------------------------------------------------------
# Manifest enforcement (strict)
# ---------------------------------------------------------------------------


class TestManifestEnforcement:
    def test_schema_version_mismatch_refused(self, tmp_path) -> None:
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        manifest_path = Path(bundle_dir) / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["schema_version"] = SCHEMA_VERSION + 1
        manifest_path.write_text(json.dumps(manifest))

        with pytest.raises(BundleError, match="schema version mismatch"):
            BundleLoader().load(bundle_dir)

    def test_tampered_file_refused(self, tmp_path) -> None:
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        tables = Path(bundle_dir) / "tables.json"
        tables.write_text('[{"full_name": "evil.injected", "entity_type": "TABLE"}]')

        with pytest.raises(BundleError, match="Checksum mismatch for tables.json"):
            BundleLoader().load(bundle_dir)

    def test_missing_required_file_refused(self, tmp_path) -> None:
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        (Path(bundle_dir) / "workload.json").unlink()

        with pytest.raises(BundleError, match="workload.json"):
            BundleLoader().load(bundle_dir)

    def test_manifest_listed_but_missing_queries_refused(self, tmp_path) -> None:
        """queries.jsonl listed in manifest but absent on disk → REFUSED. The writer
        only lists it when written, so listed-but-missing is always truncation or
        tampering — silently degrading was the 2026-07-08 review's finding 6."""
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        (Path(bundle_dir) / "queries.jsonl").unlink()

        with pytest.raises(BundleError, match="queries.jsonl"):
            BundleLoader().load(bundle_dir)

    def test_queries_absent_from_manifest_loads_cleanly(self, tmp_path) -> None:
        """A bundle collected with --exclude-query-text (no queries.jsonl written,
        none listed in the manifest) loads with queries=None."""
        bundle_dir = BundleWriter().write(_make_bundle([], queries=None), str(tmp_path))

        loaded = BundleLoader().load(bundle_dir)
        assert loaded.queries is None

    def test_partial_workload_json_raises_bundle_error(self, tmp_path) -> None:
        """A workload.json missing required SlotUtilization fields (hand-edited,
        re-checksummed) must fail as BundleError, not a raw TypeError."""
        import json as _json
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        wl_path = Path(bundle_dir) / "workload.json"
        wl_path.write_text('{"p50_slots": 1.0}')
        # Re-checksum so the manifest gate passes and deserialization is reached
        manifest_path = Path(bundle_dir) / "manifest.json"
        manifest = _json.loads(manifest_path.read_text())
        from bq_assess.bundle.models import sha256_file
        manifest["files"]["workload.json"] = sha256_file(wl_path)
        manifest_path.write_text(_json.dumps(manifest))

        with pytest.raises(BundleError, match="workload.json"):
            BundleLoader().load(bundle_dir)

    def test_missing_manifest_refused(self, tmp_path) -> None:
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        (Path(bundle_dir) / "manifest.json").unlink()

        with pytest.raises(BundleError, match="manifest.json not found"):
            BundleLoader().load(bundle_dir)

    def test_nonexistent_path_refused(self) -> None:
        with pytest.raises(BundleError, match="not found"):
            BundleLoader().load("/nonexistent/bundle")

    def test_manifest_carries_disclaimer(self, tmp_path) -> None:
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path))
        manifest = json.loads((Path(bundle_dir) / "manifest.json").read_text())
        assert manifest["disclaimer"] == FULL_DISCLAIMER
        assert manifest["schema_version"] == SCHEMA_VERSION
        assert manifest["bq_location"] == "australia-southeast1"
        assert manifest["aws_region"] == "ap-southeast-2"


# ---------------------------------------------------------------------------
# Zip ingestion
# ---------------------------------------------------------------------------


class TestZipIngestion:
    def test_zip_equals_directory(self, tmp_path) -> None:
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path / "out"))
        zip_path = tmp_path / "bundle.zip"
        _zip_bundle(bundle_dir, zip_path)

        from_dir = BundleLoader().load(bundle_dir)
        from_zip = BundleLoader().load(str(zip_path))

        assert dataclasses.asdict(from_zip.workload) == dataclasses.asdict(from_dir.workload)
        assert from_zip.project_id == from_dir.project_id
        assert from_zip.rates == from_dir.rates
        assert len(from_zip.entities) == len(from_dir.entities)

    def test_zip_with_nested_folder(self, tmp_path) -> None:
        """Customers zip the folder itself: bundle.zip containing bundle/…"""
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path / "out"))
        zip_path = tmp_path / "nested.zip"
        _zip_bundle(bundle_dir, zip_path, prefix="bundle/")

        loaded = BundleLoader().load(str(zip_path))
        assert loaded.project_id == "test-project"

    def test_not_a_zip_refused(self, tmp_path) -> None:
        bogus = tmp_path / "bogus.zip"
        bogus.write_text("this is not a zip")
        with pytest.raises(BundleError, match="Not a valid zip"):
            BundleLoader().load(str(bogus))

    def test_zip_without_manifest_refused(self, tmp_path) -> None:
        src = tmp_path / "empty"
        src.mkdir()
        (src / "readme.txt").write_text("no bundle here")
        zip_path = tmp_path / "nomanifest.zip"
        _zip_bundle(str(src), zip_path)

        with pytest.raises(BundleError, match="No manifest.json found"):
            BundleLoader().load(str(zip_path))

    def test_tampered_zip_refused(self, tmp_path) -> None:
        """Tampering inside the zip is caught by the same checksum gate."""
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path / "out"))
        # Tamper before zipping
        (Path(bundle_dir) / "pricing.json").write_text('{"model": "CAPACITY"}')
        zip_path = tmp_path / "tampered.zip"
        _zip_bundle(bundle_dir, zip_path)

        with pytest.raises(BundleError, match="Checksum mismatch"):
            BundleLoader().load(str(zip_path))


# ---------------------------------------------------------------------------
# Cleanup guard: zip extraction shouldn't leak the temp dir on load failure
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_schema_version_is_one(self) -> None:
        """Bump SCHEMA_VERSION when the bundle shape changes — this test is the
        tripwire reminding you the loader/writer must stay compatible."""
        assert SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Review fixes (2026-07-08 code review of the collector/report split)
# ---------------------------------------------------------------------------


class TestZipDepthAndCleanup:
    def test_zip_two_levels_deep_loads(self, tmp_path) -> None:
        """`zip -r bundle.zip bundle-out/bundle` stores entries two levels deep —
        the documented customer command must load (review fix 4)."""
        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path / "out"))
        zip_path = tmp_path / "deep.zip"
        _zip_bundle(bundle_dir, zip_path, prefix="bundle-out/bundle/")

        loaded = BundleLoader().load(str(zip_path))
        assert loaded.project_id == "test-project"

    def test_zip_temp_dir_cleaned_up(self, tmp_path, monkeypatch) -> None:
        """Zip extraction temp dirs are removed after load — success AND error
        paths (review fix 9)."""
        import tempfile as _tempfile
        created: list[str] = []
        real_mkdtemp = _tempfile.mkdtemp

        def tracking_mkdtemp(*args, **kwargs):
            d = real_mkdtemp(*args, **kwargs)
            created.append(d)
            return d

        monkeypatch.setattr(_tempfile, "mkdtemp", tracking_mkdtemp)

        bundle_dir = BundleWriter().write(_make_bundle([]), str(tmp_path / "out"))
        zip_path = tmp_path / "b.zip"
        _zip_bundle(bundle_dir, zip_path, prefix="bundle/")

        BundleLoader().load(str(zip_path))
        assert created and not Path(created[-1]).exists(), "temp dir leaked on success"

        # Error path: tampered zip must also clean up
        (Path(bundle_dir) / "pricing.json").write_text('{"model": "CAPACITY"}')
        bad_zip = tmp_path / "bad.zip"
        _zip_bundle(bundle_dir, bad_zip, prefix="bundle/")
        with pytest.raises(BundleError):
            BundleLoader().load(str(bad_zip))
        assert not Path(created[-1]).exists(), "temp dir leaked on error path"


class TestQueryLogFormatConsistency:
    """Review fix 6: _queries_from_file must accept every format
    WorkloadAnalyzer.analyze_from_file accepts (JSON array AND JSONL)."""

    _ENTRIES = [
        {"query": "SELECT a FROM ds.t WHERE x = 'secret'", "total_slot_ms": 100,
         "total_bytes_processed": 10, "creation_time": "2026-07-01T10:00:00+00:00"},
        {"query": "SELECT b FROM ds.u LIMIT 5", "total_slot_ms": 50,
         "total_bytes_processed": 5, "creation_time": "2026-07-01T11:00:00+00:00"},
    ]

    def test_jsonl_file_yields_statements(self, tmp_path) -> None:
        from bq_assess.collector import _queries_from_file
        path = tmp_path / "logs.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in self._ENTRIES))

        records = _queries_from_file(str(path))
        assert len(records) == 2
        # Anonymization applied before anything else sees the text
        assert "secret" not in records[0].query

    def test_json_array_file_yields_statements(self, tmp_path) -> None:
        from bq_assess.collector import _queries_from_file
        path = tmp_path / "logs.json"
        path.write_text(json.dumps(self._ENTRIES))

        records = _queries_from_file(str(path))
        assert len(records) == 2


class TestTruncationProof:
    """Review round-2 fix 2: truncation is proven from the RAW row count —
    empty-text rows must not defeat the boundary check."""

    def _rows(self, n, empties=0):
        rows = [
            {"query": f"SELECT {i}", "total_slot_ms": n - i,
             "total_bytes_processed": 1, "total_bytes_billed": 1,
             "missing_billed_jobs": 0, "statement_type": "SELECT",
             "creation_time": None}
            for i in range(n - empties)
        ]
        rows += [{"query": "", "total_slot_ms": 0} for _ in range(empties)]
        return rows

    def test_truncated_flag_from_raw_rows_despite_empty_text(self, monkeypatch) -> None:
        from bq_assess import collector as coll
        from bq_assess.core.jobs_query import QUERIES_EXPORT_LIMIT

        # limit+1 raw rows returned, one with empty text: records == LIMIT exactly,
        # but truncation must STILL be flagged (the old len(records) check missed it).
        monkeypatch.setattr(
            coll, "read_jobs_queries",
            lambda *a, **k: self._rows(QUERIES_EXPORT_LIMIT + 1, empties=1),
        )
        records, truncated = coll._queries_from_api(None, "p", 30, "US")
        assert truncated is True
        assert len(records) == QUERIES_EXPORT_LIMIT

    def test_not_truncated_at_exact_limit(self, monkeypatch) -> None:
        from bq_assess import collector as coll
        from bq_assess.core.jobs_query import QUERIES_EXPORT_LIMIT

        monkeypatch.setattr(
            coll, "read_jobs_queries",
            lambda *a, **k: self._rows(QUERIES_EXPORT_LIMIT),
        )
        records, truncated = coll._queries_from_api(None, "p", 30, "US")
        assert truncated is False
        assert len(records) == QUERIES_EXPORT_LIMIT
