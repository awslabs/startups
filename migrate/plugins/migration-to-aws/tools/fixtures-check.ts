// fixtures-check.ts — structural integrity gate for the committed replay fixtures.
//
// WHY: the fixture sets under `fixtures/` are the plugin's regression harness — canned
// captures, mid-pipeline seeds, expected-assertion documents, and stdlib asserters that
// fresh-agent replays are checked against. They rot silently in ways `mise run build`
// never sees: a capture manifest can reference files that were never committed (a
// repo-root `.gitignore` rule once swallowed three of them), a seed `.phase-status.json`
// can lag behind the phases a skill declares, and an asserter can carry syntax only a
// newer Python accepts. Each of those failures is invisible until someone replays the
// fixture by hand. This check makes them a CI failure instead.
//
// Checks (all offline, zero-dep, read-only):
//   1. every fixtures/**/*.json (dotfiles included) parses
//   2. every fixtures/**/*.py byte-compiles under the ambient python3
//   3. every capture manifest's file references resolve:
//        - `captures[]` / `api[]` entries with status "ok" must have their file on disk
//          (failed/skipped entries may legitimately have none)
//        - `build.files[]` must all exist unless build.method is "unavailable"
//   4. no file under fixtures/ is gitignored (exists locally but would never commit)
//   5. every fixtures/**/.phase-status.json is schema-shaped (migration_id/last_updated/
//      phases; statuses in the enum) and its phases match the owning skill's declared
//      phase set exactly (owning skill inferred from the fixture dir's first name
//      segment -> skills/<segment>-to-aws; cross-check skipped when no such skill)
//
// Usage:
//   node fixtures-check.ts            # check the repo's own fixtures (mise task)
//   node fixtures-check.ts <root>     # check another checkout (e.g. a PR worktree)
//
// Zero-dep: runs under Node 24 native TS type-stripping (same as the other tools).

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, join, relative } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.argv[2] ?? ".";
const PLUGIN = join(ROOT, "migrate/plugins/migration-to-aws");
const FIXTURES = join(PLUGIN, "fixtures");
const SKILLS = join(PLUGIN, "skills");

const problems: string[] = [];
const notes: string[] = [];

/** Recursively list files under a dir (paths relative to it), or [] when absent. */
function walk(root: string, rel = ""): string[] {
  const abs = join(root, rel);
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs)) {
    const r = rel ? join(rel, entry) : entry;
    if (statSync(join(root, r)).isDirectory()) out.push(...walk(root, r));
    else out.push(r);
  }
  return out;
}

const files = walk(FIXTURES);
const jsonFiles = files.filter((f) => f.endsWith(".json"));
const pyFiles = files.filter((f) => f.endsWith(".py"));
const manifests = jsonFiles.filter((f) => basename(f) === "manifest.json");
const phaseStatusFiles = jsonFiles.filter((f) => basename(f) === ".phase-status.json");

// ---- 1. JSON parses -------------------------------------------------------
const parsed = new Map<string, unknown>();
for (const rel of jsonFiles) {
  try {
    parsed.set(rel, JSON.parse(readFileSync(join(FIXTURES, rel), "utf8")));
  } catch (e) {
    problems.push(`invalid JSON: fixtures/${rel} (${(e as Error).message})`);
  }
}

// ---- 2. asserters parse as Python -------------------------------------------
// ast.parse (not py_compile): same syntax guarantee, but writes no __pycache__
// bytecode into the fixture tree. Checked one file at a time so every broken
// asserter is reported, not just the first.
if (pyFiles.length > 0) {
  const probe = spawnSync("python3", ["--version"], { encoding: "utf8" });
  if (probe.error) {
    notes.push(`python3 unavailable — skipped syntax-checking ${pyFiles.length} asserter(s)`);
  } else {
    for (const f of pyFiles) {
      const py = spawnSync(
        "python3",
        ["-c", "import ast,sys\nsrc=open(sys.argv[1],'rb').read()\nast.parse(src, sys.argv[1])", join(FIXTURES, f)],
        { encoding: "utf8" },
      );
      if (py.status !== 0) {
        problems.push(`asserter does not parse: fixtures/${f}\n${(py.stderr || py.stdout).trim()}`);
      }
    }
  }
}

// ---- 3. manifest reference integrity ---------------------------------------
type CaptureEntry = { file?: unknown; status?: unknown };
function checkEntries(manifestRel: string, entries: unknown, label: string): number {
  if (!Array.isArray(entries)) return 0;
  let checked = 0;
  for (const raw of entries) {
    const e = raw as CaptureEntry;
    if (typeof e?.file !== "string") continue;
    checked++;
    const target = join(FIXTURES, dirname(manifestRel), e.file);
    if (e.status === "ok" && !existsSync(target)) {
      problems.push(
        `fixtures/${manifestRel}: ${label} entry '${e.file}' has status "ok" but the file is missing`,
      );
    }
  }
  return checked;
}

