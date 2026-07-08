// parse.ts — read a markdown file's `---` frontmatter block and bind it into the
// typed shapes in types.ts. Zero-dep: a small reader for the YAML subset we author
// (flat scalars, a `_fragments` list of `{_id, _trigger, _file}`, and `_assemble`
// / `_produces` / `_reads` / `_contributes` lists). Not a general YAML parser.

import type {
  ArtifactRef,
  AssemblerFrontmatter,
  CheckItem,
  ExecSpec,
  FragmentFrontmatter,
  FragmentRef,
  KnowledgeRef,
  PhaseFrontmatter,
  ReEntryGuard,
  Trigger,
} from "./types.ts";
import { readFileSync } from "node:fs";

const PHASE_KEYS = new Set([
  "_phase", "_title", "_kind", "_requires_phase", "_init", "_interactive",
  "_input", "_fragments", "_trigger", "_assemble", "_produces", "_advances_to",
  "_exec", "_re_entry_guard", "_preconditions", "_postconditions",
  "_forbids_files", "_knowledge",
]);
/** The closed vocabulary of check kinds usable in _preconditions/_postconditions. */
export const CHECK_KINDS = new Set([
  "_check_phase_completed", "_check_single_active_phase", "_check_file_exists",
  "_validate_json", "_assert",
]);
/** The closed vocabulary of _on_failure / _on_error actions. */
export const ON_ERROR_ACTIONS = new Set([
  "_warn_and_skip", "_default_and_warn", "_halt_and_inform", "_unrecoverable",
]);
const GUARD_KEYS = new Set([
  "_stale_if_completed", "_stale_artifact", "_on_reentry", "_on_confirm",
]);
/** The closed vocabulary of `_exec` sub-keys. */
const EXEC_KEYS = new Set(["_agent"]);
/** The closed vocabulary of `_exec._agent` capability tiers (ordered least→most privileged). */
export const EXEC_TIERS = ["ro", "rw", "git"] as const;
export const EXEC_TIER_SET = new Set<string>(EXEC_TIERS);
const FRAGMENT_KEYS = new Set(["_fragment", "_of_phase", "_contributes"]);
const ASSEMBLER_KEYS = new Set(["_assemble", "_of_phase", "_reads", "_produces", "_knowledge"]);

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

/**
 * An ARTIFACT block-list (`_produces` / `_contributes`): each item is either a
 * bare filename (`- foo.tf`) or an inline conditional map (`- { file: foo.tf,
 * _when: "..." }`), mirroring `_knowledge`. Returns one ArtifactRef per item.
 * A map item with no parseable `file:` yields `{ file: "", when }` so the checker
 * can flag it as malformed. `when` is opaque prose (bound, not evaluated by CI).
 */
