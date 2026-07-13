#!/usr/bin/env bash
set -euo pipefail
# Structural validation for the bq-assess Claude Code skill plugin.
# Runs offline — no GCP credentials or Claude Code required.
#
# Validates: Requirement 10.5, Requirement 10.4, Property 11
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_HOME="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLUGIN_ROOT="$PLUGIN_HOME/skills/bq-assess"
ERRORS=0
fail() { echo "FAIL: $1"; ERRORS=$((ERRORS + 1)); }
pass() { echo "PASS: $1"; }
echo "=== bq-assess plugin structural checks ==="
echo ""
# ---------- 1. plugin.json is valid JSON ----------
MANIFEST="$PLUGIN_HOME/.claude-plugin/plugin.json"
if [ ! -f "$MANIFEST" ]; then
  fail "plugin.json not found at $MANIFEST"
else
  if python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$MANIFEST" 2>/dev/null; then
    pass "plugin.json is valid JSON"
  else
    fail "plugin.json is not valid JSON"
  fi
fi
# ---------- 2. SKILL.md YAML frontmatter ----------
SKILL_MD="$PLUGIN_ROOT/SKILL.md"
if [ ! -f "$SKILL_MD" ]; then
  fail "SKILL.md not found at $SKILL_MD"
else
  python3 - "$SKILL_MD" <<'PYEOF' || ERRORS=$((ERRORS + 1))
import yaml, sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()
if not content.startswith("---"):
    print(f"FAIL: SKILL.md does not start with YAML frontmatter")
    sys.exit(1)
parts = content.split("---", 2)
if len(parts) < 3:
    print(f"FAIL: SKILL.md frontmatter not properly delimited")
    sys.exit(1)
fm = yaml.safe_load(parts[1])
if not isinstance(fm, dict):
    print(f"FAIL: SKILL.md frontmatter is not a YAML mapping")
    sys.exit(1)
missing = [f for f in ("name", "description") if not fm.get(f)]
if missing:
    print(f"FAIL: SKILL.md frontmatter missing required fields: {', '.join(missing)}")
    sys.exit(1)
print(f"PASS: SKILL.md frontmatter valid (name={fm['name']})")
PYEOF
fi
# ---------- 3. Phase files referenced in state machine exist ----------
for phase in preflight scan interpret; do
  PHASE_FILE="$PLUGIN_ROOT/references/phases/${phase}.md"
  if [ -f "$PHASE_FILE" ]; then
    pass "Phase file exists: references/phases/${phase}.md"
  else
    fail "Phase file missing: references/phases/${phase}.md"
  fi
done
# ---------- 4. Forbidden-string check (Property 11) ----------
#
# No file in the plugin tree may reference an internal hostname. There are
# no exceptions: the public plugin installs from github.com/awslabs/startups.
echo ""
echo "Checking for forbidden strings..."
FORBIDDEN_FOUND=0
for pattern in "ssh.gitlab.aws.dev" "w.amazon.com"; do
  HITS=$(grep -r --include="*.md" --include="*.sh" --include="*.yaml" --include="*.yml" --include="*.json" \
    -l "$pattern" "$PLUGIN_ROOT" "$PLUGIN_HOME/README.md" "$PLUGIN_HOME/docs" 2>/dev/null \
    || true)
  if [ -n "$HITS" ]; then
    for hit in $HITS; do
      rel="${hit#$PLUGIN_HOME/}"
      fail "Forbidden string '$pattern' found in $rel"
      FORBIDDEN_FOUND=1
    done
  fi
done
if [ "$FORBIDDEN_FOUND" -eq 0 ]; then
  pass "No forbidden strings in plugin files"
fi
# ---------- Summary ----------
echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "FAILED: $ERRORS check(s) failed"
  exit 1
else
  echo "ALL CHECKS PASSED"
  exit 0
fi
