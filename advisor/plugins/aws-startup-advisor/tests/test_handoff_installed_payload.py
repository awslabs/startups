"""Guard: each handoff exit's writer command works from a skill-only install.

`npx skills add --skill <skill>` installs ONLY that skill's directory tree — no
plugin-level `scripts/` and no `.claude-plugin/plugin.json`. The substring guards
in test_decision_gate_wiring.py and the source-checkout writer tests cannot catch
a command that resolves the writer from the plugin root, because the source
checkout always has one. So this test copies each skill payload on its own,
extracts the exact writer command from each exit's markdown, and executes it from
an unrelated cwd with no plugin root, asserting it still emits an uploadable plan.
"""
from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_WRITER = PLUGIN_ROOT / "scripts" / "emit-plan-json.py"

# (skill, owning_skill, exit doc relative to the skill root)
HANDOFF_EXITS = [
    ("gcp-to-aws", "GCP_TO_AWS", "references/phases/estimate/estimate.md"),
    ("gcp-to-aws", "GCP_TO_AWS", "references/phases/generate/generate.md"),
    ("heroku-to-aws", "HEROKU_TO_AWS", "references/phases/estimate/estimate-assemble.md"),
    ("heroku-to-aws", "HEROKU_TO_AWS", "references/phases/generate/generate-assemble.md"),
]

# The inline-code writer command in an exit's markdown.
_COMMAND_RE = re.compile(r"`(python3 [^`]*emit-plan-json\.py[^`]*)`")


def _seed(migration_dir: Path, owning_skill: str) -> None:
    status = {
        "migration_id": "0226-1430",
        "run_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
        "owning_skill": owning_skill,
        "phases": {"generate": "completed"},
    }
    (migration_dir / ".phase-status.json").write_text(json.dumps(status), encoding="utf-8")
    infra: dict = {"projected_costs": {"aws_monthly_balanced": 112}}
    if owning_skill == "HEROKU_TO_AWS":
        infra["current_costs"] = {"source": "billing_data"}
        infra["cost_comparison"] = {"heroku_monthly_baseline": 90}
    else:
        infra["current_costs"] = {"gcp_monthly": 165}
    (migration_dir / "estimation-infra.json").write_text(json.dumps(infra), encoding="utf-8")


@pytest.mark.parametrize(("skill", "owning_skill", "exit_doc"), HANDOFF_EXITS)
def test_exit_command_emits_plan_from_skill_only_install(
    tmp_path: Path, skill: str, owning_skill: str, exit_doc: str
) -> None:
    doc = PLUGIN_ROOT / "skills" / skill / exit_doc
    commands = _COMMAND_RE.findall(doc.read_text(encoding="utf-8"))
    assert commands, f"{skill}/{exit_doc}: no emit-plan-json.py command found"

    # Skill-only install: this skill's tree alone, nothing from the plugin root.
    installed = tmp_path / "installed" / skill
    shutil.copytree(PLUGIN_ROOT / "skills" / skill, installed)
    migration_dir = tmp_path / "run"
    migration_dir.mkdir()
    _seed(migration_dir, owning_skill)
    unrelated_cwd = tmp_path / "elsewhere"
    unrelated_cwd.mkdir()

    for command in commands:
        command = command.replace("<SKILL_BASE>", str(installed))
        command = command.replace("python3 ", f'"{sys.executable}" ', 1)
        env = {
            **os.environ,
            "MIGRATION_DIR": str(migration_dir),
            # No plugin root in a skill-only install: point it at nothing.
            "PLUGIN_ROOT": str(tmp_path / "no-plugin-root"),
        }
        result = subprocess.run(
            ["bash", "-c", command], cwd=unrelated_cwd, env=env, capture_output=True, text=True
        )

        assert result.returncode == 0, f"{skill}/{exit_doc}: {result.stderr.strip()}"
        assert result.stdout.startswith("PLAN_OK |"), f"{skill}/{exit_doc}: {result.stdout.strip()}"
        assert (migration_dir / "plan.json").is_file()


def test_skill_local_writers_match_the_plugin_writer() -> None:
    # The skill-local copies exist only so skill-only installs can reach the writer;
    # they must never drift from the plugin-level source of truth.
    copies = sorted((PLUGIN_ROOT / "skills").glob("*/scripts/emit-plan-json.py"))
    assert {p.parent.parent.name for p in copies} >= {"gcp-to-aws", "heroku-to-aws"}
    for copy in copies:
        assert filecmp.cmp(copy, PLUGIN_WRITER, shallow=False), (
            f"{copy.relative_to(PLUGIN_ROOT)} drifted from scripts/emit-plan-json.py"
        )
