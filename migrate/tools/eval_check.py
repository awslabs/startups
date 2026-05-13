#!/usr/bin/env python3
"""Evaluation harness checker script.

Reads invariant definitions from tests/invariants.yml and validates migration
output against them. Produces structured JSON results suitable for consumption
by the eval skill or direct inspection.

Usage:
    python tools/eval_check.py --migration-dir PATH --fixture NAME [--json]

Exit codes:
    0 - All hard invariants pass
    1 - One or more hard invariants fail
    2 - Configuration or runtime error
"""

import argparse
import glob as globmod
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml


def load_invariants(fixture_name: str) -> dict:
    """Load invariant definitions for the given fixture.

    Looks for fixture-specific invariants first at:
        tests/fixtures/<fixture_name>/invariants.yml
    Falls back to the shared invariants at:
        tests/invariants.yml
    """
    repo_root = Path(__file__).resolve().parent.parent

    # Try fixture-specific invariants first
    fixture_invariants = repo_root / "tests" / "fixtures" / fixture_name / "invariants.yml"
    if fixture_invariants.exists():
        with open(fixture_invariants, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data

    # Fall back to shared invariants
    invariants_path = repo_root / "tests" / "invariants.yml"
    if not invariants_path.exists():
        print(f"Error: No invariants found for fixture '{fixture_name}'", file=sys.stderr)
        sys.exit(2)

    with open(invariants_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data.get("fixture") != fixture_name:
        print(
            f"Warning: invariants.yml fixture '{data.get('fixture')}' "
            f"does not match requested fixture '{fixture_name}'",
            file=sys.stderr,
        )

    return data


def check_file_exists(migration_dir: Path, check: dict) -> dict:
    """Assert a file exists in the migration directory."""
    target = migration_dir / check["file"]
    if target.exists():
        return {"status": "pass"}
    return {"status": "fail", "details": f"File not found: {check['file']}"}


def check_file_absent(migration_dir: Path, check: dict) -> dict:
    """Assert file(s) do NOT exist in the migration directory."""
    files = check.get("files", [check["file"]] if "file" in check else [])
    found = []
    for f in files:
        if (migration_dir / f).exists():
            found.append(f)
    if found:
        return {"status": "fail", "details": f"Forbidden file(s) found: {', '.join(found)}"}
    return {"status": "pass"}


def check_content_absent(migration_dir: Path, check: dict) -> dict:
    """Assert patterns are NOT present in a file."""
    if "file_glob" in check:
        files = list(migration_dir.glob(check["file_glob"]))
    else:
        target = migration_dir / check["file"]
        files = [target] if target.exists() else []

    if not files:
        # If no files match, can't have content — pass
        return {"status": "pass"}

    violations = []
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in check["patterns"]:
            if pattern in content:
                violations.append(f"Found '{pattern}' in {file_path.name}")

    if violations:
        return {"status": "fail", "details": "; ".join(violations[:5])}
    return {"status": "pass"}


def check_content_present(migration_dir: Path, check: dict) -> dict:
    """Assert patterns ARE present in file(s)."""
    if "file_glob" in check:
        files = list(migration_dir.glob(check["file_glob"]))
    else:
        target = migration_dir / check["file"]
        files = [target] if target.exists() else []

    if not files:
        return {"status": "fail", "details": "No matching files found"}

    missing = []
    for pattern in check["patterns"]:
        found_in_any = any(
            pattern in f.read_text(encoding="utf-8")
            for f in files
            if f.exists()
        )
        if not found_in_any:
            missing.append(pattern)

    if missing:
        return {"status": "fail", "details": f"Patterns not found: {', '.join(missing)}"}
    return {"status": "pass"}


def check_json_path_value(migration_dir: Path, check: dict) -> dict:
    """Assert a JSON field has a specific value or is not null."""
    target = migration_dir / check["file"]
    if not target.exists():
        return {"status": "fail", "details": f"File not found: {check['file']}"}

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "fail", "details": f"Cannot parse {check['file']}: {e}"}

    # Simple dot-path navigation ($.foo.bar.baz)
    path = check["path"].lstrip("$.")
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return {"status": "fail", "details": f"Path '{check['path']}' not found"}

    if "not_null" in check and check["not_null"]:
        if current is None:
            return {"status": "fail", "details": f"Value at '{check['path']}' is null"}
        return {"status": "pass"}

    if "one_of" in check:
        if current not in check["one_of"]:
            return {
                "status": "fail",
                "details": f"Value '{current}' not in {check['one_of']}",
            }
        return {"status": "pass"}

    if "equals" in check:
        if current != check["equals"]:
            return {
                "status": "fail",
                "details": f"Expected '{check['equals']}', got '{current}'",
            }

    return {"status": "pass"}


def check_json_every(migration_dir: Path, check: dict) -> dict:
    """Assert every item in a JSON array has required fields."""
    target = migration_dir / check["file"]
    if not target.exists():
        return {"status": "fail", "details": f"File not found: {check['file']}"}

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "fail", "details": f"Cannot parse {check['file']}: {e}"}

    # Navigate to array (simple path: $.resources or $.mappings)
    path = check["path"].lstrip("$.")
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return {"status": "fail", "details": f"Path '{check['path']}' not found"}

    if not isinstance(current, list):
        return {"status": "fail", "details": f"Value at '{check['path']}' is not an array"}

    missing_fields = []
    for i, item in enumerate(current):
        if not isinstance(item, dict):
            continue
        for field in check["has_fields"]:
            if field not in item:
                missing_fields.append(f"Item {i} missing '{field}'")

    if missing_fields:
        return {"status": "fail", "details": "; ".join(missing_fields[:5])}
    return {"status": "pass"}


