"""Tests for startup program artifact validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "validate-startup-program-artifacts.py"


def run_validator(migration_dir: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--migration-dir", str(migration_dir)],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def test_unknown_status_passes_neutral_copy(tmp_path: Path) -> None:
    prefs = json.loads(
        (PLUGIN_ROOT / "fixtures" / "preferences-unknown-startup.json").read_text()
    )
    (tmp_path / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")
    (tmp_path / "STARTUP_PROGRAMS.md").write_text(
        "# AWS Startup Programs\n\n**Startup status:** not confirmed in Clarify.\n",
        encoding="utf-8",
    )
    code, out = run_validator(tmp_path)
    assert code == 0, out
    assert "STARTUP_OK" in out


def test_unknown_status_fails_eligible_founders_bleed(tmp_path: Path) -> None:
    prefs = json.loads(
        (PLUGIN_ROOT / "fixtures" / "preferences-unknown-startup.json").read_text()
    )
    (tmp_path / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")
    (tmp_path / "STARTUP_PROGRAMS.md").write_text(
        "**your status: eligible_founders**\n",
        encoding="utf-8",
    )
    code, out = run_validator(tmp_path)
    assert code == 1, out
    assert "STARTUP_FAIL" in out


def test_eligible_founders_status_not_checked(tmp_path: Path) -> None:
    prefs = json.loads(
        (PLUGIN_ROOT / "fixtures" / "preferences-unknown-startup.json").read_text()
    )
    prefs["design_constraints"]["startup_program_status"] = {
        "value": "eligible_founders",
        "chosen_by": "user",
    }
    (tmp_path / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")
    (tmp_path / "STARTUP_PROGRAMS.md").write_text(
        "**your status: eligible_founders**\n",
        encoding="utf-8",
    )
    code, out = run_validator(tmp_path)
    assert code == 0, out
