// hooks-check.ts — every path a hook command references must exist in the plugin.
//
// WHY: `hooks/hooks.json` runs on the user's machine at session start, and a command that
// names a file the release does not ship fails there rather than here. That is not
// hypothetical: the `SessionStart` hook added in c4e9af8 runs
// `cat ${CLAUDE_PLUGIN_ROOT}/scripts/startup-context.txt`, and the re-sync in c2e2a49
// deleted `scripts/startup-context.txt` while keeping the command. Every session start
// and every `/clear` has printed
//   cat: .../scripts/startup-context.txt: No such file or directory
// since 2.0.0, and because the hook is non-blocking the only visible symptom is that the
// ambient startup-context lens silently stops being injected. Two releases shipped that
// way. Nothing in `mise run build` looks at hooks.json, so this check makes a dangling
// hook path a CI failure instead of a user-visible one.
//
// Checks (all offline, zero-dep, read-only):
//   1. hooks/hooks.json parses
//   2. every ${CLAUDE_PLUGIN_ROOT}-relative path in a hook `command` exists on disk
//
// Usage:
//   node hooks-check.ts                      # advisor plugin (mise task)
//   node hooks-check.ts <root> <plugin-sub>   # another checkout / the other plugin
//
// Zero-dep: runs under Node 24 native TS type-stripping (same as the other tools).

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.argv[2] ?? ".";
const PLUGIN_SUBPATH = process.argv[3] ?? "advisor/plugins/aws-startup-advisor";
const PLUGIN = join(ROOT, PLUGIN_SUBPATH);
const HOOKS_JSON = join(PLUGIN, "hooks", "hooks.json");

const problems: string[] = [];

// A plugin is allowed to ship no hooks at all; only a broken one is a problem.
if (!existsSync(HOOKS_JSON)) {
  console.log(`hooks check: OK (no hooks/hooks.json in ${PLUGIN_SUBPATH})`);
  process.exit(0);
}

let doc: unknown;
try {
  doc = JSON.parse(readFileSync(HOOKS_JSON, "utf8"));
} catch (e) {
  console.error(`hooks check: FAILED (1 problem(s))`);
  console.error(`  - invalid JSON: hooks/hooks.json (${(e as Error).message})`);
  process.exit(1);
}

/** Collect every `command` string anywhere in the hooks document. */
function commands(node: unknown, out: string[] = []): string[] {
  if (Array.isArray(node)) {
    for (const v of node) commands(v, out);
  } else if (node !== null && typeof node === "object") {
    for (const [k, v] of Object.entries(node)) {
      if (k === "command" && typeof v === "string") out.push(v);
      else commands(v, out);
    }
  }
  return out;
}

// `${CLAUDE_PLUGIN_ROOT}/x` and bare `$CLAUDE_PLUGIN_ROOT/x`. Stop at whitespace and at
// the shell metacharacters that would end a path, so `cat ${VAR}/a.txt | head` yields
// `a.txt` and not `a.txt |`.
const REF = /\$(?:\{CLAUDE_PLUGIN_ROOT\}|CLAUDE_PLUGIN_ROOT\b)((?:\/[^\s"'|;&<>()]+)+)/g;

const found: string[] = [];
for (const command of commands(doc)) {
  for (const m of command.matchAll(REF)) {
    const rel = (m[1] ?? "").replace(/^\/+/, "");
    if (!rel) continue;
    found.push(rel);
    if (!existsSync(join(PLUGIN, rel))) {
      problems.push(`hooks/hooks.json references '${rel}', which does not exist in the plugin`);
    }
  }
}

// ---- report -----------------------------------------------------------------
if (problems.length > 0) {
  console.error(`hooks check: FAILED (${problems.length} problem(s))`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`hooks check: OK (${found.length} plugin-root reference(s) in ${PLUGIN_SUBPATH}/hooks/hooks.json)`);
