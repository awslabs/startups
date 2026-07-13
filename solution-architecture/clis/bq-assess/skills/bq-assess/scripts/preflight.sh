#!/usr/bin/env bash
set -euo pipefail

# Preflight environment check for the bq-assess Claude Code skill.
# Emits a JSON object to stdout with tool/auth status.
# No side effects — checks only; does not install or modify anything (Req 4.6).

has() { command -v "$1" >/dev/null 2>&1 && echo true || echo false; }

adc_path="${HOME}/.config/gcloud/application_default_credentials.json"
adc_present=$([ -f "$adc_path" ] && echo true || echo false)

cat <<EOF
{
  "bq_assess_installed": $(has bq-assess),
  "gcloud_installed": $(has gcloud),
  "adc_present": $adc_present,
  "adc_path": "$adc_path"
}
EOF