def check_uniqueness(migration_dir: Path, check: dict) -> dict:
    """Assert all values at a path are unique."""
    target = migration_dir / check["file"]
    if not target.exists():
        return {"status": "fail", "details": f"File not found: {check['file']}"}

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "fail", "details": f"Cannot parse {check['file']}: {e}"}

    # Simple extraction: $.resources[*].address -> data["resources"][i]["address"]
    path = check["path"]
    # Parse pattern: $.array[*].field
    import re
    match = re.match(r"\$\.(\w+)\[\*\]\.(\w+)", path)
    if not match:
        return {"status": "fail", "details": f"Unsupported path pattern: {path}"}

    array_key, field_key = match.groups()
    if array_key not in data or not isinstance(data[array_key], list):
        return {"status": "fail", "details": f"'{array_key}' not found or not an array"}

    values = [item.get(field_key) for item in data[array_key] if isinstance(item, dict)]
    seen = set()
    duplicates = []
    for v in values:
        if v in seen:
            duplicates.append(str(v))
        seen.add(v)

    if duplicates:
        return {"status": "fail", "details": f"Duplicate values: {', '.join(duplicates[:5])}"}
    return {"status": "pass"}


def check_cross_file_join(migration_dir: Path, check: dict) -> dict:
    """Assert all values in source path exist in target path."""
    import re

    source_file = migration_dir / check["source_file"]
    target_file = migration_dir / check["target_file"]

    if not source_file.exists():
        return {"status": "fail", "details": f"Source file not found: {check['source_file']}"}
    if not target_file.exists():
        return {"status": "fail", "details": f"Target file not found: {check['target_file']}"}

    try:
        source_data = json.loads(source_file.read_text(encoding="utf-8"))
        target_data = json.loads(target_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "fail", "details": f"JSON parse error: {e}"}

    def extract_values(data, path):
        match = re.match(r"\$\.(\w+)\[\*\]\.(\w+)", path)
        if not match:
            match = re.match(r"\$\[\*\]\.(\w+)", path)
            if match:
                field = match.group(1)
                if isinstance(data, list):
                    return [item.get(field) for item in data if isinstance(item, dict)]
            return []
        array_key, field_key = match.groups()
        if array_key in data and isinstance(data[array_key], list):
            return [item.get(field_key) for item in data[array_key] if isinstance(item, dict)]
        return []

    source_values = extract_values(source_data, check["source_path"])
    target_values = set(extract_values(target_data, check["target_path"]))

    orphans = [str(v) for v in source_values if v not in target_values]
    if orphans:
        return {"status": "fail", "details": f"Orphaned values: {', '.join(orphans[:5])}"}
    return {"status": "pass"}


