"""Check the primary recommendation produced by the demo scenarios."""

import argparse
import json
import pathlib


EXPECTED = {
    # Sonnet 5 (2026-06-30) supports Mantle Messages, so balanced+Messages no
    # longer escalates to Opus.
    "default": {
        "decision_status": "recommended",
        "api_path": "mantle_messages",
        "primary_model": "anthropic.claude-sonnet-5",
        "invocation_model_id": "anthropic.claude-sonnet-5",
        "probe_status": "not_run",
    },
    "conflict": {
        "decision_status": "decision_required",
        "api_path": None,
        "primary_model": None,
        "invocation_model_id": None,
        "probe_status": "not_applicable",
    },
    "runtime": {
        "decision_status": "recommended",
        "api_path": "runtime_converse",
        "primary_model": "anthropic.claude-sonnet-5",
        "invocation_model_id": "global.anthropic.claude-sonnet-5",
        "probe_status": "not_run",
    },
}


def check(path, scenario):
    artifact = json.loads(path.read_text())
    workload_id = artifact["primary_unit"]
    recommendation = artifact["workloads"][workload_id]
    actual = {
        "decision_status": recommendation["decision_status"],
        "api_path": recommendation["api_path"],
        "primary_model": recommendation["primary_model"],
        "invocation_model_id": recommendation["invocation_model_id"],
        "probe_status": recommendation["verification"]["probe_status"],
    }
    expected = EXPECTED[scenario]
    mismatches = {
        key: {"expected": expected[key], "actual": actual[key]}
        for key in expected
        if actual[key] != expected[key]
    }
    if scenario == "conflict":
        paths = {
            option["api_path"] for option in recommendation["decision_options"]
        }
        if paths != {"mantle_messages", "runtime_converse"}:
            mismatches["decision_options"] = {
                "expected": ["mantle_messages", "runtime_converse"],
                "actual": sorted(paths),
            }
    if mismatches:
        print(json.dumps(mismatches, indent=2))
        return 1
    print(f"PASS scenario={scenario} workload={workload_id}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=pathlib.Path)
    parser.add_argument("scenario", choices=sorted(EXPECTED))
    args = parser.parse_args()
    return check(args.artifact, args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())
