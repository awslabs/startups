// build.ts — generate and verify the standalone ATX Custom bundle for agent-advisor.
//
// WHY: the plugin keeps the FULL skill (including the Migration Plan stage, which loads the
// sibling gcp-to-aws engine). The ATX bundle must be self-contained — an ATX transformation
// definition has no sibling skills to climb into. Rather than fork the prose (which drifts —
// see the cached_stale enum bug and the arm64 rate copies), the bundle is a STRICT SUBSET of
// the canonical skill plus ONE generated entry file:
//
//   transformation_definition.md = atx/agent-advisor/preamble.md + skills/agent-advisor/SKILL.md
//
// Every other bundle file is byte-identical to its canonical source. The sibling-reference scan
// below is what makes "the ATX build does not depend on gcp-to-aws" a machine-checked property
// instead of a promise.
//
// Usage:
//   node tools/atx-bundle/build.ts            # CHECK mode: verify only, exit 1 on any ERROR
//   node tools/atx-bundle/build.ts --write     # BUILD mode: write the bundle, then verify
//
// Zero-dep: runs under Node 24 native TS type-stripping (same as the other tools here).

import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";

const PLUGIN = "migrate/plugins/migration-to-aws";
const SKILL = join(PLUGIN, "skills/agent-advisor");
const ATX = join(PLUGIN, "atx/agent-advisor");
const MANIFEST = join(ATX, "manifest.txt");
const PREAMBLE = join(ATX, "preamble.md");
const OUT = ".tmp/atx-bundle/agent-advisor";

// Canonical files that intentionally never ship to ATX. A canonical file matching none of these
// and absent from the manifest is an ERROR — new files must be classified, not silently dropped.
const EXCLUDE_RULES: { pattern: RegExp; why: string }[] = [
  { pattern: /^scripts\/test_/, why: "unit tests — not needed at runtime" },
];

// Terminal / pseudo phases: legal `_advances_to` targets that are states, not phase directories.
const TERMINAL_PHASES = new Set(["complete"]);

// Sibling-skill references, split by severity because the two kinds fail differently:
//
//   LOAD  — a path the runtime would actually resolve and read. In the bundle there is no sibling
//           to read, so the phase would break. ERROR.
//   CITE  — prose naming a sibling skill (a provenance note, or "run that skill next"). Nothing
//           breaks, but it dangles for an ATX reader who has no such skill. WARN.
//
// `${CLAUDE_PLUGIN_ROOT}/skills/agent-advisor/...` is the skill addressing ITSELF — not a sibling
// dependency — so the load pattern carries a negative lookahead for its own name.
const SIBLING_LOAD_PATTERNS = [
  /\$\{CLAUDE_PLUGIN_ROOT\}\/skills\/(?!agent-advisor)[a-z-]+/,
  /\$GCP_BASE/,
];
const SIBLING_CITE_PATTERNS = [
  /skills\/gcp-to-aws/,
  /skills\/heroku-to-aws/,
  /skills\/vercel-to-aws/,
  /skills\/llm-to-bedrock/,
  /skills\/shared/,
];
const SIBLING_ALLOWED_PREFIX = "references/phases/migration-plan/";

// Build artefacts and virtualenvs live next to the canonical files but are not part of the skill.
const IGNORE_DIRS = new Set(["__pycache__", ".venv", ".pytest_cache", "node_modules"]);

// The capability gate marker that migration-plan.md must carry for the bundle to be honest about
// the missing engine. Keep this string in sync with the phase file.
const CAPABILITY_GATE_MARKER = "ATX capability gate";

// Prose pointers at Claude Code slash commands. An ATX user cannot run these, so they should be
// reworded to be environment-neutral. Tracked as WARN so the bundle still builds.
const SLASH_COMMAND_PATTERN = /\/migration-to-aws:[a-z-]+/g;

const write = process.argv.includes("--write");
const errors: string[] = [];
const warnings: string[] = [];

