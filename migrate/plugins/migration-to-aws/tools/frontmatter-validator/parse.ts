// parse.ts — read a markdown file's `---` frontmatter block and bind it into the
// typed shapes in types.ts. Zero-dep: a small reader for the YAML subset we author
// (flat scalars, a `_fragments` list of `{_id, _trigger, _file}`, and `_assemble`
// / `_produces` / `_reads` / `_contributes` lists). Not a general YAML parser.

import type {
  AssemblerFrontmatter,
  FragmentFrontmatter,
  FragmentRef,
  PhaseFrontmatter,
  ReEntryGuard,
  Trigger,
} from "./types.ts";
import { readFileSync } from "node:fs";

const PHASE_KEYS = new Set([
  "_phase", "_title", "_kind", "_requires_phase", "_init", "_input",
  "_fragments", "_trigger", "_assemble", "_produces", "_advances_to",
  "_re_entry_guard",
]);
const GUARD_KEYS = new Set([
  "_stale_if_completed", "_stale_artifact", "_on_reentry", "_on_confirm",
]);
const FRAGMENT_KEYS = new Set(["_fragment", "_of_phase", "_contributes"]);
const ASSEMBLER_KEYS = new Set(["_assemble", "_of_phase", "_reads", "_produces"]);

/** Return the frontmatter block text (between the leading `---` fences), or null. */
export function extractFrontmatter(path: string): string | null {
  const text = readFileSync(path, "utf8");
  if (!text.startsWith("---\n")) return null;
  const end = text.indexOf("\n---", 4);
  if (end === -1) return null;
  return text.slice(4, end + 1);
}

/** Top-level `_`-keys appearing at column 0. */
function topLevelKeys(fm: string): string[] {
  const keys: string[] = [];
  for (const line of fm.split("\n")) {
    const m = /^(_[a-z_]+):/.exec(line);
    if (m) keys.push(m[1]);
  }
  return keys;
}

function unknownAmong(fm: string, allowed: Set<string>): string[] {
  return topLevelKeys(fm).filter((k) => !allowed.has(k));
}

function scalar(fm: string, key: string): string | null {
  const m = new RegExp(`^${key}:\\s*(.+)$`, "m").exec(fm);
  if (!m) return null;
  return m[1].trim().replace(/^["']|["']$/g, "");
}

/** A block-list: `key:\n  - a\n  - b`. */
function blockList(fm: string, key: string): string[] {
  const re = new RegExp(`^${key}:\\s*\\n((?:\\s*-\\s*.+\\n?)+)`, "m");
  const m = re.exec(fm);
  if (!m) return [];
  return m[1]
    .split("\n")
    .map((l) => l.replace(/^\s*-\s*/, "").trim())
    .filter(Boolean);
}

function parseTrigger(raw: string): Trigger {
  const t = raw.trim();
  if (/_always\s*:\s*true/.test(t)) return { kind: "always" };
  const g = /_glob\s*:\s*["']?([^"'}]+)["']?/.exec(t);
  if (g) return { kind: "glob", pattern: g[1].trim() };
  const w = /_when\s*:\s*["']?([^"'}]+)["']?/.exec(t);
  if (w) return { kind: "when", condition: w[1].trim() };
  return { kind: "unknown", raw: t };
}

function parseFragments(fm: string): FragmentRef[] {
  const out: FragmentRef[] = [];
  // each entry: - _id: X ... _trigger: { ... } ... _file: Y
  const re = /-\s*_id:\s*([\w-]+)[\s\S]*?_trigger:\s*\{([^}]*)\}[\s\S]*?_file:\s*([^\n]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(fm))) {
    out.push({ id: m[1], trigger: parseTrigger(m[2]), file: m[3].trim() });
  }
  return out;
}

/** Extract the indented body lines of a `key:` block (lines more-indented than the key). */
function indentedBlock(fm: string, key: string): string | null {
  const lines = fm.split("\n");
  const idx = lines.findIndex((l) => new RegExp(`^${key}:\\s*$`).test(l));
  if (idx === -1) return null;
  const body: string[] = [];
  for (let i = idx + 1; i < lines.length; i++) {
    const l = lines[i];
    if (l.trim() === "") continue;
    if (/^\s/.test(l)) body.push(l);
    else break; // dedent to column 0 ends the block
  }
  return body.join("\n");
}

/** Parse the nested `_re_entry_guard:` block, or null when the key is absent. */
function parseReEntryGuard(fm: string): ReEntryGuard | null {
  const body = indentedBlock(fm, "_re_entry_guard");
  if (body === null) return null;
  const sub = (k: string): string | null => {
    const m = new RegExp(`^\\s*${k}:\\s*(.+)$`, "m").exec(body);
    return m ? m[1].trim().replace(/^["']|["']$/g, "") : null;
  };
  const guardKeys: string[] = [];
  for (const line of body.split("\n")) {
    const m = /^\s*(_[a-z_]+):/.exec(line);
    if (m) guardKeys.push(m[1]);
  }
  return {
    staleIfCompleted: sub("_stale_if_completed"),
    staleArtifact: sub("_stale_artifact"),
    onReentry: sub("_on_reentry"),
    onConfirm: sub("_on_confirm"),
    unknownKeys: guardKeys.filter((k) => !GUARD_KEYS.has(k)),
  };
}

export function parsePhase(path: string, fm: string): PhaseFrontmatter {
  const assembleBlock = /_assemble:\s*\n\s*_file:\s*([^\n]+)/.exec(fm);
  const roleRaw = scalar(fm, "_kind");
  const role = roleRaw === "checkpoint" ? "checkpoint" : "backbone";
  // phase-level _trigger: a `_trigger: { ... }` at column 0 (NOT a _fragments[] entry,
  // which is indented under a `- _id:`). Match only a top-of-line _trigger.
  const ptrig = /^_trigger:\s*\{([^}]*)\}/m.exec(fm);
  return {
    kind: "phase",
    sourceFile: path,
    phase: scalar(fm, "_phase") ?? "",
    title: scalar(fm, "_title"),
    role,
    requiresPhase: scalar(fm, "_requires_phase"),
    init: /^_init:\s*true\s*$/m.test(fm),
    fragments: parseFragments(fm),
    trigger: ptrig ? parseTrigger(ptrig[1]) : null,
    assembleFile: assembleBlock ? assembleBlock[1].trim() : null,
    produces: blockList(fm, "_produces"),
    advancesTo: scalar(fm, "_advances_to"),
    reEntryGuard: parseReEntryGuard(fm),
    unknownKeys: unknownAmong(fm, PHASE_KEYS),
  };
}

export function parseFragment(path: string, fm: string): FragmentFrontmatter {
  return {
    kind: "fragment",
    sourceFile: path,
    fragment: scalar(fm, "_fragment") ?? "",
    ofPhase: scalar(fm, "_of_phase"),
    contributes: blockList(fm, "_contributes"),
    unknownKeys: unknownAmong(fm, FRAGMENT_KEYS),
  };
}

export function parseAssembler(path: string, fm: string): AssemblerFrontmatter {
  return {
    kind: "assembler",
    sourceFile: path,
    assemble: scalar(fm, "_assemble"),
    ofPhase: scalar(fm, "_of_phase"),
    reads: blockList(fm, "_reads"),
    produces: blockList(fm, "_produces"),
    unknownKeys: unknownAmong(fm, ASSEMBLER_KEYS),
  };
}
