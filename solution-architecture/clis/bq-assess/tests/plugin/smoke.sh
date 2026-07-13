#!/usr/bin/env bash
set -euo pipefail

# Smoke test: runs bq-assess against the reference dataset with skill-default
# parameters and verifies the JSON report exists and parses.
#
# Requires GCP credentials with read access to the target project. Set
# BQ_SMOKE_PROJECT and BQ_SMOKE_DATASET to a project/dataset you can read.
# Validates: Requirement 11.3

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bq-assess-smoke.XXXXXX")"

cleanup() { rm -rf "$OUTPUT_DIR"; }
trap cleanup EXIT

echo "=== bq-assess smoke test ==="
echo "Output dir: $OUTPUT_DIR"

# Run with skill-default parameters (mirrors scan.md defaults)
bq-assess \
  --gcp-project "${BQ_SMOKE_PROJECT:?Set BQ_SMOKE_PROJECT to a GCP project you can read}" \
  --use-adc \
  --datasets "${BQ_SMOKE_DATASET:?Set BQ_SMOKE_DATASET to a dataset in that project}" \
  --format json,html \
  --output "$OUTPUT_DIR"

# Verify JSON report exists
JSON_REPORT=$(find "$OUTPUT_DIR" -name "assessment-*.json" -type f | head -1)

if [ -z "$JSON_REPORT" ]; then
  echo "FAIL: No JSON report found in $OUTPUT_DIR"
  exit 1
fi

# Verify JSON is parseable
if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$JSON_REPORT"; then
  echo "FAIL: JSON report is not valid JSON: $JSON_REPORT"
  exit 1
fi

echo "PASS: Smoke test completed. Report: $JSON_REPORT"