function walk(root: string, rel = ""): string[] {
  const abs = join(root, rel);
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs)) {
    if (IGNORE_DIRS.has(entry)) continue;
    const r = rel ? join(rel, entry) : entry;
    if (statSync(join(root, r)).isDirectory()) out.push(...walk(root, r));
    else out.push(r);
  }
  return out;
}

function readManifest(): string[] {
  if (!existsSync(MANIFEST)) {
    errors.push(`manifest missing: ${MANIFEST}`);
    return [];
  }
  return readFileSync(MANIFEST, "utf8")
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
}

const manifest = readManifest();
const manifestSet = new Set(manifest);

// ---------------------------------------------------------------- check 1: manifest <-> canonical
const canonical = walk(SKILL).filter((f) => !f.startsWith(".") && !f.includes("/."));
const canonicalSet = new Set(canonical);

for (const rel of manifest) {
  if (!canonicalSet.has(rel)) {
    errors.push(`manifest lists a file that does not exist in the canonical skill: ${rel}`);
  }
  const excluded = EXCLUDE_RULES.find((r) => r.pattern.test(rel));
  if (excluded) {
    errors.push(`manifest lists ${rel}, but an exclusion rule covers it (${excluded.why})`);
  }
}
for (const rel of canonical) {
  if (manifestSet.has(rel)) continue;
  if (EXCLUDE_RULES.some((r) => r.pattern.test(rel))) continue;
  errors.push(
    `canonical file is neither in the manifest nor excluded — classify it: ${rel}`,
  );
}

// ------------------------------------------------------- check 2: no sibling-skill dependencies
for (const rel of manifest) {
  const abs = join(SKILL, rel);
  if (!existsSync(abs)) continue;
  if (rel.startsWith(SIBLING_ALLOWED_PREFIX)) continue; // gated stage — see check 3
  const text = readFileSync(abs, "utf8");
  for (const pattern of SIBLING_LOAD_PATTERNS) {
    const hit = text.match(pattern);
    if (hit) {
      errors.push(
        `${rel} RESOLVES a sibling-skill path (${hit[0]}) — nothing to read in a standalone bundle`,
      );
    }
  }
  for (const pattern of SIBLING_CITE_PATTERNS) {
    const hit = text.match(pattern);
    if (hit) {
      warnings.push(`${rel} names a sibling skill in prose (${hit[0]}) — dangles for an ATX reader`);
    }
  }
}

// ------------------------------------- check 3: the Migration Plan phase carries the capability gate
const gatePhase = "references/phases/migration-plan/migration-plan.md";
if (manifestSet.has(gatePhase)) {
  const text = existsSync(join(SKILL, gatePhase)) ? readFileSync(join(SKILL, gatePhase), "utf8") : "";
  if (!text.includes(CAPABILITY_GATE_MARKER)) {
    errors.push(
      `${gatePhase} must carry the "${CAPABILITY_GATE_MARKER}" marker: without it the bundle ` +
        `would try to load the absent gcp-to-aws engine instead of resolving the stage to ` +
        `not_applicable`,
    );
  }
}

// ------------------------------------------------- check 4: the phase graph closes inside the bundle
const phaseFiles = manifest.filter((f) => /^references\/phases\/.*\.md$/.test(f));
const phaseDirs = new Set(
  phaseFiles.map((f) => f.split("/")[2]).filter((d): d is string => Boolean(d)),
);
for (const rel of phaseFiles) {
  const text = readFileSync(join(SKILL, rel), "utf8");
  for (const m of text.matchAll(/^\s*_file:\s*(phases\/[^\s]+)/gm)) {
    const target = join("references", m[1]!);
    if (!manifestSet.has(target)) {
      errors.push(`${rel} loads a fragment missing from the bundle: ${m[1]}`);
    }
  }
  for (const m of text.matchAll(/^_advances_to:\s*([a-z-]+)/gm)) {
    if (!phaseDirs.has(m[1]!) && !TERMINAL_PHASES.has(m[1]!)) {
      errors.push(`${rel} advances to a phase missing from the bundle: ${m[1]}`);
    }
  }
}

