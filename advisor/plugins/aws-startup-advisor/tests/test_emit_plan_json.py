"""Tests for scripts/emit-plan-json.py (the plan.json writer).

Mirrors the repo convention (see test_validate_migration_report.py): invoke the
script as a subprocess against a temporary $MIGRATION_DIR, assert the machine
status line and the written file. The writer copies validated values only and
fails open (exit 0, no file) on any missing/unusable input.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "emit-plan-json.py"
FIXTURES = PLUGIN_ROOT / "fixtures"


def _seed(
    migration_dir: Path,
    *,
    owning_skill: str | None = "GCP_TO_AWS",
    run_id: str | None = "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    projected: object = {"aws_monthly_balanced": 112},
    current_costs: object = {"gcp_monthly": 165},
) -> None:
    """Write a minimal .phase-status.json + estimation-infra.json into the dir."""
    status: dict = {"migration_id": "0226-1430", "last_updated": "2026-02-26T14:30:00Z", "phases": {"generate": "completed"}}
    if owning_skill is not None:
        status["owning_skill"] = owning_skill
    if run_id is not None:
        status["run_id"] = run_id
    (migration_dir / ".phase-status.json").write_text(json.dumps(status), encoding="utf-8")

    infra: dict = {}
    if projected is not None:
        infra["projected_costs"] = projected
    if current_costs is not None:
        infra["current_costs"] = current_costs
    (migration_dir / "estimation-infra.json").write_text(json.dumps(infra), encoding="utf-8")


def _run(migration_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--migration-dir", str(migration_dir), *extra],
        capture_output=True,
        text=True,
    )


def test_gcp_happy_path_writes_copyable_fields(tmp_path: Path) -> None:
    _seed(tmp_path)
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_OK |")
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["schemaVersion"] == 1
    assert plan["sourcePlatform"] == "GCP"
    assert plan["scope"] == "INFRA_ONLY"
    assert plan["runId"] == "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    assert plan["cost"]["awsMonthly"] == 112
    assert plan["cost"]["awsMonthlyBasis"] == "BALANCED"
    assert plan["cost"]["sourceMonthly"] == 165
    # producerVersion (the web contract's field name, not "pluginVersion") is copied
    # from the real .claude-plugin/plugin.json.
    assert isinstance(plan["producerVersion"], str) and plan["producerVersion"]
    assert "pluginVersion" not in plan
    # No generated fields leak in.
    assert "awsServiceItems" not in plan["cost"]
    assert "expertConsultations" not in plan


def test_service_items_from_real_heroku_fixture(tmp_path: Path) -> None:
    # Real captured run-state: breakdown keyed by display name + a "total" rollup.
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURES / "heroku-workshop" / "seed", run_dir)
    result = _run(run_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    plan = json.loads((run_dir / "plan.json").read_text())
    items = plan["cost"]["awsServiceItems"]
    by_name = {i["serviceName"]: i for i in items}
    # The "total" rollup row is not a service and must be dropped.
    assert "total" not in by_name
    assert by_name["Elastic Beanstalk"]["monthlyCost"] == 50.0
    assert by_name["RDS PostgreSQL"]["monthlyCost"] == 45.0
    # INFRA_ONLY run => every item is INFRASTRUCTURE (implied by scope, not guessed).
    assert all(i["classification"] == "INFRASTRUCTURE" for i in items)
    assert all("category" not in i for i in items)


def test_service_items_slug_key_uses_nested_service_name(tmp_path: Path) -> None:
    # Reference shape: the key is a slug, the display name is a nested "service" field.
    _seed(
        tmp_path,
        projected={
            "aws_monthly_balanced": 15,
            "breakdown": {
                "security_baseline": {
                    "service": "AWS Security Baseline (Tier 1)",
                    "mid": 15,
                    "components": {"guardduty": 13},
                }
            },
        },
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    items = plan["cost"]["awsServiceItems"]
    assert items == [
        {"serviceName": "AWS Security Baseline (Tier 1)", "monthlyCost": 15, "classification": "INFRASTRUCTURE"}
    ]


def test_service_items_skips_entries_without_a_numeric_mid(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        projected={
            "aws_monthly_balanced": 50,
            "breakdown": {
                "total": {"mid": 50},  # rollup, skipped
                "Good": {"mid": 30},
                "NoMid": {"premium": 40},  # no .mid -> skipped, not emitted with a wrong cost
            },
        },
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    names = [i["serviceName"] for i in plan["cost"]["awsServiceItems"]]
    assert names == ["Good"]


def test_service_items_skips_negative_mid(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        projected={"aws_monthly_balanced": 50, "breakdown": {"Bad": {"mid": -5}, "Good": {"mid": 30}}},
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_omits_service_items_when_breakdown_fully_filtered(tmp_path: Path) -> None:
    # Non-empty breakdown but no usable entry -> omit the field, don't emit [].
    _seed(
        tmp_path,
        projected={"aws_monthly_balanced": 50, "breakdown": {"total": {"mid": 50}, "Bad": {"premium": 10}}},
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "awsServiceItems" not in plan["cost"]


def test_omits_service_items_when_breakdown_empty(tmp_path: Path) -> None:
    # GCP runs can carry an empty breakdown; omit the field rather than emit [].
    _seed(tmp_path, projected={"aws_monthly_balanced": 112, "breakdown": {}})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "awsServiceItems" not in plan["cost"]


def test_heroku_maps_to_heroku_infra(tmp_path: Path) -> None:
    _seed(tmp_path, owning_skill="HEROKU_TO_AWS", current_costs={"heroku_monthly": 90})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["sourcePlatform"] == "HEROKU"
    assert plan["scope"] == "INFRA_ONLY"
    assert plan["cost"]["sourceMonthly"] == 90


def test_omits_source_monthly_when_baseline_unavailable(tmp_path: Path) -> None:
    # Heroku with no billing access: current_costs marks it unavailable, no number.
    _seed(tmp_path, owning_skill="HEROKU_TO_AWS", current_costs={"source": "unavailable"})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "sourceMonthly" not in plan["cost"]
    assert plan["cost"]["awsMonthly"] == 112


def test_fail_open_when_no_estimation_infra(tmp_path: Path) -> None:
    # Only the status file, no cost estimate to hand off.
    (tmp_path / ".phase-status.json").write_text(
        json.dumps({"migration_id": "0226-1430", "last_updated": "x", "phases": {"a": "completed"}, "owning_skill": "GCP_TO_AWS", "run_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301"}),
        encoding="utf-8",
    )
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_when_no_run_id(tmp_path: Path) -> None:
    _seed(tmp_path, run_id=None)
    result = _run(tmp_path)

    assert result.returncode == 0
    assert "PLAN_SKIP |" in result.stdout
    assert "run_id" in result.stdout
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_for_unsupported_skill(tmp_path: Path) -> None:
    # OpenAI/LLM path has no web handoff yet -> skip, do not guess a platform.
    _seed(tmp_path, owning_skill="LLM_TO_BEDROCK")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_for_ai_inclusive_run(tmp_path: Path) -> None:
    # A GCP run that also costed AI (estimation-ai.json present) is FULL/AI_ONLY, not
    # INFRA_ONLY. The infra-only writer must skip it rather than mislabel the scope.
    _seed(tmp_path)  # GCP + estimation-infra.json
    (tmp_path / "estimation-ai.json").write_text(json.dumps({"projected_costs": {}}), encoding="utf-8")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_missing_aws_monthly(tmp_path: Path) -> None:
    _seed(tmp_path, projected={"aws_monthly_premium": 198})  # balanced scenario absent
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / ".phase-status.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "estimation-infra.json").write_text("{}", encoding="utf-8")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_non_object_status(tmp_path: Path) -> None:
    # Valid JSON but not an object: .get() would raise AttributeError — must fail open.
    (tmp_path / ".phase-status.json").write_text("[1, 2, 3]", encoding="utf-8")
    (tmp_path / "estimation-infra.json").write_text(
        json.dumps({"projected_costs": {"aws_monthly_balanced": 10}}), encoding="utf-8"
    )
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_non_object_estimation_infra(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "estimation-infra.json").write_text("[1, 2, 3]", encoding="utf-8")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_non_finite_cost(tmp_path: Path) -> None:
    # json.load accepts Infinity; it must NOT be written as awsMonthly (invalid JSON
    # token the strict web schema rejects).
    _seed(tmp_path)
    (tmp_path / "estimation-infra.json").write_text(
        '{"projected_costs": {"aws_monthly_balanced": Infinity}, "current_costs": {"gcp_monthly": 100}}',
        encoding="utf-8",
    )
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_source_monthly_prefers_the_platform_key(tmp_path: Path) -> None:
    # An unrelated *_monthly field must not be copied ahead of the platform's own key,
    # regardless of JSON key order.
    _seed(tmp_path, current_costs={"support_monthly": 20, "gcp_monthly": 165})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert plan["cost"]["sourceMonthly"] == 165


def test_source_monthly_omitted_when_only_an_unrelated_monthly_key(tmp_path: Path) -> None:
    # Platform key absent: do NOT copy a stray *_monthly (would fabricate a source cost).
    _seed(tmp_path, current_costs={"support_monthly": 20})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "sourceMonthly" not in plan["cost"]


def test_fail_open_on_unhashable_owning_skill(tmp_path: Path) -> None:
    # A list owning_skill is unhashable; the lookup must not crash the run.
    (tmp_path / ".phase-status.json").write_text(
        json.dumps({"migration_id": "x", "last_updated": "x", "phases": {"a": "completed"}, "owning_skill": ["GCP_TO_AWS"], "run_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301"}),
        encoding="utf-8",
    )
    (tmp_path / "estimation-infra.json").write_text(
        json.dumps({"projected_costs": {"aws_monthly_balanced": 10}}), encoding="utf-8"
    )
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_non_utf8_input(tmp_path: Path) -> None:
    # Non-UTF-8 bytes raise UnicodeDecodeError (a ValueError, not OSError/JSONDecodeError).
    (tmp_path / ".phase-status.json").write_bytes(b"\xff\xfe\x00bad")
    (tmp_path / "estimation-infra.json").write_text("{}", encoding="utf-8")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_whitespace_run_id(tmp_path: Path) -> None:
    # A whitespace-only run_id is unattributable; it must not be written as runId.
    _seed(tmp_path, run_id="   ")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_non_object_plugin_json_omits_producer_version(tmp_path: Path) -> None:
    # A valid-JSON but non-object plugin.json raises AttributeError on .get(); the
    # optional version is omitted, the otherwise-valid handoff still emits.
    _seed(tmp_path)
    bad = tmp_path / "plugin.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    result = _run(tmp_path, "--plugin-json", str(bad))

    assert result.stdout.startswith("PLAN_OK |")
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "producerVersion" not in plan


def test_fail_open_on_non_string_run_id(tmp_path: Path) -> None:
    # A numeric run_id would be copied verbatim and rejected by the strict web schema.
    _seed(tmp_path, run_id=None)
    (tmp_path / ".phase-status.json").write_text(
        json.dumps({"migration_id": "x", "last_updated": "x", "phases": {"a": "completed"}, "owning_skill": "GCP_TO_AWS", "run_id": 12345}),
        encoding="utf-8",
    )
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_service_items_skips_blank_service_name(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        projected={"aws_monthly_balanced": 30, "breakdown": {"": {"mid": 30}, "Good": {"mid": 20}}},
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_service_items_skips_rollup_surfaced_via_service_label(tmp_path: Path) -> None:
    # Rollup keyed by a slug but labelled "Total" via the nested service field.
    _seed(
        tmp_path,
        projected={
            "aws_monthly_balanced": 70,
            "breakdown": {"grand": {"service": "Total", "mid": 70}, "Good": {"mid": 20}},
        },
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_service_items_uses_key_when_service_label_is_blank(tmp_path: Path) -> None:
    # A whitespace-only label must fall back to the key, not drop a valid item.
    _seed(
        tmp_path,
        projected={"aws_monthly_balanced": 50, "breakdown": {"Elastic Beanstalk": {"service": "   ", "mid": 50}}},
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Elastic Beanstalk"]


def test_fail_open_on_deeply_nested_json(tmp_path: Path) -> None:
    # Pathologically nested JSON makes json.load raise RecursionError (not a
    # ValueError); the catch-all must still fail open, never crash the run.
    depth = 100000
    (tmp_path / ".phase-status.json").write_text("[" * depth + "]" * depth, encoding="utf-8")
    (tmp_path / "estimation-infra.json").write_text("{}", encoding="utf-8")
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_no_temp_file_left_after_success(tmp_path: Path) -> None:
    # Atomic write renames the temp into place; no *.tmp should survive a success.
    _seed(tmp_path)
    _run(tmp_path)

    assert (tmp_path / "plan.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".plan-*")) == []  # unique mkstemp temp is renamed away


def test_gcp_monthly_shape_and_bare_numbers(tmp_path: Path) -> None:
    # GCP core services carry the figure under `monthly` + a `service` label, with a
    # nested `alternative` that must NOT become its own line item; some breakdowns
    # use bare numbers keyed by category.
    _seed(
        tmp_path,
        projected={
            "aws_monthly_balanced": 265,
            "breakdown": {
                "compute": {"service": "Fargate", "monthly": 71, "alternative": {"service": "Lambda", "monthly": 9}},
                "database": {"service": "Aurora PostgreSQL", "monthly": 269},
                "networking": {"service": "ALB + NAT Gateway", "monthly": 53},
                "misc": 12,
            },
        },
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    by = {i["serviceName"]: i["monthlyCost"] for i in plan["cost"]["awsServiceItems"]}
    assert by == {"Fargate": 71, "Aurora PostgreSQL": 269, "ALB + NAT Gateway": 53, "misc": 12}
    assert "Lambda" not in by  # the nested alternative is not a separate service


def test_omits_service_items_over_the_hundred_item_cap(tmp_path: Path) -> None:
    breakdown = {f"svc{n}": {"mid": 1} for n in range(101)}
    _seed(tmp_path, projected={"aws_monthly_balanced": 101, "breakdown": breakdown})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "awsServiceItems" not in plan["cost"]


def test_service_items_skips_overlong_name_and_over_cap_cost(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        projected={
            "aws_monthly_balanced": 40,
            "breakdown": {
                "x" * 129: {"mid": 10},  # name exceeds 128 -> skipped
                "Huge": {"mid": 100_000_001},  # over the USD cap -> skipped
                "Good": {"mid": 30},
            },
        },
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_service_items_name_bound_uses_utf16_length(tmp_path: Path) -> None:
    # 65 astral-plane chars = 65 code points but 130 UTF-16 units (> 128); the strict
    # web schema counts UTF-16, so this must be dropped even though len() is 65.
    astral = "\U0001F600" * 65
    _seed(
        tmp_path,
        projected={"aws_monthly_balanced": 40, "breakdown": {astral: {"mid": 10}, "Good": {"mid": 30}}},
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_service_items_drops_over_cap_primary_without_substituting(tmp_path: Path) -> None:
    # monthly is the primary figure but over cap; must NOT fall back to mid=5.
    _seed(
        tmp_path,
        projected={
            "aws_monthly_balanced": 40,
            "breakdown": {
                "X": {"service": "X", "monthly": 100_000_001, "mid": 5},
                "Good": {"mid": 30},
            },
        },
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_fail_open_on_aws_monthly_over_usd_cap(tmp_path: Path) -> None:
    _seed(tmp_path, projected={"aws_monthly_balanced": 100_000_001})
    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.startswith("PLAN_SKIP |")
    # Distinct over-cap diagnostic, not the missing/malformed "no usable" reason.
    assert "exceeds" in result.stdout
    assert "no usable" not in result.stdout
    assert not (tmp_path / "plan.json").exists()


def test_sweeps_old_orphan_temp_but_keeps_a_recent_one(tmp_path: Path) -> None:
    old = tmp_path / ".plan-OLD.json.tmp"
    old.write_text("orphan", encoding="utf-8")
    backdated = time.time() - 7200  # 2h old -> abandoned
    os.utime(old, (backdated, backdated))
    recent = tmp_path / ".plan-RECENT.json.tmp"  # simulates a concurrent run's live temp
    recent.write_text("in-flight", encoding="utf-8")

    _seed(tmp_path)
    result = _run(tmp_path)

    assert result.stdout.startswith("PLAN_OK |")
    assert not old.exists()  # reclaimed
    assert recent.exists()  # a live concurrent temp is preserved
    assert (tmp_path / "plan.json").exists()


def test_plan_json_is_written_owner_only(tmp_path: Path) -> None:
    # plan.json holds customer cost data; it is written 0600 (owner-only), not the
    # umask-wide 0644 a plain write would produce.
    _seed(tmp_path)
    _run(tmp_path)

    mode = stat.S_IMODE((tmp_path / "plan.json").stat().st_mode)
    assert mode == 0o600


def test_corrupt_input_preserves_a_prior_valid_plan(tmp_path: Path) -> None:
    # A transient/corrupt input on re-run is unclassifiable — it must NOT destroy a
    # previously-valid handoff (unlike a deterministic SkipEmit, which does clear it).
    prior = tmp_path / "plan.json"
    prior.write_text('{"prior": true}', encoding="utf-8")
    (tmp_path / ".phase-status.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "estimation-infra.json").write_text("{}", encoding="utf-8")
    result = _run(tmp_path)

    assert result.stdout.startswith("PLAN_SKIP |")
    assert prior.read_text() == '{"prior": true}'


def test_sweeps_orphan_temp_even_on_a_skip(tmp_path: Path) -> None:
    # The sweep runs on every invocation, so a fail-open run still reclaims orphans.
    old = tmp_path / ".plan-OLD.json.tmp"
    old.write_text("orphan", encoding="utf-8")
    backdated = time.time() - 7200
    os.utime(old, (backdated, backdated))
    # No artifacts -> SkipEmit early, before the write path.
    result = _run(tmp_path)

    assert result.stdout.startswith("PLAN_SKIP |")
    assert not old.exists()


def test_pre_existing_fixed_temp_path_is_left_untouched(tmp_path: Path) -> None:
    # The writer no longer uses a predictable plan.json.tmp; a stray one at that path
    # must be neither read nor overwritten (guards the old symlink-overwrite hazard).
    stray = tmp_path / "plan.json.tmp"
    stray.write_text("do not touch", encoding="utf-8")
    _seed(tmp_path)
    result = _run(tmp_path)

    assert result.stdout.startswith("PLAN_OK |")
    assert (tmp_path / "plan.json").exists()
    assert stray.read_text() == "do not touch"


def test_bad_plugin_json_omits_producer_version_but_still_emits(tmp_path: Path) -> None:
    # producerVersion is optional: a corrupt plugin.json must omit it, not sink the run.
    _seed(tmp_path)
    bad = tmp_path / "plugin.json"
    bad.write_text("{not json", encoding="utf-8")
    result = _run(tmp_path, "--plugin-json", str(bad))

    assert result.stdout.startswith("PLAN_OK |")
    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "producerVersion" not in plan
    assert plan["cost"]["awsMonthly"] == 112


def test_skip_removes_a_stale_plan_json(tmp_path: Path) -> None:
    # A prior run wrote plan.json; the run then grows to include AI -> this run skips.
    # The stale INFRA_ONLY file must be removed so the import can't ingest it.
    (tmp_path / "plan.json").write_text('{"stale": true}', encoding="utf-8")
    _seed(tmp_path)
    (tmp_path / "estimation-ai.json").write_text(json.dumps({"projected_costs": {}}), encoding="utf-8")
    result = _run(tmp_path)

    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_fail_open_on_boolean_cost(tmp_path: Path) -> None:
    # JSON true is a Python bool (int subclass); it must NOT pass the numeric guard and
    # get written as awsMonthly:true, which the strict web schema would reject.
    _seed(tmp_path, projected={"aws_monthly_balanced": True})
    result = _run(tmp_path)

    assert result.stdout.startswith("PLAN_SKIP |")
    assert not (tmp_path / "plan.json").exists()


def test_service_items_skips_total_case_insensitively(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        projected={"aws_monthly_balanced": 50, "breakdown": {"Total": {"mid": 50}, "Good": {"mid": 30}}},
    )
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert [i["serviceName"] for i in plan["cost"]["awsServiceItems"]] == ["Good"]


def test_omits_negative_source_monthly(tmp_path: Path) -> None:
    _seed(tmp_path, current_costs={"gcp_monthly": -5})
    result = _run(tmp_path)

    plan = json.loads((tmp_path / "plan.json").read_text())
    assert "sourceMonthly" not in plan["cost"]