let manifestRefs = 0;
for (const rel of manifests) {
  const m = parsed.get(rel) as Record<string, unknown> | undefined;
  if (!m) continue; // parse failure already reported
  manifestRefs += checkEntries(rel, m["captures"], "captures[]");
  manifestRefs += checkEntries(rel, m["api"], "api[]");
  const build = m["build"] as { method?: unknown; files?: unknown } | undefined;
  if (build && build.method !== "unavailable" && Array.isArray(build.files)) {
    for (const f of build.files) {
      if (typeof f !== "string") continue;
      manifestRefs++;
      if (!existsSync(join(FIXTURES, dirname(rel), f))) {
        problems.push(
          `fixtures/${rel}: build.files entry '${f}' is missing (build.method is "${String(build.method)}")`,
        );
      }
    }
  }
}

// ---- 4. gitignore detection -------------------------------------------------
if (files.length > 0) {
  const relToRepo = files.map((f) => join(relative(ROOT, FIXTURES), f)).join("\n");
  const ci = spawnSync("git", ["-C", ROOT, "check-ignore", "--stdin"], {
    input: relToRepo,
    encoding: "utf8",
  });
  if (ci.error) {
    notes.push("git unavailable — skipped the gitignore check");
  } else {
    // exit 0 = some ignored (listed on stdout), 1 = none ignored, 128 = error
    if (ci.status !== null && ci.status > 1) {
      notes.push(`git check-ignore failed (${(ci.stderr || "").trim()}) — skipped the gitignore check`);
    } else {
      for (const line of ci.stdout.split("\n").filter(Boolean)) {
        problems.push(`gitignored fixture: ${line} exists locally but will never be committed`);
      }
    }
  }
}

// ---- 5. .phase-status.json shape + phase-set cross-check --------------------
const STATUS_ENUM = new Set(["pending", "in_progress", "completed"]);

/** Declared phases of a skill: the `_phase:` frontmatter values under references/phases/. */
function declaredPhases(skill: string): Set<string> | null {
  const phasesDir = join(SKILLS, skill, "references/phases");
  if (!existsSync(phasesDir)) return null;
  const out = new Set<string>();
  for (const rel of walk(phasesDir).filter((f) => f.endsWith(".md"))) {
    const head = readFileSync(join(phasesDir, rel), "utf8").slice(0, 400);
    const m = head.match(/^_phase:\s*([a-z0-9_-]+)\s*$/m);
    if (m) out.add(m[1]);
  }
  return out.size > 0 ? out : null;
}

for (const rel of phaseStatusFiles) {
  const ps = parsed.get(rel) as Record<string, unknown> | undefined;
  if (!ps) continue;
  const where = `fixtures/${rel}`;
  for (const req of ["migration_id", "last_updated", "phases"]) {
    if (!(req in ps)) problems.push(`${where}: missing required key '${req}'`);
  }
  const phases = (ps["phases"] ?? {}) as Record<string, unknown>;
  for (const [name, status] of Object.entries(phases)) {
    if (typeof status !== "string" || !STATUS_ENUM.has(status)) {
      problems.push(`${where}: phases.${name} has invalid status '${String(status)}'`);
    }
  }
  // owning skill: first segment of the fixture dir name -> skills/<segment>-to-aws
  const fixtureDir = rel.split("/")[0] ?? "";
  const skill = `${fixtureDir.split("-")[0]}-to-aws`;
  const declared = declaredPhases(skill);
  if (!declared) {
    notes.push(`${where}: no declared-phase set found for inferred skill '${skill}' — cross-check skipped`);
    continue;
  }
  const have = new Set(Object.keys(phases));
  for (const p of declared) {
    if (!have.has(p)) problems.push(`${where}: skill '${skill}' declares phase '${p}' but the seed omits it`);
  }
  for (const p of have) {
    if (!declared.has(p)) problems.push(`${where}: seed lists phase '${p}' which skill '${skill}' does not declare`);
  }
  const current = ps["current_phase"];
  if (typeof current === "string" && current !== "complete" && !declared.has(current)) {
    problems.push(`${where}: current_phase '${current}' is not a declared phase of '${skill}'`);
  }
}

// ---- report -----------------------------------------------------------------
for (const n of notes) console.log(`note: ${n}`);
if (problems.length > 0) {
  console.error(`fixtures check: FAILED (${problems.length} problem(s))`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(
  `fixtures check: OK (${jsonFiles.length} json, ${pyFiles.length} asserter(s), ` +
    `${manifests.length} manifest(s) / ${manifestRefs} reference(s), ${phaseStatusFiles.length} phase-status seed(s))`,
);