// ---------------------------------------- check 5: runtime scripts survive a host without uv
// A TOP-LEVEL third-party import makes the script unimportable on a bare python3 host — ERROR.
// A lazy import (inside a function, or guarded by try/except ImportError) only fails on the code
// path that needs it, which the ATX preamble may have disabled anyway — WARN, with the caller
// responsible for provisioning the dep (`uv run --with ...`) or degrading.
const THIRD_PARTY = /(jsonschema|yaml|requests|boto3|pydantic|anthropic)\b/;
for (const rel of manifest.filter((f) => /^scripts\/.*\.py$/.test(f))) {
  const text = readFileSync(join(SKILL, rel), "utf8");
  for (const m of text.matchAll(/^(\s*)(?:import|from)\s+([A-Za-z_][\w.]*)/gm)) {
    const [, indent, mod] = m;
    if (!THIRD_PARTY.test(mod!)) continue;
    if (indent!.length === 0) {
      errors.push(
        `${rel} imports ${mod} at top level — the script cannot even be loaded on a bare python3 host`,
      );
    } else {
      warnings.push(
        `${rel} lazily imports ${mod} — that code path needs uv (or the dep preinstalled) on the ATX host`,
      );
    }
  }
}

// ------------------------------------------------------------- check 6: preamble present, entry sane
if (!existsSync(PREAMBLE)) {
  errors.push(`preamble missing: ${PREAMBLE}`);
}
if (!manifestSet.has("SKILL.md")) {
  errors.push("manifest must list SKILL.md — it is the body of transformation_definition.md");
}

// ------------------------------------------------------------------- WARN: Claude Code slash commands
for (const rel of manifest) {
  const abs = join(SKILL, rel);
  if (!existsSync(abs)) continue;
  const hits = new Set(readFileSync(abs, "utf8").match(SLASH_COMMAND_PATTERN) ?? []);
  if (hits.size > 0) {
    warnings.push(`${rel} points at Claude Code slash command(s) ${[...hits].join(", ")}`);
  }
}

// ------------------------------------------------------------------------------------ build mode
if (write) {
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  let copied = 0;
  for (const rel of manifest) {
    const src = join(SKILL, rel);
    if (!existsSync(src)) continue;
    if (rel === "SKILL.md") continue; // becomes transformation_definition.md
    const dest = join(OUT, rel);
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(src, dest);
    copied += 1;
  }
  if (existsSync(PREAMBLE) && existsSync(join(SKILL, "SKILL.md"))) {
    // Strip SKILL.md's YAML frontmatter: `name`/`description` are Claude Code plugin metadata
    // (they drive skill discovery there). ATX takes the transformation name and description as
    // `atx custom def publish` flags, so carrying the block would leave a stray YAML island in
    // the middle of the definition.
    const skillText = readFileSync(join(SKILL, "SKILL.md"), "utf8");
    const body = skillText.startsWith("---\n")
      ? skillText.slice(skillText.indexOf("\n---", 4) + 4).replace(/^\n+/, "")
      : skillText;
    const entry = `${readFileSync(PREAMBLE, "utf8").trimEnd()}\n\n${body}`;
    writeFileSync(join(OUT, "transformation_definition.md"), entry);
  }
  console.log(`built ${OUT}: ${copied} copied + transformation_definition.md`);
  console.log(
    `publish with:\n  atx custom def publish --transformation-name agent-advisor --source-directory ${OUT}`,
  );
}

// --------------------------------------------------------------------------------------- report
for (const w of warnings) console.log(`WARN  ${w}`);
if (errors.length > 0) {
  for (const e of errors) console.error(`ERROR ${e}`);
  console.error(`\natx:check FAILED — ${errors.length} error(s), ${warnings.length} warning(s)`);
  process.exit(1);
}
console.log(
  `atx:check OK — ${manifest.length} files in the bundle, ${warnings.length} warning(s)`,
);