function artifactList(fm: string, key: string): ArtifactRef[] {
  const out: ArtifactRef[] = [];
  for (const raw of blockList(fm, key)) {
    if (raw.startsWith("{")) {
      const fmatch = /file:\s*([^,}]+)/.exec(raw);
      const file = fmatch ? fmatch[1].trim().replace(/^["']|["']$/g, "") : "";
      const wmatch = /_when:\s*["']?([^"'}]+)["']?/.exec(raw);
      out.push({ file, when: wmatch ? wmatch[1].trim() : null });
    } else {
      out.push({ file: raw, when: null });
    }
  }
  return out;
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

/** Parse `_input`: either a scalar (`workspace` / a quoted glob) or a block list. */
function parseInput(fm: string): string[] {
  // Block form first: `_input:` followed by newline + `- ` items.
  const block = blockList(fm, "_input");
  if (block.length) return block;
  // Scalar form: `_input: <value>` on the same line.
  const m = /^_input:[ \t]*(\S.*)$/m.exec(fm);
  if (m) return [m[1].trim().replace(/^["']|["']$/g, "")];
  return [];
}

/** Parse `_knowledge`: a list of inline `{ file: <path>, _when: <prose> }` maps. */
function parseKnowledge(fm: string): KnowledgeRef[] {
  const body = indentedBlock(fm, "_knowledge");
  if (body === null) return [];
  const out: KnowledgeRef[] = [];
  for (const line of body.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("-")) continue;
    const fm2 = /file:\s*([^,}]+)/.exec(t);
    if (!fm2) continue;
    const file = fm2[1].trim().replace(/^["']|["']$/g, "");
    const wm = /_when:\s*["']?([^"'}]+)["']?/.exec(t);
    out.push({ file, when: wm ? wm[1].trim() : null });
  }
  return out;
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

/**
 * Parse the `_exec:` block, or null when the key is absent. Accepts both an inline
 * map (`_exec: { _agent: rw }`) and a nested block:
 *   _exec:
 *     _agent: rw
 * `_agent` is bound verbatim; the checker enforces the closed tier vocabulary and
 * unknown sub-keys are collected for the typo check (same pattern as the guard).
 */
function parseExec(fm: string): ExecSpec | null {
  // Inline form: `_exec: { ... }` on one line.
  const inline = /^_exec:\s*\{([^}]*)\}\s*$/m.exec(fm);
  if (inline) {
    const body = inline[1];
    const am = /_agent:\s*([^,}]+)/.exec(body);
    const keys: string[] = [];
    for (const m of body.matchAll(/(_[a-z_]+):/g)) keys.push(m[1]);
    return {
      agent: am ? am[1].trim().replace(/^["']|["']$/g, "") : null,
      unknownKeys: keys.filter((k) => !EXEC_KEYS.has(k)),
    };
  }
  // Block form: `_exec:` on its own line, then indented sub-keys.
  const block = indentedBlock(fm, "_exec");
  if (block === null) return null;
  const am = /^\s*_agent:\s*(.+)$/m.exec(block);
  const keys: string[] = [];
  for (const line of block.split("\n")) {
    const m = /^\s*(_[a-z_]+):/.exec(line);
    if (m) keys.push(m[1]);
  }
  return {
    agent: am ? am[1].trim().replace(/^["']|["']$/g, "") : null,
    unknownKeys: keys.filter((k) => !EXEC_KEYS.has(k)),
  };
}

/** Parse a `_preconditions` / `_postconditions` list into CheckItems. Each list item
 * is `- <check_kind>: <arg>` optionally followed by an `_on_failure: <action>` line. */
function parseChecks(fm: string, key: string): CheckItem[] {
  const body = indentedBlock(fm, key);
  if (body === null) return [];
  const out: CheckItem[] = [];
  // Split into items on lines beginning (after indent) with `- `.
  const lines = body.split("\n");
  let cur: string[] | null = null;
  const items: string[][] = [];
  for (const line of lines) {
    if (/^\s*-\s+/.test(line)) {
      if (cur) items.push(cur);
      cur = [line];
    } else if (cur && line.trim() !== "") {
      cur.push(line);
    }
  }
  if (cur) items.push(cur);

  for (const item of items) {
    const joined = item.join("\n");
    // the check keyword is the first `_<kind>:` after the leading `- `
    const km = /^\s*-\s+(_[a-z_]+):\s*(.*)$/m.exec(item[0]);
    if (!km) continue;
    const kind = km[1];
    const rawArg = km[2].trim();
    let arg: string[];
    if (kind === "_assert") {
      arg = [rawArg.replace(/^["']|["']$/g, "")]; // opaque prose (bound, not evaluated)
    } else if (rawArg.startsWith("[")) {
      arg = rawArg.replace(/^\[|\]$/g, "").split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean);
    } else if (rawArg === "" || rawArg === "true") {
      arg = rawArg === "true" ? ["true"] : [];
    } else {
      arg = [rawArg.replace(/^["']|["']$/g, "")];
    }
    const om = /_on_failure:\s*(_[a-z_]+)/.exec(joined);
    out.push({ kind, arg, onFailure: om ? om[1] : null });
  }
  return out;
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
    // _interactive is a tri-state: true / false / null (absent). Parsed strictly so a
    // typo'd value (e.g. `_interactive: yes`) reads as null (unspecified), which the
    // _exec gate then rejects rather than silently treating as "non-interactive".
    interactive: /^_interactive:\s*true\s*$/m.test(fm)
      ? true
      : /^_interactive:\s*false\s*$/m.test(fm)
      ? false
      : null,
    fragments: parseFragments(fm),
    trigger: ptrig ? parseTrigger(ptrig[1]) : null,
    assembleFile: assembleBlock ? assembleBlock[1].trim() : null,
    produces: artifactList(fm, "_produces").map((a) => a.file),
    producesRefs: artifactList(fm, "_produces"),
    advancesTo: scalar(fm, "_advances_to"),
    exec: parseExec(fm),
    reEntryGuard: parseReEntryGuard(fm),
    preconditions: parseChecks(fm, "_preconditions"),
    postconditions: parseChecks(fm, "_postconditions"),
    forbidsFiles: blockList(fm, "_forbids_files"),
    input: parseInput(fm),
    knowledge: parseKnowledge(fm),
    unknownKeys: unknownAmong(fm, PHASE_KEYS),
  };
}

export function parseFragment(path: string, fm: string): FragmentFrontmatter {
  return {
    kind: "fragment",
    sourceFile: path,
    fragment: scalar(fm, "_fragment") ?? "",
    ofPhase: scalar(fm, "_of_phase"),
    contributes: artifactList(fm, "_contributes").map((a) => a.file),
    contributesRefs: artifactList(fm, "_contributes"),
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
    produces: artifactList(fm, "_produces").map((a) => a.file),
    producesRefs: artifactList(fm, "_produces"),
    knowledge: parseKnowledge(fm),
    unknownKeys: unknownAmong(fm, ASSEMBLER_KEYS),
  };
}