def check_custom(migration_dir: Path, check: dict, repo_root: Path) -> dict:
    """Delegate to a custom Python handler script.

    Runs the handler in-process by importing it with runpy and capturing stdout.
    Each handler expects sys.argv[1] to be the migration directory and prints
    JSON to stdout: {"status": "pass"} or {"status": "fail", "details": "..."}.
    """
    handler_path = repo_root / check["handler"]
    if not handler_path.exists():
        return {"status": "skip", "details": f"Handler not found: {check['handler']}"}

    try:
        import runpy

        captured = io.StringIO()
        fake_argv = [str(handler_path), str(migration_dir)]
        with patch.object(sys, "argv", fake_argv), redirect_stdout(captured):
            runpy.run_path(str(handler_path), run_name="__main__")
        output = json.loads(captured.getvalue())
        return output
    except (json.JSONDecodeError, Exception) as e:
        return {"status": "fail", "details": f"Handler error: {e}"}


# Dispatcher mapping check types to functions
CHECK_DISPATCH = {
    "file_exists": check_file_exists,
    "file_absent": check_file_absent,
    "content_absent": check_content_absent,
    "content_present": check_content_present,
    "json_path_value": check_json_path_value,
    "json_every": check_json_every,
    "uniqueness": check_uniqueness,
    "cross_file_join": check_cross_file_join,
}


def run_check(invariant: dict, migration_dir: Path, repo_root: Path) -> dict:
    """Run a single invariant check and return the result."""
    check = invariant["check"]
    check_type = check["type"]

    if check_type == "custom":
        result = check_custom(migration_dir, check, repo_root)
    elif check_type in CHECK_DISPATCH:
        result = CHECK_DISPATCH[check_type](migration_dir, check)
    else:
        result = {"status": "skip", "details": f"Unknown check type: {check_type}"}

    return {
        "id": invariant["id"],
        "description": invariant["description"],
        "source": invariant["source"],
        **result,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluation harness checker")
    parser.add_argument(
        "--migration-dir",
        type=Path,
        required=True,
        help="Path to the migration output directory",
    )
    parser.add_argument(
        "--fixture",
        type=str,
        default="minimal-cloud-run-sql",
        help="Fixture name (default: minimal-cloud-run-sql)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (default)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    migration_dir = args.migration_dir.resolve()

    if not migration_dir.exists():
        print(f"Error: Migration directory not found: {migration_dir}", file=sys.stderr)
        sys.exit(2)

    # Load invariants
    data = load_invariants(args.fixture)

    hard_results = []
    soft_results = []

    # Run hard invariants
    for inv in data.get("hard_invariants", []):
        result = run_check(inv, migration_dir, repo_root)
        hard_results.append(result)

    # Run soft observations
    for obs in data.get("soft_observations", []):
        result = run_check(obs, migration_dir, repo_root)
        result["expected"] = obs.get("expected")
        soft_results.append(result)

    # Compute summary
    hard_failures = [r for r in hard_results if r["status"] == "fail"]
    hard_passes = [r for r in hard_results if r["status"] == "pass"]
    hard_skips = [r for r in hard_results if r["status"] == "skip"]

    output = {
        "fixture": args.fixture,
        "migration_dir": str(migration_dir),
        "hard_invariants": hard_results,
        "soft_observations": soft_results,
        "summary": {
            "hard_total": len(hard_results),
            "hard_passed": len(hard_passes),
            "hard_failed": len(hard_failures),
            "hard_skipped": len(hard_skips),
            "status": "fail" if hard_failures else "pass",
        },
    }

    print(json.dumps(output, indent=2))
    sys.exit(1 if hard_failures else 0)


if __name__ == "__main__":
    main()
