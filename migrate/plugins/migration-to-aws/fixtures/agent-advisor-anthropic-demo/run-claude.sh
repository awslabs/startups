#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$PROJECT_DIR/local-plugin"

cd "$PROJECT_DIR"
exec claude --plugin-dir "$PLUGIN_DIR" "$@"
